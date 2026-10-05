"""Analysis runner over a real (temporary) database (#27, FR-06, ADR-002 §4)."""

from __future__ import annotations

import random
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from cvidee.analysis.types import (
    HOUR_MS,
    MINUTE_MS,
    ConnectionEvent,
    ConnectionSource,
    Role,
)
from cvidee.runner.service import AnalysisRunner, RunnerSettings
from cvidee.runner.sources import SourceSettings, gateway_events
from cvidee.store.derived import SqlDerivedDataRepository
from cvidee.store.engine import create_db_engine, create_session_factory, database_url
from cvidee.store.enums import ObservationKind, ObservationOrigin, RunStatus, ValueKind
from cvidee.store.models import (
    AnalysisRun,
    BurnerCycle,
    SignalDefinition,
    SignalMapping,
    SourceEntity,
)
from cvidee.store.observations import SqlObservationRepository
from cvidee.store.records import ObservationRecord
from cvidee.store.schema import upgrade_to_head

T0 = 1_791_100_800_000  # whole UTC hour
FLAME = "binary_sensor.remeha_flame"
DEMAND = "binary_sensor.remeha_heat_demand"
GATEWAY = "binary_sensor.can_gateway"
SPAN = 14 * HOUR_MS
END = T0 + SPAN
HUGE = 10 * 365 * 24 * HOUR_MS


def _rec(entity: str, ts: int, on: bool, kind: ObservationKind) -> ObservationRecord:
    return ObservationRecord(
        entity_id=entity,
        ts=ts,
        state="on" if on else "off",
        value_num=1.0 if on else 0.0,
        kind=kind,
        origin=ObservationOrigin.LIVE,
        received_at_ts=ts + 100,
        last_reported_ts=None,
    )


def make_db(tmp_path: Path, name: str = "db") -> sessionmaker[Session]:
    url = database_url(tmp_path / f"{name}.sqlite")
    upgrade_to_head(url)
    return create_session_factory(create_db_engine(url))


def seed(factory: sessionmaker[Session], *, seed_value: int = 1) -> None:
    """Synthetic flame/demand stream with a short WS outage; mappings for both roles."""
    rng = random.Random(seed_value)
    records: list[ObservationRecord] = [
        _rec(FLAME, T0, False, ObservationKind.POLL),
        _rec(DEMAND, T0, False, ObservationKind.POLL),
    ]
    t = T0
    while t < END - 30 * MINUTE_MS:
        t += rng.randint(2, 25) * MINUTE_MS
        records.append(_rec(DEMAND, t, True, ObservationKind.CHANGE))
        flame_on = t + rng.randint(10, 120) * 1000
        records.append(_rec(FLAME, flame_on, True, ObservationKind.CHANGE))
        flame_off = flame_on + rng.randint(2, 20) * MINUTE_MS
        records.append(_rec(FLAME, flame_off, False, ObservationKind.CHANGE))
        t = flame_off + rng.randint(1, 3) * MINUTE_MS
        records.append(_rec(DEMAND, t, False, ObservationKind.CHANGE))
    with factory.begin() as session:
        repo = SqlObservationRepository(session)
        repo.add_observations(records)
        repo.add_connection_events(
            [
                ConnectionEvent(T0, ConnectionSource.WS, up=True),
                ConnectionEvent(T0 + 5 * HOUR_MS, ConnectionSource.WS, up=False),
                ConnectionEvent(T0 + 5 * HOUR_MS + 20 * MINUTE_MS, ConnectionSource.WS, up=True),
            ]
        )
        for role in (Role.FLAME, Role.HEAT_DEMAND):
            session.add(
                SignalDefinition(
                    role=role.value,
                    value_type="boolean",
                    scope_type="boiler",
                    default_kind=ValueKind.REPORTED,
                    default_max_age_ms=HOUR_MS,
                    required_for=[],
                    catalogue_version="test",
                )
            )
        session.flush()
        for role, entity in ((Role.FLAME, FLAME), (Role.HEAT_DEMAND, DEMAND)):
            ent = session.scalars(
                select(SourceEntity).where(SourceEntity.entity_id == entity)
            ).one()
            session.add(
                SignalMapping(
                    role=role.value,
                    scope_key="",
                    source_entity_id=ent.id,
                    kind=ValueKind.REPORTED,
                    heartbeat_expected=False,
                    max_age_ms=HOUR_MS,
                    valid_from_ts=T0 - HOUR_MS,
                    created_at_ts=T0,
                )
            )


def derived(factory: sessionmaker[Session]) -> tuple[object, ...]:
    with factory() as session:
        repo = SqlDerivedDataRepository(session)
        lo, hi = 0, END + 10 * HOUR_MS
        return (
            repo.burner_cycles(lo, hi),
            repo.mode_segments(lo, hi),
            repo.quality_events(lo, hi),
        )


def settle_of(runner: AnalysisRunner) -> int:
    return runner._settings_config().settle_ms


@pytest.fixture
def factory(tmp_path: Path) -> sessionmaker[Session]:
    f = make_db(tmp_path)
    seed(f)
    return f


@pytest.fixture
def reference(tmp_path: Path) -> tuple[object, ...]:
    f = make_db(tmp_path, "ref")
    seed(f)
    runner = AnalysisRunner(f, RunnerSettings(chunk_ms=HUGE))
    runs = runner.run_range(T0, END)
    assert [r.status for r in runs] == [RunStatus.SUCCEEDED]
    out = derived(f)
    assert out[0], "synthetic stream must produce cycles"
    return out


@pytest.mark.parametrize("chunk_ms", [HOUR_MS, 3 * HOUR_MS + 7 * MINUTE_MS, 24 * HOUR_MS])
def test_chunked_ticks_equal_whole_range(
    factory: sessionmaker[Session], reference: tuple[object, ...], chunk_ms: int
) -> None:
    runner = AnalysisRunner(factory, RunnerSettings(chunk_ms=chunk_ms))
    settle = settle_of(runner)
    for hour in range(1, 15):
        runner.tick(T0 + hour * HOUR_MS + settle)
    runner.tick(END + settle)
    assert derived(factory) == reference


def test_crash_rolls_back_and_next_run_recovers(
    factory: sessionmaker[Session], reference: tuple[object, ...]
) -> None:
    calls = {"n": 0}

    def boom(session: Session, result: object, run: AnalysisRun) -> None:
        calls["n"] += 1
        if calls["n"] == 2:  # after replace_from deleted and inserted
            raise RuntimeError("crash mid-run")

    runner = AnalysisRunner(factory, RunnerSettings(chunk_ms=4 * HOUR_MS), after_run=[boom])
    settle = settle_of(runner)
    runs = runner.tick(END + settle)
    assert [r.status for r in runs] == [RunStatus.SUCCEEDED, RunStatus.FAILED]
    with factory() as session:
        failed = session.scalars(
            select(AnalysisRun).where(AnalysisRun.status == RunStatus.FAILED)
        ).one()
        assert failed.errors
        before = session.scalar(select(func.count()).select_from(BurnerCycle))
    # Only the first chunk's rows exist: the failed run was rolled back entirely.
    assert before is not None
    assert before < len(reference[0])  # type: ignore[arg-type]
    runner.tick(END + settle)
    assert derived(factory) == reference


def test_request_recompute_reemits_range(
    factory: sessionmaker[Session], reference: tuple[object, ...]
) -> None:
    runner = AnalysisRunner(factory, RunnerSettings(chunk_ms=6 * HOUR_MS))
    settle = settle_of(runner)
    runner.tick(END + settle)
    assert derived(factory) == reference
    with factory.begin() as session:  # damage derived rows inside the range
        session.execute(delete(BurnerCycle).where(BurnerCycle.start_ts >= T0 + 4 * HOUR_MS))
    queued = runner.request_recompute(T0 + 4 * HOUR_MS, T0 + 8 * HOUR_MS)
    assert queued.status is RunStatus.QUEUED
    runs = runner.tick(END + settle)
    assert runs
    assert all(r.status is RunStatus.SUCCEEDED for r in runs)
    assert derived(factory) == reference
    with factory() as session:
        done = session.get(AnalysisRun, queued.id)
        assert done is not None
        assert done.status is not RunStatus.QUEUED
    runner.tick(END + settle)  # idempotent: re-running changes nothing
    assert derived(factory) == reference


def test_gateway_observations_become_can_gateway_events(
    factory: sessionmaker[Session],
) -> None:
    with factory.begin() as session:
        SqlObservationRepository(session).add_observations(
            [
                _rec(GATEWAY, T0, True, ObservationKind.POLL),
                ObservationRecord(
                    entity_id=GATEWAY,
                    ts=T0 + HOUR_MS,
                    state="unavailable",
                    value_num=None,
                    kind=ObservationKind.CHANGE,
                    origin=ObservationOrigin.LIVE,
                    received_at_ts=T0 + HOUR_MS + 1,
                    last_reported_ts=None,
                ),
                _rec(GATEWAY, T0 + 2 * HOUR_MS, True, ObservationKind.CHANGE),
            ]
        )
    with factory() as session:
        events = gateway_events(SqlObservationRepository(session), GATEWAY, T0, END)
    assert events == [
        ConnectionEvent(T0, ConnectionSource.CAN_GATEWAY, up=True),
        ConnectionEvent(T0 + HOUR_MS, ConnectionSource.CAN_GATEWAY, up=False),
        ConnectionEvent(T0 + 2 * HOUR_MS, ConnectionSource.CAN_GATEWAY, up=True),
    ]
    runner = AnalysisRunner(
        factory, RunnerSettings(sources=SourceSettings(can_gateway_entity_id=GATEWAY))
    )
    runs = runner.tick(END + settle_of(runner))
    assert runs
    assert all(r.status is RunStatus.SUCCEEDED for r in runs)
    assert (runs[-1].stats or {})["connection_events"] >= 3
