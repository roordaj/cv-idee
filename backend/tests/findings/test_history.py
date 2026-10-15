"""Historical advice keeps the original provenance through edits and status changes."""

import json
from collections.abc import AsyncIterator
from copy import deepcopy
from importlib.resources import files
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cvidee.api.schemas.settings import SettingsIn
from cvidee.config import Settings
from cvidee.findings.history import HistoryReadModel
from cvidee.findings.repository import SqlFindingRepository
from cvidee.main import create_app
from cvidee.rules.changelog import changes_since, parse_changelogs
from cvidee.rules.registry import RuleRegistry
from cvidee.rules.short_cycling import ShortCyclingRule
from cvidee.runner.service import AnalysisRunner, RunnerSettings
from cvidee.settings.backend import SettingsBackend
from cvidee.store.enums import SnapshotTrigger
from cvidee.store.models import RecommendationSnapshot
from tests.runner.test_runner import END, HUGE, make_db, seed


@pytest.fixture
def history_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[sessionmaker[Session], AnalysisRunner, SettingsBackend]:
    factory = make_db(tmp_path, "history")
    seed(factory)
    rule = ShortCyclingRule()
    monkeypatch.setattr(rule, "required_signals", frozenset())
    monkeypatch.setattr(rule, "resolution_limits", lambda params: ())
    runner = AnalysisRunner(factory, RunnerSettings(chunk_ms=HUGE, registry=RuleRegistry([rule])))
    settings = SettingsBackend(factory, runner)
    initial = settings.settings()
    settings.put_settings(
        SettingsIn(
            revision=initial.revision,
            values=initial.values.model_copy(update={"short_cycle_min": 4, "min_short_cycles": 2}),
        )
    )
    assert all(run.status.value == "succeeded" for run in runner.tick(END + 300_000))
    with factory() as session:
        assert session.scalar(select(RecommendationSnapshot)) is not None
    return factory, runner, settings


@pytest.fixture
async def client(
    history_setup: tuple[sessionmaker[Session], AnalysisRunner, SettingsBackend],
) -> AsyncIterator[httpx.AsyncClient]:
    factory, runner, _ = history_setup
    app = create_app(Settings.model_validate({}))
    app.state.session_factory = factory
    app.state.runner = runner
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


async def test_old_parameters_and_provenance_survive_settings_and_status_changes(
    client: httpx.AsyncClient,
    history_setup: tuple[sessionmaker[Session], AnalysisRunner, SettingsBackend],
) -> None:
    factory, runner, settings = history_setup
    original = (await client.get("/api/history")).json()["items"][0]
    assert original["parameters"]["short_cycle_min"] == 4
    assert original["profile_version"] is not None
    assert original["config_hash"]
    assert "Kortecyclusgrens: 4 min" in original["settings_text"]
    with factory() as session:
        row = session.scalar(select(RecommendationSnapshot))
        assert row is not None
        frozen = deepcopy(row.content)
        frozen_settings = deepcopy(row.settings)
        original_id = row.id
        assert row.trigger is SnapshotTrigger.CREATED
        assert row.settings["installation_profile"]["specs"]
    ident = original["finding_id"]
    assert (
        await client.post(f"/api/findings/{ident}/notes", json={"text": "Eerst observeren."})
    ).status_code == 201
    assert (
        await client.post(f"/api/findings/{ident}/status", json={"status": "accepted"})
    ).status_code == 200
    before = (await client.get("/api/history")).json()["total"]
    await client.post(f"/api/findings/{ident}/status", json={"status": "accepted"})
    assert (await client.get("/api/history")).json()["total"] == before
    current = settings.settings()
    settings.put_settings(
        SettingsIn(
            revision=current.revision,
            values=current.values.model_copy(update={"short_cycle_min": 5}),
        )
    )
    runner.tick(END + 300_000)
    body = (await client.get("/api/history")).json()
    old = next(item for item in body["items"] if item["id"] == original["id"])
    assert old["parameters"]["short_cycle_min"] == 4
    assert "Kortecyclusgrens: 4 → 5" in old["rule_now_text"]
    accepted = next(item for item in body["items"] if item["status"] == "accepted")
    assert accepted["note"] == "Eerst observeren."
    assert accepted["observation_period"] == original["observation_period"]
    assert accepted["config_hash"] == original["config_hash"]
    assert accepted["parameters"] == original["parameters"]
    with factory() as session:
        row = session.get(RecommendationSnapshot, original_id)
        assert row is not None
        assert row.content == frozen
        assert row.settings == frozen_settings


async def test_expiry_creates_a_status_snapshot_and_history_is_paginated(
    client: httpx.AsyncClient,
    history_setup: tuple[sessionmaker[Session], AnalysisRunner, SettingsBackend],
) -> None:
    factory, _, _ = history_setup
    ident = (await client.get("/api/history")).json()["items"][0]["finding_id"]
    await client.post(
        f"/api/findings/{ident}/status",
        json={"status": "postponed", "postponed_until": "2099-01-01T00:00:00Z"},
    )
    with factory.begin() as session:
        repo = SqlFindingRepository(session)
        finding = repo.by_human_id(ident)
        assert finding is not None
        rec = repo.recommendation_of(finding)
        assert rec is not None
        rec.postponed_until_ts = 1
    assert (await client.get(f"/api/findings/{ident}")).json()["status"] == "open"
    page = (await client.get("/api/history?limit=1&offset=0")).json()
    assert page["total"] >= 3
    assert len(page["items"]) == 1
    assert page["items"][0]["status"] == "open"
    next_page = (await client.get("/api/history?limit=1&offset=1")).json()
    assert next_page["items"][0]["status"] == "postponed"
    assert (await client.get("/api/history?offset=999")).json()["items"] == []
    for query in ("limit=0", "offset=-1", "limit=501"):
        assert (await client.get(f"/api/history?{query}")).status_code == 422
    with factory() as session:
        unavailable = HistoryReadModel(session, RuleRegistry([])).history(50, 0)
        assert "niet meer beschikbaar" in unavailable.items[0].rule_now_text


def test_packaged_changelog_matches_documented_versions() -> None:
    directory = Path(__file__).resolve().parents[3] / "docs" / "regels"
    assert json.loads(
        files("cvidee.rules").joinpath("changelog.json").read_text()
    ) == parse_changelogs(directory)
    assert changes_since("kort-branden", "0.9.0", "1.0.0") == ["Eerste versie."]
    assert changes_since("kort-branden", "1.0.0", "1.0.0") == []


async def test_status_snapshot_keeps_original_profile_after_profile_edit(
    client: httpx.AsyncClient,
    history_setup: tuple[sessionmaker[Session], AnalysisRunner, SettingsBackend],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cvidee.installation.defaults import default_profile
    from cvidee.installation.repository import SqlInstallationProfileRepository
    from cvidee.installation.specs import MAX_FLOW
    from cvidee.store.enums import SpecStatus

    factory, runner, _ = history_setup
    old = (await client.get("/api/history")).json()["items"][0]
    with factory.begin() as session:
        updated = default_profile(END + 1)
        updated.valid_from_ts = END + 1
        spec = next(spec for spec in updated.specs if spec.key == MAX_FLOW)
        spec.status, spec.value_num = SpecStatus.KNOWN, 45
        SqlInstallationProfileRepository(session).save_new_version(updated)
    monkeypatch.setattr(runner.registry.get("kort-branden"), "version", "1.1.0")
    await client.post(f"/api/findings/{old['finding_id']}/status", json={"status": "done"})
    new = (await client.get("/api/history")).json()["items"][0]
    assert new["profile_version"] == old["profile_version"]
    assert "Maximale CV-aanvoer: onbekend" in new["settings_text"]
    assert "45 °C" not in new["settings_text"]
    assert new["rule"]["version"] == "1.0.0"
    assert "1.0.0 naar 1.1.0" in new["rule_now_text"]
