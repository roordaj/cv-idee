"""SQL implementation of the raw-data store: observations and connection events (#16).

Semantics (ADR-001 §3/§7, ADR-002 §3.1, FR-06/FR-08):

* **Dedupe** on ``(entity, ts, state)`` (ADR-003 §4.2). A duplicate is merged into the
  stored row instead of being inserted: the strongest reported kind stays
  (``change > confirm > poll``), origin ``live > import``, earliest ``received_at_ts``,
  latest ``last_reported_ts``. The merge is commutative, so the stored result does not
  depend on the order in which (batches of) records arrive.
* **Classification**: a reported ``change`` whose state equals the previous stored state
  of the entity (order ``(ts, state)``) is stored as ``confirm``: an identical value
  repeated is never a transition. ``confirm`` and ``poll`` are kept as reported (a poll
  after reconnect is never promoted to a transition, scenario 5). When late data is
  inserted before stored rows, the immediate successor is reclassified as well; the
  original ``reported_kind`` is kept for that purpose.
* **Duplicate counts** are returned per entity and whole UTC hour in
  :class:`~cvidee.store.records.InsertResult`; :func:`duplicate_quality_events` turns
  them into ``QualityEvent(kind=DUPLICATE)`` values ("ontdubbeld") once the caller knows
  the role mapping. They are not written to ``quality_events`` here: that table is owned
  by the pipeline (ADR-001 §5, ADR-003 §8); ingest records the totals in ``import_jobs`` /
  ``analysis_runs.stats``.
* **Retention** deletes raw rows only (``observations``, ``connection_events``), never
  derived data.

The caller owns the transaction: nothing here commits.
"""

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import CursorResult, Table, bindparam, delete, insert, select, update
from sqlalchemy.orm import Session

from cvidee.analysis.types import (
    HOUR_MS,
    ConnectionEvent,
    ConnectionSource,
    Observation,
    ObservedValue,
    QualityEvent,
    QualityEventKind,
    SignalRef,
)
from cvidee.store.enums import ObservationKind, ObservationOrigin
from cvidee.store.models import ConnectionEvent as ConnectionEventRow
from cvidee.store.models import Observation as ObservationRow
from cvidee.store.models import SourceEntity
from cvidee.store.records import DuplicateCount, InsertResult, ObservationRecord

__all__ = [
    "DAY_MS",
    "RETENTION_MAX_DAYS",
    "RETENTION_MIN_DAYS",
    "RETENTION_SETTING_KEY",
    "UNKNOWN_STATES",
    "PurgeResult",
    "SqlObservationRepository",
    "classify",
    "duplicate_quality_events",
    "merge_duplicate_counts",
    "merge_records",
    "resolve_retention_days",
    "retention_cutoff_ts",
    "run_retention",
    "to_analysis_observation",
]

DAY_MS = 24 * HOUR_MS

UNKNOWN_STATES: frozenset[str] = frozenset({"unavailable", "unknown"})
"""Raw HA states that mean "value explicitly unknown" (``Observation.value is None``)."""

_KIND_RANK: Mapping[ObservationKind, int] = {
    ObservationKind.POLL: 0,
    ObservationKind.CONFIRM: 1,
    ObservationKind.CHANGE: 2,
}

_OBS = cast(Table, ObservationRow.__table__)
_CONN = cast(Table, ConnectionEventRow.__table__)
_ENT = cast(Table, SourceEntity.__table__)

type _Key = tuple[int, str]  # (ts, state): order of rows within one entity


# ------------------------------------------------------------------------- pure helpers


def hour_floor(ts: int) -> int:
    return ts - ts % HOUR_MS


def merge_records(a: ObservationRecord, b: ObservationRecord) -> ObservationRecord:
    """Merge two records with the same ``(entity, ts, state)``; commutative and idempotent.

    ``kind`` is the *reported* kind here.
    """
    if a.last_reported_ts is None:
        last_reported = b.last_reported_ts
    elif b.last_reported_ts is None:
        last_reported = a.last_reported_ts
    else:
        last_reported = max(a.last_reported_ts, b.last_reported_ts)
    if a.value_num is None:
        value_num = b.value_num
    elif b.value_num is None:
        value_num = a.value_num
    else:
        value_num = min(a.value_num, b.value_num)  # equal in practice; min keeps it symmetric
    live = ObservationOrigin.LIVE in (a.origin, b.origin)
    return ObservationRecord(
        entity_id=a.entity_id,
        ts=a.ts,
        state=a.state,
        value_num=value_num,
        kind=a.kind if _KIND_RANK[a.kind] >= _KIND_RANK[b.kind] else b.kind,
        origin=ObservationOrigin.LIVE if live else ObservationOrigin.IMPORT,
        received_at_ts=min(a.received_at_ts, b.received_at_ts),
        last_reported_ts=last_reported,
    )


def classify(
    reported_kind: ObservationKind, state: str, previous_state: str | None
) -> ObservationKind:
    """Stored kind: a reported change that repeats the previous state is a confirm."""
    if reported_kind is ObservationKind.CHANGE and state == previous_state:
        return ObservationKind.CONFIRM
    return reported_kind


def merge_duplicate_counts(*groups: Iterable[DuplicateCount]) -> tuple[DuplicateCount, ...]:
    """Sum duplicate counts (e.g. of several insert batches) per (entity, hour)."""
    total: Counter[tuple[str, int]] = Counter()
    for group in groups:
        for c in group:
            total[(c.entity_id, c.hour_start_ts)] += c.count
    return tuple(DuplicateCount(e, h, n) for (e, h), n in sorted(total.items()) if n > 0)


def duplicate_quality_events(
    counts: Iterable[DuplicateCount],
    signal_for: Callable[[str, int], SignalRef | None],
) -> tuple[QualityEvent, ...]:
    """'Ontdubbeld' quality events (ADR-003 §8): one per signal and whole UTC hour, with
    ``count``.

    ``signal_for(entity_id, hour_start_ts)`` applies the role mapping valid at that time;
    entities without a mapping are skipped (``None`` would mean "all signals").
    """
    total: Counter[tuple[int, SignalRef]] = Counter()
    for c in counts:
        signal = signal_for(c.entity_id, c.hour_start_ts)
        if signal is not None and c.count > 0:
            total[(c.hour_start_ts, signal)] += c.count
    return tuple(
        QualityEvent(
            kind=QualityEventKind.DUPLICATE,
            signal=signal,
            start=hour,
            end=hour + HOUR_MS,
            count=n,
            final=True,
        )
        for (hour, signal), n in sorted(total.items(), key=lambda kv: (kv[0][0], str(kv[0][1])))
    )


def to_analysis_observation(
    record: ObservationRecord,
    signal: SignalRef,
    value_map: Mapping[str, ObservedValue | None] | None = None,
) -> Observation:
    """Map a stored record to the pipeline's ``Observation`` for ``signal`` (ADR-001 §3).

    ``unavailable``/``unknown`` become ``None``; a mapping's ``value_map`` (raw state ->
    canonical value) wins; otherwise ``on``/``off`` as ``bool``, the parsed number, else
    the raw state as code.
    """
    value: ObservedValue | None
    if record.state in UNKNOWN_STATES:
        value = None
    elif value_map is not None and record.state in value_map:
        value = value_map[record.state]
    elif record.state in ("on", "off"):
        value = record.state == "on"
    elif record.value_num is not None:
        value = float(record.value_num)
    else:
        value = record.state
    last_reported = record.last_reported_ts
    # ADR-003 §4.3: only a poll may carry evidence older than its ts.
    if (
        last_reported is not None
        and last_reported < record.ts
        and record.kind is not ObservationKind.POLL
    ):
        last_reported = None
    return Observation(
        signal=signal,
        ts=record.ts,
        value=value,
        kind=record.kind,
        last_reported=last_reported,
    )


# ------------------------------------------------------------------------------ retention

RETENTION_SETTING_KEY = "retention.raw_days"
RETENTION_MIN_DAYS = 30
RETENTION_MAX_DAYS = 730


@dataclass(frozen=True, slots=True)
class PurgeResult:
    cutoff_ts: int
    observations: int
    connection_events: int

    @property
    def total(self) -> int:
        return self.observations + self.connection_events


def resolve_retention_days(settings_values: Mapping[str, Any] | None, default_days: int) -> int:
    """``retention.raw_days`` from the current settings revision, else ``default_days``.

    Values outside 30-730 days (ADR-001 §7) or of the wrong type fall back to the default.
    """
    if settings_values is not None:
        raw = settings_values.get("retention_days", settings_values.get(RETENTION_SETTING_KEY))
        if (
            isinstance(raw, int)
            and not isinstance(raw, bool)
            and RETENTION_MIN_DAYS <= raw <= RETENTION_MAX_DAYS
        ):
            return raw
    return default_days


def retention_cutoff_ts(now_ts: int, retention_days: int) -> int:
    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")
    return now_ts - retention_days * DAY_MS


def run_retention(
    repository: "SqlObservationRepository", now_ts: int, retention_days: int
) -> PurgeResult:
    """Daily retention job: delete raw rows older than ``now - retention``."""
    return repository.purge_raw_before(retention_cutoff_ts(now_ts, retention_days))


# ----------------------------------------------------------------------------- repository


def _record_from_row(entity_id: str, row: Any, kind_col: str) -> ObservationRecord:
    m = row._mapping
    return ObservationRecord(
        entity_id=entity_id,
        ts=m["ts"],
        state=m["state"],
        value_num=m["value_num"],
        kind=m[kind_col],
        origin=m["origin"],
        received_at_ts=m["received_at_ts"],
        last_reported_ts=m["last_reported_ts"],
    )


_RECORD_COLUMNS = (
    _OBS.c.id,
    _OBS.c.ts,
    _OBS.c.state,
    _OBS.c.value_num,
    _OBS.c.kind,
    _OBS.c.reported_kind,
    _OBS.c.origin,
    _OBS.c.received_at_ts,
    _OBS.c.last_reported_ts,
)

_UPDATE_OBS = (
    update(_OBS)
    .where(_OBS.c.id == bindparam("b_id"))
    .values(
        kind=bindparam("b_kind"),
        reported_kind=bindparam("b_reported_kind"),
        value_num=bindparam("b_value_num"),
        origin=bindparam("b_origin"),
        received_at_ts=bindparam("b_received_at_ts"),
        last_reported_ts=bindparam("b_last_reported_ts"),
    )
)


class SqlObservationRepository:
    """SQLAlchemy (SQLite) implementation of :class:`~cvidee.store.repositories.
    ObservationRepository`."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._entity_ids: dict[str, int] = {}

    # ------------------------------------------------------------------ observations

    def add_observations(self, records: Iterable[ObservationRecord]) -> InsertResult:
        batch: dict[str, dict[_Key, ObservationRecord]] = defaultdict(dict)
        dupes: Counter[tuple[str, int]] = Counter()
        for r in records:
            per_entity = batch[r.entity_id]
            key = (r.ts, r.state)
            seen = per_entity.get(key)
            if seen is None:
                per_entity[key] = r
            else:
                per_entity[key] = merge_records(seen, r)
                dupes[(r.entity_id, hour_floor(r.ts))] += 1
        if not batch:
            return InsertResult(inserted=0, duplicates_skipped=0)

        ids = self._ensure_entities(batch)
        inserted = 0
        for entity_id in sorted(batch):
            inserted += self._upsert_entity(entity_id, ids[entity_id], batch[entity_id], dupes)
        counts = tuple(DuplicateCount(e, h, n) for (e, h), n in sorted(dupes.items()))
        return InsertResult(
            inserted=inserted,
            duplicates_skipped=sum(c.count for c in counts),
            duplicates=counts,
        )

    def _ensure_entities(
        self, batch: Mapping[str, Mapping[_Key, ObservationRecord]]
    ) -> dict[str, int]:
        bounds = {e: (min(rs)[0], max(rs)[0]) for e, rs in batch.items()}
        found = {
            row.entity_id: (row.id, row.first_seen_ts, row.last_seen_ts)
            for row in self._session.execute(
                select(
                    _ENT.c.id, _ENT.c.entity_id, _ENT.c.first_seen_ts, _ENT.c.last_seen_ts
                ).where(_ENT.c.entity_id.in_(list(bounds)))
            )
        }
        for entity_id, (lo, hi) in sorted(bounds.items()):
            if entity_id not in found:
                new_id = self._session.execute(
                    insert(_ENT)
                    .values(entity_id=entity_id, first_seen_ts=lo, last_seen_ts=hi)
                    .returning(_ENT.c.id)
                ).scalar_one()
                found[entity_id] = (new_id, lo, hi)
            else:
                sid, first, last = found[entity_id]
                if lo < first or hi > last:
                    self._session.execute(
                        update(_ENT)
                        .where(_ENT.c.id == sid)
                        .values(first_seen_ts=min(lo, first), last_seen_ts=max(hi, last))
                    )
        result = {e: v[0] for e, v in found.items()}
        self._entity_ids.update(result)
        return result

    def _upsert_entity(
        self,
        entity_id: str,
        sid: int,
        batch: Mapping[_Key, ObservationRecord],
        dupes: Counter[tuple[str, int]],
    ) -> int:
        lo = min(batch)[0]
        hi = max(batch)[0]
        order = (_OBS.c.ts, _OBS.c.state)
        stored: dict[_Key, tuple[int, ObservationKind, ObservationRecord]] = {}
        for row in self._session.execute(
            select(*_RECORD_COLUMNS)
            .where(_OBS.c.source_entity_id == sid, _OBS.c.ts >= lo, _OBS.c.ts <= hi)
            .order_by(*order)
        ):
            rec = _record_from_row(entity_id, row, "reported_kind")
            stored[(rec.ts, rec.state)] = (row.id, row.kind, rec)
        previous_state = self._session.execute(
            select(_OBS.c.state)
            .where(_OBS.c.source_entity_id == sid, _OBS.c.ts < lo)
            .order_by(_OBS.c.ts.desc(), _OBS.c.state.desc())
            .limit(1)
        ).scalar_one_or_none()
        successor = self._session.execute(
            select(_OBS.c.id, _OBS.c.state, _OBS.c.kind, _OBS.c.reported_kind)
            .where(_OBS.c.source_entity_id == sid, _OBS.c.ts > hi)
            .order_by(*order)
            .limit(1)
        ).first()

        inserts: list[dict[str, Any]] = []
        updates: list[dict[str, Any]] = []
        for key in sorted(stored.keys() | batch.keys()):
            new = batch.get(key)
            old = stored.get(key)
            if old is None:
                assert new is not None
                rec = new
            elif new is None:
                rec = old[2]
            else:
                rec = merge_records(old[2], new)
                dupes[(entity_id, hour_floor(rec.ts))] += 1
            kind = classify(rec.kind, rec.state, previous_state)
            previous_state = rec.state
            if old is None:
                inserts.append(
                    {
                        "source_entity_id": sid,
                        "ts": rec.ts,
                        "state": rec.state,
                        "value_num": rec.value_num,
                        "kind": kind,
                        "reported_kind": rec.kind,
                        "origin": rec.origin,
                        "received_at_ts": rec.received_at_ts,
                        "last_reported_ts": rec.last_reported_ts,
                    }
                )
            elif kind is not old[1] or rec != old[2]:
                updates.append(_update_params(old[0], kind, rec))

        if successor is not None:
            kind = classify(successor.reported_kind, successor.state, previous_state)
            if kind is not successor.kind:
                self._session.execute(
                    update(_OBS).where(_OBS.c.id == successor.id).values(kind=kind)
                )
        if inserts:
            self._session.execute(insert(_OBS), inserts)
        if updates:
            self._session.execute(_UPDATE_OBS, updates)
        return len(inserts)

    def _entity_id(self, entity_id: str) -> int | None:
        sid = self._entity_ids.get(entity_id)
        if sid is None:
            sid = self._session.execute(
                select(_ENT.c.id).where(_ENT.c.entity_id == entity_id)
            ).scalar_one_or_none()
            if sid is not None:
                self._entity_ids[entity_id] = sid
        return sid

    def observations(
        self, entity_id: str, start_ts: int, end_ts: int, *, with_carry_in: bool = False
    ) -> list[ObservationRecord]:
        """Observations in ``[start_ts, end_ts)`` ordered by ``(ts, state)``.

        With ``with_carry_in`` the last observation before ``start_ts`` (if any) is
        prepended, to seed an analysis window (ADR-002 §3.1).
        """
        sid = self._entity_id(entity_id)
        if sid is None:
            return []
        rows = self._session.execute(
            select(*_RECORD_COLUMNS)
            .where(_OBS.c.source_entity_id == sid, _OBS.c.ts >= start_ts, _OBS.c.ts < end_ts)
            .order_by(_OBS.c.ts, _OBS.c.state)
        )
        result = [_record_from_row(entity_id, row, "kind") for row in rows]
        if with_carry_in:
            seed = self.last_before(entity_id, start_ts)
            if seed is not None:
                result.insert(0, seed)
        return result

    def last_before(self, entity_id: str, ts: int) -> ObservationRecord | None:
        """The last observation with ``ts`` strictly before ``ts`` (order ``(ts, state)``)."""
        sid = self._entity_id(entity_id)
        if sid is None:
            return None
        row = self._session.execute(
            select(*_RECORD_COLUMNS)
            .where(_OBS.c.source_entity_id == sid, _OBS.c.ts < ts)
            .order_by(_OBS.c.ts.desc(), _OBS.c.state.desc())
            .limit(1)
        ).first()
        return None if row is None else _record_from_row(entity_id, row, "kind")

    # ------------------------------------------------------------- connection events

    def add_connection_events(self, events: Iterable[ConnectionEvent]) -> InsertResult:
        """Insert, ignoring duplicates on ``(source, ts, up)``."""
        unique: set[tuple[ConnectionSource, int, bool]] = set()
        total = 0
        for e in events:
            total += 1
            unique.add((e.source, e.ts, e.up))
        if not unique:
            return InsertResult(inserted=0, duplicates_skipped=0)
        lo = min(k[1] for k in unique)
        hi = max(k[1] for k in unique)
        existing = {
            (row.source, row.ts, row.up)
            for row in self._session.execute(
                select(_CONN.c.source, _CONN.c.ts, _CONN.c.up).where(
                    _CONN.c.ts >= lo, _CONN.c.ts <= hi
                )
            )
        }
        new = sorted(unique - existing, key=lambda k: (k[1], k[0].value, k[2]))
        if new:
            self._session.execute(
                insert(_CONN), [{"source": s, "ts": ts, "up": up} for s, ts, up in new]
            )
        return InsertResult(inserted=len(new), duplicates_skipped=total - len(new))

    def connection_events(
        self, start_ts: int, end_ts: int, *, with_carry_in: bool = False
    ) -> list[ConnectionEvent]:
        """Events in ``[start_ts, end_ts)`` ordered by ``(ts, source, up)``.

        With ``with_carry_in`` the last event before ``start_ts`` of each source is
        prepended (the connection state at the window start).
        """
        rows = self._session.execute(
            select(_CONN.c.ts, _CONN.c.source, _CONN.c.up)
            .where(_CONN.c.ts >= start_ts, _CONN.c.ts < end_ts)
            .order_by(_CONN.c.ts, _CONN.c.source, _CONN.c.up)
        )
        result = [ConnectionEvent(ts=r.ts, source=r.source, up=r.up) for r in rows]
        if with_carry_in:
            seeds: list[ConnectionEvent] = []
            for source in ConnectionSource:
                r = self._session.execute(
                    select(_CONN.c.ts, _CONN.c.up)
                    .where(_CONN.c.source == source, _CONN.c.ts < start_ts)
                    .order_by(_CONN.c.ts.desc(), _CONN.c.up)  # same ts: 'down' is the state
                    .limit(1)
                ).first()
                if r is not None:
                    seeds.append(ConnectionEvent(ts=r.ts, source=source, up=r.up))
            seeds.sort(key=lambda e: (e.ts, e.source.value, e.up))
            result = seeds + result
        return result

    # ---------------------------------------------------------------------- retention

    def purge_before(self, ts: int) -> int:
        """Retention: delete raw rows older than ``ts``; returns the number deleted."""
        return self.purge_raw_before(ts).total

    def purge_raw_before(self, ts: int) -> PurgeResult:
        """Delete observations and connection events with ``ts`` before the cutoff.

        Derived tables are never touched (ADR-001 §7).
        """
        obs = cast(
            CursorResult[Any], self._session.execute(delete(_OBS).where(_OBS.c.ts < ts))
        ).rowcount
        conn = cast(
            CursorResult[Any], self._session.execute(delete(_CONN).where(_CONN.c.ts < ts))
        ).rowcount
        return PurgeResult(cutoff_ts=ts, observations=obs, connection_events=conn)


def _update_params(row_id: int, kind: ObservationKind, rec: ObservationRecord) -> dict[str, Any]:
    return {
        "b_id": row_id,
        "b_kind": kind,
        "b_reported_kind": rec.kind,
        "b_value_num": rec.value_num,
        "b_origin": rec.origin,
        "b_received_at_ts": rec.received_at_ts,
        "b_last_reported_ts": rec.last_reported_ts,
    }
