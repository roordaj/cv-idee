"""Ingest service: HA client -> raw observation store (ADR-003 §4, §5).

Mapping of HA messages to observations (all times are HA timestamps, UTC ms):

* ``state_changed`` with a different state -> ``CHANGE`` at ``new_state.last_changed``; when
  ``old_state.last_reported > old_state.last_updated`` first a ``CONFIRM`` of the old value at
  ``old_state.last_reported`` (last evidence for the old value).
* same state (attribute-only / ``force_update``) -> ``CONFIRM`` at ``new_state.last_updated``.
* no ``old_state`` -> ``CHANGE``; no ``new_state`` -> ``CHANGE`` to ``unavailable`` at
  ``time_fired``.
* (re)connect: ``WS`` up event and one ``POLL`` per tracked entity, both at the poll moment.
* connection loss: ``WS`` down at the time of the last message received.
* confirmation polling (§4.4) over REST for signals with ``heartbeat_expected``.
* ``ingest_alive_at`` is persisted every minute; after a crash the next start first writes
  ``WS`` down at that time.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from cvidee.analysis.types import ConnectionEvent, ConnectionSource
from cvidee.ingest.ha_client import HAClient, HAState, StateChangedEvent, now_ms
from cvidee.store.enums import ObservationKind, ObservationOrigin
from cvidee.store.models import SignalMapping, SourceEntity
from cvidee.store.observations import UNKNOWN_STATES, SqlObservationRepository
from cvidee.store.records import ObservationRecord

logger = logging.getLogger(__name__)

__all__ = [
    "AliveStore",
    "FileAliveStore",
    "IngestService",
    "TrackedEntity",
    "confirm_poll_interval_ms",
    "map_state_changed",
    "sql_tracked_entities",
]

HOUSEKEEPING_INTERVAL_S = 15.0
ALIVE_INTERVAL_S = 60.0
CONFIRM_MIN_INTERVAL_MS = 5_000
CONFIRM_MAX_INTERVAL_MS = 60_000


@dataclass(frozen=True, slots=True)
class TrackedEntity:
    entity_id: str
    heartbeat_expected: bool = False
    max_age_ms: int | None = None


class AliveStore(Protocol):
    def read(self) -> int | None: ...

    def write(self, ts: int) -> None: ...


class FileAliveStore:
    """``ingest_alive_at`` in a small file next to the database."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def read(self) -> int | None:
        try:
            return int(self._path.read_text().strip())
        except (OSError, ValueError):
            return None

    def write(self, ts: int) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(str(ts))
        except OSError:
            logger.warning("Could not persist ingest_alive_at to %s", self._path)


def sql_tracked_entities(
    session_factory: Callable[[], AbstractContextManager[Session]],
) -> list[TrackedEntity]:
    """Entities in a current signal mapping (``valid_to_ts IS NULL``)."""
    with session_factory() as session:
        rows = session.execute(
            select(
                SourceEntity.entity_id, SignalMapping.heartbeat_expected, SignalMapping.max_age_ms
            )
            .join(SignalMapping, SignalMapping.source_entity_id == SourceEntity.id)
            .where(SignalMapping.valid_to_ts.is_(None))
        ).all()
    merged: dict[str, TrackedEntity] = {}
    for entity_id, heartbeat, max_age in rows:
        prev = merged.get(entity_id)
        if heartbeat:
            if prev is not None and prev.heartbeat_expected and prev.max_age_ms:
                max_age = min(max_age, prev.max_age_ms)
            merged[entity_id] = TrackedEntity(entity_id, True, max_age)
        elif prev is None:
            merged[entity_id] = TrackedEntity(entity_id)
    return list(merged.values())


def confirm_poll_interval_ms(entities: Iterable[TrackedEntity]) -> int | None:
    """Smallest ``max_age / 3`` of heartbeat signals, clamped to 5-60 s; ``None`` if none."""
    ages = [e.max_age_ms for e in entities if e.heartbeat_expected and e.max_age_ms]
    if not ages:
        return None
    return max(CONFIRM_MIN_INTERVAL_MS, min(CONFIRM_MAX_INTERVAL_MS, min(ages) // 3))


def _value_num(state: str) -> float | None:
    if state in UNKNOWN_STATES:
        return None
    try:
        return float(state)
    except ValueError:
        return None


def _record(
    entity_id: str,
    state: str,
    ts: int,
    kind: ObservationKind,
    received_at: int,
    last_reported: int | None,
) -> ObservationRecord:
    # CHANGE/CONFIRM require last_reported >= ts (ADR-003 §4.3); only a POLL may be older.
    if kind is not ObservationKind.POLL and (last_reported is None or last_reported < ts):
        last_reported = ts
    return ObservationRecord(
        entity_id=entity_id,
        ts=ts,
        state=state,
        value_num=_value_num(state),
        kind=kind,
        origin=ObservationOrigin.LIVE,
        received_at_ts=received_at,
        last_reported_ts=last_reported,
    )


def map_state_changed(event: StateChangedEvent, received_at: int) -> list[ObservationRecord]:
    """ADR-003 §4.2 mapping of one ``state_changed`` event."""
    old, new = event.old_state, event.new_state
    eid = event.entity_id
    if new is None:
        return [
            _record(eid, "unavailable", event.time_fired, ObservationKind.CHANGE, received_at, None)
        ]
    changed_ts = new.last_changed or new.last_updated or event.time_fired
    if old is None:
        return [
            _record(
                eid, new.state, changed_ts, ObservationKind.CHANGE, received_at, new.last_reported
            )
        ]
    if new.state != old.state:
        out: list[ObservationRecord] = []
        if (
            old.last_reported is not None
            and old.last_updated is not None
            and old.last_reported > old.last_updated
            and old.last_reported < changed_ts
        ):
            out.append(
                _record(
                    eid, old.state, old.last_reported, ObservationKind.CONFIRM, received_at, None
                )
            )
        out.append(
            _record(
                eid, new.state, changed_ts, ObservationKind.CHANGE, received_at, new.last_reported
            )
        )
        return out
    ts = new.last_updated or event.time_fired
    return [_record(eid, new.state, ts, ObservationKind.CONFIRM, received_at, new.last_reported)]


class IngestService:
    """Wires an :class:`HAClient` to the observation store."""

    def __init__(
        self,
        client: HAClient,
        session_factory: Callable[[], AbstractContextManager[Session]],
        tracked_provider: Callable[[], list[TrackedEntity]],
        *,
        alive_store: AliveStore | None = None,
        clock: Callable[[], int] = now_ms,
        confirm_interval_override_s: float | None = None,
    ) -> None:
        self._client = client
        self._session_factory = session_factory
        self._provider = tracked_provider
        self._alive = alive_store
        self._clock = clock
        self._interval_override = confirm_interval_override_s
        self._tracked: dict[str, TrackedEntity] = {}
        self._tasks: list[asyncio.Task[None]] = []
        self.refresh_tracked()

    # --------------------------------------------------------------- lifecycle

    def tracked_ids(self) -> set[str]:
        """Entity ids the client filters on (live view, refreshed by housekeeping)."""
        return set(self._tracked)

    def refresh_tracked(self) -> None:
        try:
            self._tracked = {e.entity_id: e for e in self._provider()}
        except Exception:
            logger.exception("Could not refresh tracked entities")

    @property
    def connected(self) -> bool:
        return self._client.connected

    async def start(self) -> None:
        self._write_crash_down_event()
        self._tasks = [
            asyncio.create_task(self._client.run(self), name="ha-client"),
            asyncio.create_task(self._housekeeping(), name="ingest-housekeeping"),
            asyncio.create_task(self._confirm_polling(), name="ingest-confirm-polling"),
        ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        await self._client.close()

    def _write_crash_down_event(self) -> None:
        """App restart or crash (§5.1): last WS up -> write down at ``ingest_alive_at``."""
        alive_at = self._alive.read() if self._alive is not None else None
        if alive_at is None:
            return
        with self._session_factory() as session:
            repo = SqlObservationRepository(session)
            now = self._clock()
            ws = [
                e
                for e in repo.connection_events(now, now + 1, with_carry_in=True)
                if e.source is ConnectionSource.WS
            ]
            if ws and ws[-1].up:
                repo.add_connection_events(
                    [
                        ConnectionEvent(
                            ts=max(alive_at, ws[-1].ts), source=ConnectionSource.WS, up=False
                        )
                    ]
                )
                session.commit()

    # ------------------------------------------------------------ HAListener

    async def on_connected(self, poll_ts: int, states: list[HAState]) -> None:
        self.refresh_tracked()
        received = self._clock()
        records = [
            _record(s.entity_id, s.state, poll_ts, ObservationKind.POLL, received, s.last_reported)
            for s in states
            if s.entity_id in self._tracked
        ]
        with self._session_factory() as session:
            repo = SqlObservationRepository(session)
            repo.add_connection_events([ConnectionEvent(poll_ts, ConnectionSource.WS, True)])
            repo.add_observations(records)
            session.commit()
        logger.info("Home Assistant connected; %d states polled", len(records))

    async def on_disconnected(self, ts: int) -> None:
        with self._session_factory() as session:
            SqlObservationRepository(session).add_connection_events(
                [ConnectionEvent(ts, ConnectionSource.WS, False)]
            )
            session.commit()
        logger.warning("Home Assistant connection lost (last message at %d)", ts)

    async def on_state_changed(self, event: StateChangedEvent) -> None:
        records = map_state_changed(event, self._clock())
        with self._session_factory() as session:
            SqlObservationRepository(session).add_observations(records)
            session.commit()

    # ------------------------------------------------------------ background

    async def _housekeeping(self) -> None:
        last_alive = 0.0
        loop = asyncio.get_running_loop()
        while True:
            await asyncio.sleep(HOUSEKEEPING_INTERVAL_S)
            self.refresh_tracked()
            if (
                self._alive is not None
                and self._client.connected
                and (loop.time() - last_alive >= ALIVE_INTERVAL_S)
            ):
                self._alive.write(self._clock())
                last_alive = loop.time()

    async def _confirm_polling(self) -> None:
        """ADR-003 §4.4: REST confirmation poll, only when a heartbeat signal is mapped."""
        while True:
            interval_ms = confirm_poll_interval_ms(self._tracked.values())
            if self._interval_override is not None:
                interval_s = self._interval_override
            else:
                interval_s = (interval_ms or CONFIRM_MAX_INTERVAL_MS) / 1000
            await asyncio.sleep(interval_s)
            if interval_ms is None or not self._client.connected:
                continue
            await self.confirmation_poll()

    async def confirmation_poll(self) -> int:
        """One pass; returns the number of CONFIRM observations stored."""
        stored = 0
        for entity in list(self._tracked.values()):
            if not entity.heartbeat_expected or not entity.max_age_ms:
                continue
            try:
                state = await self._client.get_state(entity.entity_id)
            except Exception:
                continue  # a failed poll yields nothing; the signal ages by itself
            if state is None or state.last_reported is None:
                continue
            with self._session_factory() as session:
                repo = SqlObservationRepository(session)
                last = repo.last_before(entity.entity_id, self._clock() + 1)
                if last is None or last.state != state.state:
                    continue  # state_changed stream leads for transitions
                evidence = max(last.ts, last.last_reported_ts or last.ts)
                if state.last_reported - evidence < entity.max_age_ms // 3:
                    continue
                repo.add_observations(
                    [
                        _record(
                            entity.entity_id,
                            state.state,
                            state.last_reported,
                            ObservationKind.CONFIRM,
                            self._clock(),
                            state.last_reported,
                        )
                    ]
                )
                session.commit()
                stored += 1
        return stored
