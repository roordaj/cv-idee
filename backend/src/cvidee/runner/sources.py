"""Read side of the runner: pipeline configuration and window input from the store.

* :func:`load_mapped_signals` reads the versioned signal mappings (role + scope → HA
  entity) with their validity in data time.
* :func:`build_pipeline_config` turns the current mappings into a
  :class:`~cvidee.analysis.types.PipelineConfig` with a deterministic ``config_hash``.
* :func:`load_window_input` reads what one run needs (ADR-002 §4.2 step 1): observations
  of every mapped entity in ``[context_start, end)`` within the mapping's validity, plus
  per signal the carry-in; connection events from the latest "down" before
  ``context_start`` onwards plus a carry-in per source; and the states of the optional
  CAN-gateway connectivity entity as ``ConnectionEvent(CAN_GATEWAY)`` (ADR-003 §5.2).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, cast

from sqlalchemy import Table, select
from sqlalchemy.orm import Session

from cvidee.analysis.types import (
    AnalysisWindow,
    ConnectionEvent,
    ConnectionSource,
    Observation,
    ObservationKind,
    ObservedValue,
    PipelineConfig,
    Provenance,
    Role,
    Scope,
    ScopeKind,
    SignalConfig,
    SignalRef,
    TimestampMs,
    ValueKind,
)
from cvidee.rules.base import signal_ref
from cvidee.store.models import ConnectionEvent as ConnectionEventRow
from cvidee.store.models import Observation as ObservationRow
from cvidee.store.models import SignalDefinition, SignalMapping, SourceEntity
from cvidee.store.observations import SqlObservationRepository, to_analysis_observation
from cvidee.store.records import ObservationRecord

__all__ = [
    "MappedSignal",
    "SourceSettings",
    "build_pipeline_config",
    "config_hash",
    "earliest_data_ts",
    "gateway_events",
    "load_mapped_signals",
    "load_window_input",
]

_OBS = cast(Table, ObservationRow.__table__)
_CONN = cast(Table, ConnectionEventRow.__table__)
_ENT = cast(Table, SourceEntity.__table__)


@dataclass(frozen=True, slots=True)
class SourceSettings:
    """Runner-side source configuration not (yet) held in ``signal_mappings``.

    ``can_gateway_entity_id``: HA connectivity entity of the CAN gateway (ADR-003 §5.2),
    ``None`` = not configured. ``can_gateway_roles``: roles whose values arrive via that
    gateway (``via_can_gateway``); empty until #5 establishes the boiler integration.
    """

    can_gateway_entity_id: str | None = None
    can_gateway_roles: frozenset[Role] = frozenset()


@dataclass(frozen=True, slots=True)
class MappedSignal:
    """One mapping version: ``signal`` reads ``entity_id`` during ``[valid_from, valid_to)``."""

    signal: SignalRef
    entity_id: str
    valid_from: TimestampMs
    valid_to: TimestampMs | None
    kind: ValueKind
    heartbeat_expected: bool
    max_age_ms: int
    value_map: Mapping[str, ObservedValue | None] | None
    mapping_id: int | None = None
    meaning: str | None = None

    def valid_at(self, ts: TimestampMs) -> bool:
        return self.valid_from <= ts and (self.valid_to is None or ts < self.valid_to)


def load_mapped_signals(session: Session) -> list[MappedSignal]:
    """All mapping versions (current and historical) with known roles, sorted."""
    rows = session.execute(
        select(SignalMapping, SourceEntity.entity_id).join(
            SourceEntity, SourceEntity.id == SignalMapping.source_entity_id
        )
    )
    out: list[MappedSignal] = []
    for mapping, entity_id in rows:
        try:
            role = Role(mapping.role)
            if mapping.scope_key:
                kind, _, key = mapping.scope_key.partition(":")
                signal = SignalRef(role, Scope(ScopeKind(kind), key))
            else:
                signal = signal_ref(role)
        except ValueError:
            continue  # unknown role or malformed scope: not analysable
        out.append(
            MappedSignal(
                signal=signal,
                entity_id=entity_id,
                valid_from=mapping.valid_from_ts,
                valid_to=mapping.valid_to_ts,
                kind=ValueKind(mapping.kind),
                heartbeat_expected=mapping.heartbeat_expected,
                max_age_ms=mapping.max_age_ms,
                value_map=mapping.value_map,
                mapping_id=mapping.id,
                meaning=mapping.meaning,
            )
        )
    out.sort(key=lambda m: (m.signal, m.valid_from, m.entity_id))
    return out


def mode_mapping_snapshot(mapped: Sequence[MappedSignal]) -> list[dict[str, Any]]:
    """Source- and data-time-bound mode semantics, safe to freeze in run/advice history."""
    return [
        {
            "version": m.mapping_id,
            "signal": str(m.signal),
            "entity_id": m.entity_id,
            "valid_from": m.valid_from,
            "valid_to": m.valid_to,
            "meaning": m.meaning,
            "source_semantics_confirmed": bool(m.meaning and m.meaning.strip() and m.value_map),
            "value_map": None if m.value_map is None else dict(sorted(m.value_map.items())),
        }
        for m in sorted(mapped, key=lambda m: (m.signal, m.valid_from, m.entity_id))
        if m.signal.role is Role.OPERATING_MODE
    ]


def config_hash(config: PipelineConfig, extra: Mapping[str, Any] | None = None) -> str:
    """Deterministic hash of a configuration snapshot (ADR-001 §6: settings, mappings,
    rule versions). ``repr`` of the frozen dataclasses is stable for equal content."""
    payload = repr((replace(config, config_hash=""), sorted((extra or {}).items())))
    return hashlib.sha256(payload.encode()).hexdigest()


def build_pipeline_config(
    session: Session,
    mapped: Sequence[MappedSignal],
    sources: SourceSettings,
    *,
    base: PipelineConfig | None = None,
    rule_versions: Mapping[str, str] | None = None,
) -> PipelineConfig:
    """Pipeline configuration from the latest mapping version per signal.

    Thresholds come from ``base`` (defaults of :class:`PipelineConfig` if omitted);
    plausibility bounds and counter flags from ``signal_definitions`` where present.
    """
    definitions = {d.role: d for d in session.scalars(select(SignalDefinition))}
    latest: dict[SignalRef, MappedSignal] = {}
    for m in mapped:  # sorted by valid_from: the last one wins
        latest[m.signal] = m
    signals: list[SignalConfig] = []
    for signal, m in sorted(latest.items()):
        definition = definitions.get(signal.role.value)
        signals.append(
            SignalConfig(
                signal=signal,
                provenance=Provenance(m.kind, m.entity_id),
                heartbeat_expected=m.heartbeat_expected,
                max_age_ms=m.max_age_ms if m.heartbeat_expected else None,
                plausible_min=None if definition is None else definition.plausible_min,
                plausible_max=None if definition is None else definition.plausible_max,
                cumulative=False if definition is None else definition.cumulative,
                via_can_gateway=signal.role in sources.can_gateway_roles,
            )
        )
    template = base if base is not None else PipelineConfig(signals=())
    config = replace(template, signals=tuple(signals), config_hash="")
    extra: dict[str, Any] = {
        "mappings": [
            (str(m.signal), m.entity_id, m.valid_from, m.valid_to, repr(m.value_map))
            for m in mapped
        ],
        "operating_mode_mappings": mode_mapping_snapshot(mapped),
        "gateway": sources.can_gateway_entity_id,
        "rules": sorted((rule_versions or {}).items()),
    }
    return replace(config, config_hash=config_hash(config, extra))


def earliest_data_ts(session: Session, mapped: Sequence[MappedSignal]) -> TimestampMs | None:
    """Timestamp of the oldest stored observation of any mapped entity."""
    entities = sorted({m.entity_id for m in mapped})
    if not entities:
        return None
    ts = session.execute(
        select(_OBS.c.ts)
        .join(_ENT, _ENT.c.id == _OBS.c.source_entity_id)
        .where(_ENT.c.entity_id.in_(entities))
        .order_by(_OBS.c.ts)
        .limit(1)
    ).scalar()
    return None if ts is None else int(ts)


def _gateway_up(record: ObservationRecord) -> bool:
    """ADR-003 §5.2: ``on`` → up; ``off``, ``unavailable``, ``unknown`` → down."""
    return record.state == "on"


def gateway_events(
    repo: SqlObservationRepository, entity_id: str, start_ts: int, end_ts: int
) -> list[ConnectionEvent]:
    """States of the gateway connectivity entity in ``[start_ts, end_ts)`` (with carry-in)
    as ``ConnectionEvent(CAN_GATEWAY)``."""
    return [
        ConnectionEvent(r.ts, ConnectionSource.CAN_GATEWAY, _gateway_up(r))
        for r in repo.observations(entity_id, start_ts, end_ts, with_carry_in=True)
    ]


def _last_down_before(
    session: Session, sources: SourceSettings, ts: TimestampMs
) -> TimestampMs | None:
    """Latest WS/gateway "down" before ``ts`` (to make an outage before the context visible)."""
    found: list[int] = []
    for source in (ConnectionSource.WS, ConnectionSource.CAN_GATEWAY):
        value = session.execute(
            select(_CONN.c.ts)
            .where(_CONN.c.source == source, _CONN.c.ts < ts, _CONN.c.up.is_(False))
            .order_by(_CONN.c.ts.desc())
            .limit(1)
        ).scalar()
        if value is not None:
            found.append(int(value))
    if sources.can_gateway_entity_id is not None:
        value = session.execute(
            select(_OBS.c.ts)
            .join(_ENT, _ENT.c.id == _OBS.c.source_entity_id)
            .where(
                _ENT.c.entity_id == sources.can_gateway_entity_id,
                _OBS.c.ts < ts,
                _OBS.c.state != "on",
            )
            .order_by(_OBS.c.ts.desc())
            .limit(1)
        ).scalar()
        if value is not None:
            found.append(int(value))
    return min(found) if found else None


def _mapped_observation(
    record: ObservationRecord, mapping: MappedSignal, config: PipelineConfig | None
) -> Observation:
    table = mapping.value_map
    if mapping.signal.role is Role.OPERATING_MODE:
        if table is None:
            # Only an explicitly supplied synthetic/replay table may interpret raw codes.
            table = None if config is not None and config.mode_mapping else {}
        elif not mapping.meaning or not mapping.meaning.strip():
            table = {}  # legacy unproven semantics are unknown, including for coverage
    return to_analysis_observation(record, mapping.signal, table)


def _carry_in(
    repo: SqlObservationRepository,
    versions: Sequence[MappedSignal],
    ts: TimestampMs,
    config: PipelineConfig | None,
) -> Observation | None:
    """Latest observation before ``ts`` within the validity of the mapping that held it."""
    for m in sorted(versions, key=lambda v: v.valid_from, reverse=True):
        if m.valid_from >= ts or not m.valid_at(ts):
            continue
        upper = ts if m.valid_to is None else min(ts, m.valid_to)
        record = repo.last_before(m.entity_id, upper)
        if record is not None and record.ts >= m.valid_from:
            return _mapped_observation(record, m, config)
    return None


def load_window_input(
    session: Session,
    mapped: Sequence[MappedSignal],
    sources: SourceSettings,
    window: AnalysisWindow,
    config: PipelineConfig | None = None,
) -> tuple[list[Observation], list[ConnectionEvent]]:
    """Observations and connection events for one run (ADR-002 §4.2 step 1)."""
    repo = SqlObservationRepository(session)
    start, end = window.context_start, window.end
    by_signal: dict[SignalRef, list[MappedSignal]] = {}
    for m in mapped:
        by_signal.setdefault(m.signal, []).append(m)
    observations: list[Observation] = []
    for signal, versions in sorted(by_signal.items()):
        seed = _carry_in(repo, versions, start, config)
        if seed is not None:
            observations.append(seed)
        for m in versions:
            lo = max(start, m.valid_from)
            hi = end if m.valid_to is None else min(end, m.valid_to)
            if lo >= hi:
                continue
            observations.extend(
                _mapped_observation(r, m, config) for r in repo.observations(m.entity_id, lo, hi)
            )
        # Closing or unlinking a mapping ends validity even without another HA event.
        for m in versions:
            boundary = m.valid_to
            if (
                boundary is not None
                and start <= boundary < end
                and not any(
                    observation.signal == signal and observation.ts == boundary
                    for observation in observations
                )
            ):
                observations.append(Observation(signal, boundary, None, ObservationKind.POLL))
    since = start
    last_down = _last_down_before(session, sources, start)
    if last_down is not None:
        since = min(since, last_down)
    events = repo.connection_events(since, end, with_carry_in=True)
    if sources.can_gateway_entity_id is not None:
        events.extend(gateway_events(repo, sources.can_gateway_entity_id, since, end))
    return observations, events
