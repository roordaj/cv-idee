"""Installation profile (#20, FR-02/03) and special periods (#21, FR-10) over a real database."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cvidee.analysis.types import HOUR_MS, TimeRange
from cvidee.config import Settings
from cvidee.installation import (
    SqlInstallationProfileRepository,
    boiler_dt_representative,
    circuit_is_mixed,
    default_profile,
    known,
    modulation_to_kw,
    profile_facts,
)
from cvidee.main import create_app
from cvidee.periods import (
    ExclusionPurpose,
    SqlSpecialPeriodRepository,
    excluded_intervals,
    rule_periods,
)
from cvidee.runner.service import AnalysisRunner
from cvidee.store.engine import create_db_engine, create_session_factory, database_url
from cvidee.store.enums import CircuitKind, RunStatus, SpecialPeriodKind, SpecStatus
from cvidee.store.models import AnalysisRun, SpecialPeriod
from cvidee.store.schema import upgrade_to_head

T0 = 1_791_100_800_000


@pytest.fixture
def factory(tmp_path: Path) -> sessionmaker[Session]:
    url = database_url(tmp_path / "db.sqlite")
    upgrade_to_head(url)
    return create_session_factory(create_db_engine(url))


@pytest.fixture
def session(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory() as s:
        yield s


def _period(start: int, end: int | None, **flags: bool) -> SpecialPeriod:
    return SpecialPeriod(
        kind=SpecialPeriodKind.COMMISSIONING,
        start_ts=start,
        end_ts=end,
        exclude_from_baseline=flags.get("baseline", True),
        exclude_from_comparisons=flags.get("comparisons", True),
        exclude_from_ch_conclusions=flags.get("ch", True),
        created_at_ts=0,
        updated_at_ts=0,
    )


# --------------------------------------------------------------------- profile


def test_default_profile_is_the_starting_situation(session: Session) -> None:
    repo = SqlInstallationProfileRepository(session)
    profile = repo.current_or_default(T0)
    facts = profile_facts(profile)
    kinds = {c.key: c.kind for c in facts.circuits}
    assert kinds == {"beneden": CircuitKind.DIRECT, "boven": CircuitKind.MIXING_MANIFOLD}
    assert profile.details["circuits"]["boven"]["loops"] == 5
    assert circuit_is_mixed(facts, "slaapkamer")
    assert not circuit_is_mixed(facts, "woonkamer")
    assert not circuit_is_mixed(facts, "onbekend")
    assert boiler_dt_representative(facts, "beneden")
    assert not boiler_dt_representative(facts, "boven")
    assert not boiler_dt_representative(facts, "nope")


def test_unknown_stays_unknown_and_no_kw_without_conversion(session: Session) -> None:
    facts = profile_facts(SqlInstallationProfileRepository(session).current_or_default(T0))
    assert facts.boiler.max_flow_c is None
    assert facts.boiler.min_power_kw is None
    assert not known(facts, "max_ch_flow_temperature")
    assert facts.modulation_kw_per_pct is None
    assert modulation_to_kw(facts, 50.0) is None
    assert all(s.status is SpecStatus.UNKNOWN for s in default_profile(T0).specs)


def test_versioning_is_copy_on_edit(session: Session) -> None:
    repo = SqlInstallationProfileRepository(session)
    v1_id = repo.current_or_default(T0).id
    v2 = default_profile(T0 + HOUR_MS)
    v2.valid_from_ts = T0 + HOUR_MS
    repo.save_new_version(v2)
    session.commit()
    current, old, at_edit = repo.current(), repo.at(T0), repo.at(T0 + HOUR_MS)
    assert current is not None
    assert old is not None
    assert at_edit is not None
    assert current.id == v2.id == at_edit.id
    assert old.id == v1_id
    assert old.valid_to_ts == T0 + HOUR_MS


# --------------------------------------------------------------------- periods


def test_excluded_intervals_semantics() -> None:
    rng = TimeRange(T0, T0 + 10 * HOUR_MS)
    periods = [
        _period(T0 - HOUR_MS, T0 + HOUR_MS),  # clipped at start
        _period(T0 + HOUR_MS, T0 + 2 * HOUR_MS),  # touches: merged
        _period(T0 + 5 * HOUR_MS, None),  # still running: until range end
        _period(T0 - 5 * HOUR_MS, T0),  # ends exactly at start: not included
        _period(T0 + 3 * HOUR_MS, T0 + 4 * HOUR_MS, baseline=False, comparisons=False),
    ]
    normal = excluded_intervals(periods, rng, ExclusionPurpose.NORMAL_BEHAVIOUR)
    assert normal == (
        TimeRange(T0, T0 + 2 * HOUR_MS),
        TimeRange(T0 + 5 * HOUR_MS, T0 + 10 * HOUR_MS),
    )
    inside = TimeRange(T0 + 3 * HOUR_MS, T0 + 4 * HOUR_MS)
    assert inside in excluded_intervals(periods, rng, ExclusionPurpose.OPTIMISATION)
    assert inside not in excluded_intervals(periods, rng, ExclusionPurpose.COMPARISONS)


def test_period_only_excluded_from_chosen_purposes(session: Session) -> None:
    repo = SqlSpecialPeriodRepository(session)
    repo.add(_period(T0, T0 + 4 * HOUR_MS, baseline=False, comparisons=False, ch=True))
    rng = TimeRange(T0, T0 + 8 * HOUR_MS)
    assert repo.excluded_intervals(rng, ExclusionPurpose.NORMAL_BEHAVIOUR) == ()
    assert repo.excluded_intervals(rng, ExclusionPurpose.OPTIMISATION) == (
        TimeRange(T0, T0 + 4 * HOUR_MS),
    )
    seen = rule_periods(session, rng)
    assert len(seen) == 1
    assert seen[0].excluded


# ------------------------------------------------------------------------- API


@pytest.fixture
async def api(factory: sessionmaker[Session]) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(Settings.model_validate({}))
    app.state.session_factory = factory
    app.state.runner = AnalysisRunner(factory)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


def _queued(factory: sessionmaker[Session]) -> list[AnalysisRun]:
    with factory() as s:
        return list(s.scalars(select(AnalysisRun).where(AnalysisRun.status == RunStatus.QUEUED)))


async def test_installation_round_trip_and_versioning(
    api: httpx.AsyncClient, factory: sessionmaker[Session]
) -> None:
    first = (await api.get("/api/installation")).json()
    first.pop("summary", None)
    first.pop("updated_at", None)
    assert {s["status"] for s in first["specifications"]} == {"unknown"}
    assert [c["loops"] for c in first["circuits"]] == [None, 5]

    # No-op save does not create a version or a recompute.
    same = await api.put("/api/installation", json=first)
    assert same.status_code == 200, same.text
    assert same.json()["revision"] == first["revision"]
    assert _queued(factory) == []

    edited: dict[str, Any] = {**first}
    edited["specifications"] = [
        {**s, "status": "known", "value": 60, "note": "ingesteld"}
        if s["key"] == "max_ch_flow_temperature"
        else s
        for s in first["specifications"]
    ]
    saved = (await api.put("/api/installation", json=edited)).json()
    assert saved["revision"] > first["revision"]
    spec = {s["key"]: s for s in saved["specifications"]}
    assert spec["max_ch_flow_temperature"]["value"] == 60
    assert spec["modulation_to_kw"]["status"] == "unknown"
    assert spec["modulation_to_kw"]["value"] is None
    assert len(_queued(factory)) == 1  # recompute requested

    assert (await api.get("/api/installation")).json()["revision"] == saved["revision"]
    conflict = await api.put("/api/installation", json=edited)
    assert conflict.status_code == 409


async def test_installation_rejects_values_for_unknown_specs(api: httpx.AsyncClient) -> None:
    first = (await api.get("/api/installation")).json()
    first.pop("summary", None)
    first.pop("updated_at", None)
    bad = {
        **first,
        "specifications": [
            {**s, "value": 12} if s["key"] == "max_ch_power" else s for s in first["specifications"]
        ],
    }
    assert (await api.put("/api/installation", json=bad)).status_code == 422
    kw = {
        **first,
        "specifications": [
            {**s, "status": "known", "value": "veel"} if s["key"] == "modulation_to_kw" else s
            for s in first["specifications"]
        ],
    }
    assert (await api.put("/api/installation", json=kw)).status_code == 422


async def test_periods_crud_and_recompute(
    api: httpx.AsyncClient, factory: sessionmaker[Session]
) -> None:
    body: dict[str, Any] = {
        "kind": "commissioning",
        "start": "2026-10-01T08:00:00Z",
        "end": "2026-10-03T08:00:00Z",
        "description": "Opstookprotocol",
        "excluded_from": {"normal_behaviour": True, "comparisons": True, "ch_conclusions": True},
    }
    created = await api.post("/api/periods", json=body)
    assert created.status_code == 201
    period = created.json()
    assert period["id"].startswith("P-")
    assert period["description"] == "Opstookprotocol"
    queued = _queued(factory)
    assert len(queued) == 1
    assert queued[0].emit_from_ts == 1_790_841_600_000

    updated = await api.put(
        f"/api/periods/{period['id']}",
        json={
            **body,
            "end": None,
            "excluded_from": {**body["excluded_from"], "comparisons": False},
        },
    )
    assert updated.status_code == 200
    assert updated.json()["end"] is None
    assert updated.json()["excluded_from"]["comparisons"] is False
    assert updated.json()["created_at"] == period["created_at"]

    listed = (await api.get("/api/periods")).json()["items"]
    assert [p["id"] for p in listed] == [period["id"]]

    assert (await api.post("/api/periods", json={**body, "end": body["start"]})).status_code == 422
    assert (await api.put("/api/periods/P-999", json=body)).status_code == 404
    assert (await api.delete(f"/api/periods/{period['id']}")).status_code == 204
    assert (await api.get("/api/periods")).json()["items"] == []
    assert (await api.delete(f"/api/periods/{period['id']}")).status_code == 404


@pytest.mark.parametrize(("baseline", "comparisons"), [(True, False), (False, True)])
def test_reference_exclusions_do_not_disable_cv_findings(
    session: Session, baseline: bool, comparisons: bool
) -> None:
    SqlSpecialPeriodRepository(session).add(
        _period(T0, T0 + HOUR_MS, baseline=baseline, comparisons=comparisons, ch=False)
    )
    seen = rule_periods(session, TimeRange(T0, T0 + 2 * HOUR_MS))
    assert len(seen) == 1
    assert not seen[0].excluded


async def test_installation_rejects_broken_circuit_links(api: httpx.AsyncClient) -> None:
    profile = (await api.get("/api/installation")).json()
    profile.pop("summary")
    profile.pop("updated_at")
    profile["circuits"][0]["rooms"].append("missing-room")
    response = await api.put("/api/installation", json=profile)
    assert response.status_code == 422
    assert (await api.get("/api/installation")).json()["revision"] == profile["revision"]


async def test_validated_conversion_and_old_profile_are_preserved(
    api: httpx.AsyncClient, factory: sessionmaker[Session]
) -> None:
    first = (await api.get("/api/installation")).json()
    body = {k: v for k, v in first.items() if k not in ("summary", "updated_at")}
    for spec in body["specifications"]:
        if spec["key"] == "modulation_to_kw":
            spec.update(status="known", value=0.2)
    response = await api.put("/api/installation", json=body)
    assert response.status_code == 200, response.text
    with factory() as session:
        repo = SqlInstallationProfileRepository(session)
        assert modulation_to_kw(profile_facts(repo.current()), 50) == 10
        assert modulation_to_kw(profile_facts(repo.get(first["revision"])), 50) is None


def test_migrated_profile_without_details_stays_readable(factory: sessionmaker[Session]) -> None:
    from cvidee.api.config_backend import ConfigBackend

    with factory.begin() as session:
        profile = SqlInstallationProfileRepository(session).current_or_default(T0)
        profile.details = {}
    result = ConfigBackend(factory).installation_profile()
    assert result.boiler.model == "Onbekend"
    assert all(spec.value is None for spec in result.specifications)
