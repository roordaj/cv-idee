"""Immutable settings, conflict protection and effective runner parameters (#22)."""

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cvidee.api.problems import ProblemError
from cvidee.api.routes.settings import get_settings_backend
from cvidee.api.schemas.settings import SettingsIn
from cvidee.config import Settings
from cvidee.main import create_app
from cvidee.rules.base import FindingCandidate, RuleContext
from cvidee.rules.registry import RuleRegistry, default_registry
from cvidee.rules.short_cycling import ShortCyclingParams, ShortCyclingRule
from cvidee.runner.service import AnalysisRunner, RunnerSettings
from cvidee.settings.backend import SettingsBackend
from cvidee.settings.repository import rule_params
from cvidee.store.engine import create_db_engine, create_session_factory, database_url
from cvidee.store.models import AnalysisRun, RecommendationSnapshot, SettingsRevision
from cvidee.store.schema import upgrade_to_head
from tests.rules.test_short_cycling import burst, ctx
from tests.runner.test_runner import END, HUGE, seed

NOW = 1_791_100_800_000


@pytest.fixture
def sessions(tmp_path: Path) -> sessionmaker[Session]:
    url = database_url(tmp_path / "settings.sqlite")
    upgrade_to_head(url)
    return create_session_factory(create_db_engine(url))


def test_defaults_noop_history_and_reverting_rejects_old_token(
    sessions: sessionmaker[Session],
) -> None:
    backend = SettingsBackend(sessions, clock=lambda: NOW)
    first = backend.settings()
    assert first.values.short_cycle_min == 3
    assert (
        backend.put_settings(SettingsIn(revision=first.revision, values=first.values)).revision
        == first.revision
    )
    assert backend.settings_history().items == []
    changed = backend.put_settings(
        SettingsIn(
            revision=first.revision,
            values=first.values.model_copy(update={"short_cycle_min": 4}),
            changed_by="Jan",
            note="Langere cycli onderzoeken",
        )
    )
    assert changed.revision != first.revision
    reverted = backend.put_settings(SettingsIn(revision=changed.revision, values=first.values))
    assert reverted.revision != first.revision
    with pytest.raises(ProblemError) as error:
        backend.put_settings(SettingsIn(revision=first.revision, values=first.values))
    assert error.value.problem.status == 409
    history = backend.settings_history().items
    assert len(history) == 2
    assert history[1].values.short_cycle_min == 4
    assert history[1].changed_by == "Jan"
    assert history[1].note == "Langere cycli onderzoeken"
    assert history[1].saved_at == datetime.fromtimestamp(NOW / 1000, UTC)


def test_few_zone_threshold_is_visible_and_unset_by_default(
    sessions: sessionmaker[Session],
) -> None:
    backend = SettingsBackend(sessions, clock=lambda: NOW)
    current = backend.settings()
    field = current.json_schema["properties"]["few_active_zones_max"]
    assert current.values.few_active_zones_max is None
    assert field["default"] is None
    assert field["x-unit"] == "zones"

    changed = backend.put_settings(
        SettingsIn(
            revision=current.revision,
            values=current.values.model_copy(update={"few_active_zones_max": 2}),
        )
    )
    assert changed.values.few_active_zones_max == 2


def test_onboarding_completion_persists_without_recompute(sessions: sessionmaker[Session]) -> None:
    runner = MagicMock(spec=AnalysisRunner)
    backend = SettingsBackend(sessions, runner, clock=lambda: NOW)
    initial = backend.settings()
    completed = datetime.fromtimestamp(NOW / 1000, UTC)
    saved = backend.put_settings(
        SettingsIn(
            revision=initial.revision,
            values=initial.values,
            onboarding_completed_at=completed,
        )
    )
    assert saved.onboarding_completed_at == completed
    assert not saved.recompute_started
    runner.request_recompute.assert_not_called()
    assert SettingsBackend(sessions).settings().onboarding_completed_at == completed


def test_short_cycle_change_changes_outcome_and_keeps_old_rule_snapshot(
    sessions: sessionmaker[Session],
) -> None:
    backend = SettingsBackend(sessions, clock=lambda: NOW)
    registry = default_registry()
    context = ctx(burst(1, 5))
    initial = backend.settings()
    original = registry.evaluate(
        "kort-branden", context, rule_params(registry, "kort-branden", initial.values)
    )
    assert len(original.candidates) == 1
    saved = backend.put_settings(
        SettingsIn(
            revision=initial.revision,
            values=initial.values.model_copy(update={"short_cycle_min": 1.5}),
        )
    )
    new = registry.evaluate(
        "kort-branden", context, rule_params(registry, "kort-branden", saved.values)
    )
    assert new.candidates == ()
    assert original.snapshot.params["short_cycle_min"] == 3
    assert new.snapshot.params["short_cycle_min"] == 1.5
    assert original.snapshot.params_hash != new.snapshot.params_hash


def test_runner_recomputes_with_settings_and_records_the_snapshot(
    sessions: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed(sessions)
    rule = ShortCyclingRule()
    # The synthetic runner fixture has no mode mapping and coarse change-only events.
    # Relax only availability here to observe the parameters passed by the real runner.
    monkeypatch.setattr(rule, "required_signals", frozenset())
    monkeypatch.setattr(rule, "resolution_limits", lambda params: ())
    seen: list[float] = []
    original_evaluate = rule._evaluate

    def capture(context: RuleContext, params: ShortCyclingParams) -> Sequence[FindingCandidate]:
        seen.append(params.short_cycle_min)
        return original_evaluate(context, params)

    monkeypatch.setattr(rule, "_evaluate", capture)
    runner = AnalysisRunner(sessions, RunnerSettings(chunk_ms=HUGE, registry=RuleRegistry([rule])))
    backend = SettingsBackend(sessions, runner, clock=lambda: NOW)
    initial = backend.settings()
    saved = backend.put_settings(
        SettingsIn(
            revision=initial.revision,
            values=initial.values.model_copy(
                update={"short_cycle_min": 4, "demand_after_stop_s": 60, "min_short_cycles": 2}
            ),
        )
    )
    assert saved.recompute_started
    runs = runner.tick(END + 300_000)
    assert runs
    assert all(run.status.value == "succeeded" for run in runs)
    assert seen == [4]
    with sessions() as session:
        row = session.scalar(select(AnalysisRun).where(AnalysisRun.status == "succeeded"))
        assert row is not None
        assert row.settings_revision_id is not None
        assert row.stats["settings"]["short_cycle_min"] == 4
        first_hash = row.config_hash
        revision = session.get(SettingsRevision, row.settings_revision_id)
        assert revision is not None
        assert revision.values["short_cycle_min"] == 4
        snapshots = list(session.scalars(select(RecommendationSnapshot)))
        assert snapshots
        assert snapshots[0].settings["short_cycle_min"] == 4
        assert snapshots[0].rule_params["short_cycle_min"] == 4
    backend.put_settings(
        SettingsIn(
            revision=saved.revision, values=saved.values.model_copy(update={"short_cycle_min": 5})
        )
    )
    second = runner.tick(END + 300_000)
    assert second
    assert second[-1].config_hash != first_hash
    assert seen[-1] == 5
    with sessions() as session:
        snapshots = list(
            session.scalars(select(RecommendationSnapshot).order_by(RecommendationSnapshot.id))
        )
        assert snapshots[0].rule_params["short_cycle_min"] == 4
        assert snapshots[-1].rule_params["short_cycle_min"] == 5
        assert snapshots[0].settings_revision_id != snapshots[-1].settings_revision_id


def test_concurrent_saves_only_accept_one_revision(sessions: sessionmaker[Session]) -> None:
    backend = SettingsBackend(sessions, clock=lambda: NOW)
    initial = backend.settings()
    barrier = Barrier(2)

    def save(value: float) -> int:
        barrier.wait(timeout=5)
        try:
            backend.put_settings(
                SettingsIn(
                    revision=initial.revision,
                    values=initial.values.model_copy(update={"short_cycle_min": value}),
                )
            )
            return 200
        except ProblemError as error:
            return error.problem.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, (4, 5)))
    assert sorted(results) == [200, 409]
    assert len(backend.settings_history().items) == 1


async def test_settings_routes_validate_and_expose_registered_schema(
    sessions: sessionmaker[Session],
) -> None:
    backend = SettingsBackend(sessions, clock=lambda: NOW)
    app = create_app(Settings.model_validate({}))
    app.dependency_overrides[get_settings_backend] = lambda: backend
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = (await client.get("/api/settings")).json()
        assert "kort-branden" in first["json_schema"]["x-rule-schemas"]
        invalid = await client.put(
            "/api/settings",
            json={
                "revision": first["revision"],
                "values": {"repetition_days": 10, "repetition_window_days": 3},
            },
        )
        assert invalid.status_code == 422
        valid = await client.put(
            "/api/settings",
            json={
                "revision": first["revision"],
                "values": {"gas_price_eur_per_m3": 1.5},
                "changed_by": "Jan",
            },
        )
        assert valid.status_code == 200, valid.text
        assert valid.json()["values"]["gas_price_eur_per_m3"] == 1.5
        history = (await client.get("/api/settings/history")).json()
        assert history["items"][0]["changed_by"] == "Jan"
