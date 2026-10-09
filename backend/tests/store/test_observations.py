"""Observation store: dedupe, classification, range queries, retention (#16)."""

import random
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from cvidee.analysis.types import (
    HOUR_MS,
    ConnectionEvent,
    ConnectionSource,
    QualityEventKind,
    Role,
    SignalRef,
)
from cvidee.store.engine import create_db_engine, create_session_factory
from cvidee.store.enums import ObservationKind, ObservationOrigin
from cvidee.store.models import Base, QualityEvent, SourceEntity
from cvidee.store.observations import (
    DAY_MS,
    SqlObservationRepository,
    classify,
    duplicate_quality_events,
    merge_duplicate_counts,
    resolve_retention_days,
    retention_cutoff_ts,
    run_retention,
    to_analysis_observation,
)
from cvidee.store.records import DuplicateCount, ObservationRecord
from cvidee.store.schema import upgrade_to_head

T0 = 1_791_100_800_000  # 2026-10-04T08:00:00Z, a whole UTC hour
FLAME = "binary_sensor.remeha_flame"
FLOW = "sensor.remeha_flow_temperature"

CHANGE = ObservationKind.CHANGE
CONFIRM = ObservationKind.CONFIRM
POLL = ObservationKind.POLL
LIVE = ObservationOrigin.LIVE
IMPORT = ObservationOrigin.IMPORT


def rec(
    ts: int,
    state: str,
    kind: ObservationKind = CHANGE,
    *,
    entity: str = FLAME,
    origin: ObservationOrigin = LIVE,
    received: int | None = None,
    last_reported: int | None = None,
) -> ObservationRecord:
    value_num = {"on": 1.0, "off": 0.0}.get(state)
    if value_num is None and state.replace(".", "", 1).isdigit():
        value_num = float(state)
    return ObservationRecord(
        entity_id=entity,
        ts=ts,
        state=state,
        value_num=value_num,
        kind=kind,
        origin=origin,
        received_at_ts=ts + 100 if received is None else received,
        last_reported_ts=last_reported,
    )


@contextmanager
def memory_session() -> Iterator[Session]:
    """Fresh in-memory database (schema from the models; parity is tested in test_schema)."""
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as s:
            yield s
    finally:
        engine.dispose()


@pytest.fixture
def session() -> Iterator[Session]:
    with memory_session() as s:
        yield s


@pytest.fixture
def repo(session: Session) -> SqlObservationRepository:
    return SqlObservationRepository(session)


def snapshot(session: Session) -> list[tuple[Any, ...]]:
    from cvidee.store.models import Observation

    stmt = (
        select(
            SourceEntity.entity_id,
            Observation.ts,
            Observation.state,
            Observation.value_num,
            Observation.kind,
            Observation.reported_kind,
            Observation.origin,
            Observation.received_at_ts,
            Observation.last_reported_ts,
        )
        .join(SourceEntity, SourceEntity.id == Observation.source_entity_id)
        .order_by(SourceEntity.entity_id, Observation.ts, Observation.state)
    )
    return [tuple(r) for r in session.execute(stmt)]


def kinds(repo: SqlObservationRepository, entity: str = FLAME) -> list[tuple[int, str, str]]:
    return [(r.ts - T0, r.state, r.kind.value) for r in repo.observations(entity, 0, 2**62)]


# ----------------------------------------------------------------------- insert / dedupe


def test_insert_and_range_query_sorted(repo: SqlObservationRepository) -> None:
    result = repo.add_observations(
        [rec(T0 + 30, "off"), rec(T0 + 10, "on"), rec(T0 + 20, "21.5", entity=FLOW)]
    )
    assert (result.inserted, result.duplicates_skipped, result.duplicates) == (3, 0, ())
    assert [r.ts for r in repo.observations(FLAME, T0, T0 + 31)] == [T0 + 10, T0 + 30]
    assert [r.ts for r in repo.observations(FLAME, T0 + 10, T0 + 30)] == [T0 + 10]  # half-open
    assert repo.observations(FLOW, T0, T0 + 100)[0].value_num == 21.5
    assert repo.observations("sensor.unknown", T0, T0 + 100) == []


def test_source_entity_created_and_seen_range_extended(
    repo: SqlObservationRepository, session: Session
) -> None:
    repo.add_observations([rec(T0 + 10, "on")])
    repo.add_observations([rec(T0 + 5, "off"), rec(T0 + 50, "off")])
    entity = session.scalars(select(SourceEntity)).one()
    assert (entity.entity_id, entity.first_seen_ts, entity.last_seen_ts) == (
        FLAME,
        T0 + 5,
        T0 + 50,
    )


def test_duplicates_skipped_and_counted_per_hour(repo: SqlObservationRepository) -> None:
    first = repo.add_observations([rec(T0 + 10, "on"), rec(T0 + 10, "on")])
    assert (first.inserted, first.duplicates_skipped) == (1, 1)
    second = repo.add_observations(
        [rec(T0 + 10, "on"), rec(T0 + HOUR_MS + 1, "off"), rec(T0 + HOUR_MS + 1, "off")]
    )
    assert (second.inserted, second.duplicates_skipped) == (1, 2)
    assert second.duplicates == (
        DuplicateCount(FLAME, T0, 1),
        DuplicateCount(FLAME, T0 + HOUR_MS, 1),
    )
    assert len(repo.observations(FLAME, T0, T0 + 2 * HOUR_MS)) == 2


def test_same_ts_different_state_is_not_a_duplicate(repo: SqlObservationRepository) -> None:
    result = repo.add_observations([rec(T0, "on"), rec(T0, "off")])
    assert result.inserted == 2


def test_adr003_t13_duplicates_keep_one_change(repo: SqlObservationRepository) -> None:
    result = repo.add_observations([rec(T0, "off"), rec(T0, "off"), rec(T0, "off", POLL)])
    assert (result.inserted, result.duplicates_skipped) == (1, 2)
    assert kinds(repo) == [(0, "off", "change")]


def test_duplicate_merge_keeps_strongest_evidence(repo: SqlObservationRepository) -> None:
    repo.add_observations(
        [rec(T0, "on", POLL, origin=IMPORT, received=T0 + 900, last_reported=T0 + 50)]
    )
    repo.add_observations([rec(T0, "on", CHANGE, received=T0 + 200, last_reported=None)])
    (stored,) = repo.observations(FLAME, T0, T0 + 1)
    assert stored.kind is CHANGE
    assert stored.origin is LIVE
    assert stored.received_at_ts == T0 + 200
    assert stored.last_reported_ts == T0 + 50


# ------------------------------------------------------------------------ classification


def test_classify() -> None:
    assert classify(CHANGE, "on", "on") is CONFIRM
    assert classify(CHANGE, "on", "off") is CHANGE
    assert classify(CHANGE, "on", None) is CHANGE
    assert classify(POLL, "on", "off") is POLL  # never promoted to a transition
    assert classify(CONFIRM, "on", "off") is CONFIRM


def test_repeated_value_is_confirm_not_change(repo: SqlObservationRepository) -> None:
    repo.add_observations([rec(T0, "off"), rec(T0 + 10, "on"), rec(T0 + 20, "on")])
    repo.add_observations([rec(T0 + 30, "on"), rec(T0 + 40, "off"), rec(T0 + 50, "off", POLL)])
    assert kinds(repo) == [
        (0, "off", "change"),
        (10, "on", "change"),
        (20, "on", "confirm"),
        (30, "on", "confirm"),
        (40, "off", "change"),
        (50, "off", "poll"),
    ]


def test_late_data_reclassifies_successor(repo: SqlObservationRepository) -> None:
    repo.add_observations([rec(T0, "off"), rec(T0 + 30, "on")])
    repo.add_observations([rec(T0 + 20, "on")])  # late: t+30 now repeats t+20
    assert kinds(repo) == [(0, "off", "change"), (20, "on", "change"), (30, "on", "confirm")]
    repo.add_observations([rec(T0 + 25, "off")])  # late again: t+30 is a transition again
    assert kinds(repo) == [
        (0, "off", "change"),
        (20, "on", "change"),
        (25, "off", "change"),
        (30, "on", "change"),
    ]


def test_classification_is_per_entity(repo: SqlObservationRepository) -> None:
    repo.add_observations([rec(T0, "on"), rec(T0 + 10, "on", entity=FLOW)])
    assert kinds(repo, FLOW) == [(10, "on", "change")]


# ---------------------------------------------------------------- range query / carry-in


def test_last_before_and_carry_in(repo: SqlObservationRepository) -> None:
    repo.add_observations([rec(T0, "on"), rec(T0 + 10, "off"), rec(T0 + 20, "on")])
    seed = repo.last_before(FLAME, T0 + 20)
    assert seed is not None
    assert (seed.ts, seed.state) == (T0 + 10, "off")
    assert repo.last_before(FLAME, T0) is None
    window = repo.observations(FLAME, T0 + 15, T0 + 30, with_carry_in=True)
    assert [(r.ts, r.state) for r in window] == [(T0 + 10, "off"), (T0 + 20, "on")]
    assert repo.observations(FLAME, T0, T0 + 5, with_carry_in=True)[0].ts == T0


# ------------------------------------------------------------------- connection events


def test_connection_events_dedupe_and_range(repo: SqlObservationRepository) -> None:
    ws = ConnectionSource.WS
    can = ConnectionSource.CAN_GATEWAY
    events = [
        ConnectionEvent(T0 + 20, ws, True),
        ConnectionEvent(T0 + 10, ws, False),
        ConnectionEvent(T0 + 10, ws, False),
        ConnectionEvent(T0 + 5, can, False),
    ]
    first = repo.add_connection_events(events)
    assert (first.inserted, first.duplicates_skipped) == (3, 1)
    again = repo.add_connection_events(events)
    assert (again.inserted, again.duplicates_skipped) == (0, 4)
    assert repo.connection_events(T0, T0 + 30) == [
        ConnectionEvent(T0 + 5, can, False),
        ConnectionEvent(T0 + 10, ws, False),
        ConnectionEvent(T0 + 20, ws, True),
    ]
    assert repo.connection_events(T0 + 15, T0 + 30, with_carry_in=True) == [
        ConnectionEvent(T0 + 5, can, False),
        ConnectionEvent(T0 + 10, ws, False),
        ConnectionEvent(T0 + 20, ws, True),
    ]
    assert repo.connection_events(T0 + 15, T0 + 20) == []


# ------------------------------------------------------------------------- quality events


def test_duplicate_quality_events() -> None:
    boiler_flame = SignalRef(Role.FLAME)
    counts = merge_duplicate_counts(
        [DuplicateCount(FLAME, T0, 2), DuplicateCount("sensor.unmapped", T0, 5)],
        [DuplicateCount(FLAME, T0, 3), DuplicateCount(FLAME, T0 + HOUR_MS, 1)],
    )
    events = duplicate_quality_events(
        counts, lambda entity, _ts: boiler_flame if entity == FLAME else None
    )
    assert [(e.kind, e.signal, e.start, e.end, e.count, e.final) for e in events] == [
        (QualityEventKind.DUPLICATE, boiler_flame, T0, T0 + HOUR_MS, 5, True),
        (QualityEventKind.DUPLICATE, boiler_flame, T0 + HOUR_MS, T0 + 2 * HOUR_MS, 1, True),
    ]


# ----------------------------------------------------------------------- analysis mapping


def test_to_analysis_observation() -> None:
    flame = SignalRef(Role.FLAME)
    flow = SignalRef(Role.FLOW_TEMPERATURE)
    assert to_analysis_observation(rec(T0, "on"), flame).value is True
    assert to_analysis_observation(rec(T0, "off"), flame).value is False
    assert to_analysis_observation(rec(T0, "unavailable"), flame).value is None
    assert to_analysis_observation(rec(T0, "unknown"), flame).value is None
    assert to_analysis_observation(rec(T0, "55.5"), flow).value == 55.5
    assert to_analysis_observation(rec(T0, "burning"), flame).value == "burning"
    mapped = to_analysis_observation(rec(T0, "burning"), flame, {"burning": True})
    assert mapped.value is True
    obs = to_analysis_observation(rec(T0, "on", CONFIRM, last_reported=T0 + 9), flame)
    assert (obs.signal, obs.ts, obs.kind, obs.last_reported) == (flame, T0, CONFIRM, T0 + 9)
    assert to_analysis_observation(rec(T0, "on", last_reported=T0 - 1), flame).last_reported is None
    poll = rec(T0, "on", POLL, last_reported=T0 - 500)  # ADR-003 §4.3: older evidence
    assert to_analysis_observation(poll, flame).last_reported == T0 - 500


# ----------------------------------------------------------------------------- retention


def test_resolve_retention_days() -> None:
    assert resolve_retention_days(None, 180) == 180
    assert resolve_retention_days({}, 180) == 180
    assert resolve_retention_days({"retention.raw_days": 90}, 180) == 90
    assert resolve_retention_days({"retention_days": 90}, 180) == 90
    assert resolve_retention_days({"retention.raw_days": 10}, 180) == 180
    assert resolve_retention_days({"retention.raw_days": "90"}, 180) == 180
    assert resolve_retention_days({"retention.raw_days": True}, 180) == 180
    assert retention_cutoff_ts(T0, 2) == T0 - 2 * DAY_MS
    with pytest.raises(ValueError, match="at least 1"):
        retention_cutoff_ts(T0, 0)


def test_retention_deletes_raw_data_only(repo: SqlObservationRepository, session: Session) -> None:
    now = T0 + 200 * DAY_MS
    repo.add_observations([rec(T0, "on"), rec(now - DAY_MS, "off")])
    repo.add_connection_events(
        [
            ConnectionEvent(T0, ConnectionSource.WS, False),
            ConnectionEvent(now, ConnectionSource.WS, True),
        ]
    )
    session.add(
        QualityEvent(
            kind=QualityEventKind.DATA_GAP,
            signal="",
            start_ts=T0,
            end_ts=T0 + HOUR_MS,
            detail="",
            final=True,
        )
    )
    session.flush()
    result = run_retention(repo, now, 180)
    assert (result.cutoff_ts, result.observations, result.connection_events) == (
        now - 180 * DAY_MS,
        1,
        1,
    )
    assert [r.ts for r in repo.observations(FLAME, 0, 2**62)] == [now - DAY_MS]
    assert repo.connection_events(0, 2**62) == [ConnectionEvent(now, ConnectionSource.WS, True)]
    assert session.scalars(select(QualityEvent)).one().start_ts == T0  # derived data kept
    assert repo.purge_before(now) == 1


# ------------------------------------------------------------------------ property tests

_records = st.lists(
    st.builds(
        rec,
        ts=st.integers(0, 12).map(lambda i: T0 + i * 1000),
        state=st.sampled_from(["on", "off", "unavailable"]),
        kind=st.sampled_from(list(ObservationKind)),
        entity=st.sampled_from([FLAME, FLOW]),
        origin=st.sampled_from(list(ObservationOrigin)),
        received=st.integers(0, 3).map(lambda i: T0 + 50_000 + i),
        last_reported=st.none() | st.integers(0, 3).map(lambda i: T0 + 13_000 + i),
    ),
    max_size=40,
)


def _stored_after(*batches: list[ObservationRecord]) -> list[tuple[Any, ...]]:
    with memory_session() as session:
        repo = SqlObservationRepository(session)
        for batch in batches:
            repo.add_observations(batch)
        session.flush()
        return snapshot(session)


@settings(max_examples=150, deadline=None)
@given(records=_records)
def test_inserting_same_batch_twice_changes_nothing(records: list[ObservationRecord]) -> None:
    with memory_session() as session:
        repo = SqlObservationRepository(session)
        first = repo.add_observations(records)
        before = snapshot(session)
        second = repo.add_observations(records)
        assert snapshot(session) == before
    assert second.inserted == 0
    assert second.duplicates_skipped == len(records)
    assert first.inserted + first.duplicates_skipped == len(records)
    assert first.inserted == len({(r.entity_id, r.ts, r.state) for r in records})


@settings(max_examples=150, deadline=None)
@given(records=_records, seed=st.integers())
def test_shuffled_batch_gives_same_result(records: list[ObservationRecord], seed: int) -> None:
    shuffled = list(records)
    random.Random(seed).shuffle(shuffled)
    assert _stored_after(shuffled) == _stored_after(records)


@settings(max_examples=150, deadline=None)
@given(records=_records, data=st.data())
def test_split_batches_in_any_order_give_same_result(
    records: list[ObservationRecord], data: st.DataObject
) -> None:
    """Late data: arrival order over batches does not change the stored result."""
    cut = data.draw(st.integers(0, len(records)))
    a, b = records[:cut], records[cut:]
    whole = _stored_after(records)
    assert _stored_after(a, b) == whole
    assert _stored_after(b, a) == whole


@settings(max_examples=100, deadline=None)
@given(records=_records)
def test_no_repeated_state_is_stored_as_change(records: list[ObservationRecord]) -> None:
    rows = _stored_after(records)
    previous: dict[str, str] = {}
    for entity, _ts, state, _num, kind, *_ in rows:
        if previous.get(entity) == state:
            assert kind is not CHANGE
        previous[entity] = state


# ---------------------------------------------------------------------------- benchmark

BENCH_ENTITIES = 10
BENCH_ROWS_PER_ENTITY = 100_000  # 1 million rows in total
BENCH_STEP_MS = 10_000


@pytest.mark.slow
def test_range_query_on_one_million_rows_is_fast(tmp_path: Path) -> None:
    import time

    url = f"sqlite:///{tmp_path / 'bench.sqlite3'}"
    upgrade_to_head(url)
    engine = create_db_engine(url)
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.executemany(
            "INSERT INTO source_entities (id, entity_id, first_seen_ts, last_seen_ts) "
            "VALUES (?, ?, ?, ?)",
            [(i + 1, f"sensor.bench_{i}", T0, T0) for i in range(BENCH_ENTITIES)],
        )
        rows = (
            (
                e + 1,
                T0 + i * BENCH_STEP_MS,
                f"{40 + (i % 200) / 10:.1f}",
                40 + (i % 200) / 10,
                "change",
                "change",
                "live",
                T0 + i * BENCH_STEP_MS,
            )
            for e in range(BENCH_ENTITIES)
            for i in range(BENCH_ROWS_PER_ENTITY)
        )
        cur.executemany(
            "INSERT INTO observations (source_entity_id, ts, state, value_num, kind, "
            "reported_kind, origin, received_at_ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            list(rows),
        )
        raw.commit()
        cur.execute("ANALYZE")
        cur.execute("SELECT count(*) FROM observations")
        count = cur.fetchone()
        assert count is not None
        assert count[0] == BENCH_ENTITIES * BENCH_ROWS_PER_ENTITY
    finally:
        raw.close()

    with create_session_factory(engine)() as session:
        repo = SqlObservationRepository(session)
        timings: list[float] = []
        for day in range(5):
            start = T0 + day * DAY_MS
            t = time.perf_counter()
            window = repo.observations("sensor.bench_3", start, start + DAY_MS, with_carry_in=True)
            timings.append(time.perf_counter() - t)
            assert len(window) == DAY_MS // BENCH_STEP_MS + (1 if day else 0)
    engine.dispose()
    timings.sort()
    median_ms = timings[len(timings) // 2] * 1000
    print(f"\nrange query (1 entity, 1 day = 8640 rows, 1M rows total): median {median_ms:.1f} ms")
    assert median_ms < 200
