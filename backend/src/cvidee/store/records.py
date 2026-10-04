"""Storage-neutral records for raw data (ADR-001 §8).

Raw observations are stored per HA entity (not per signal role), so the raw-data
repository speaks in :class:`ObservationRecord`. Derived data uses the result types of
:mod:`cvidee.analysis.types` directly (``BurnerCycle``, ``ModeSegment``, ``QualityEvent``,
``MetricValue``), as do connection events (``ConnectionEvent``). Times are UTC ms epoch.
"""

from dataclasses import dataclass

from cvidee.store.enums import ObservationKind, ObservationOrigin


@dataclass(frozen=True, slots=True)
class ObservationRecord:
    entity_id: str  # HA entity id, e.g. 'binary_sensor.remeha_flame'
    ts: int
    state: str  # raw HA state, incl. 'unavailable' / 'unknown'
    value_num: float | None
    kind: ObservationKind
    origin: ObservationOrigin
    received_at_ts: int
    last_reported_ts: int | None = None


@dataclass(frozen=True, slots=True)
class InsertResult:
    inserted: int
    duplicates_skipped: int
