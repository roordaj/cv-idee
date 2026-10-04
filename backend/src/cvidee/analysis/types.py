"""Immutable data types of the analysis pipeline (ADR-002).

Conventions (see ``docs/adr/002-pipeline.md``):

* All instants are UTC milliseconds since the Unix epoch (:data:`TimestampMs`). There is no
  ``datetime`` in the pipeline; ``Europe/Amsterdam`` is only used for presentation and for
  local day buckets.
* All intervals are half-open ``[start, end)``.
* Types are frozen and slotted dataclasses; collections are tuples so results are hashable
  and comparable (needed for the ``chunked == whole`` property test).
* This module is independent of persistence (no SQLAlchemy); ``cvidee.store`` maps these
  types to rows.
"""

from __future__ import annotations

import bisect
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum

type TimestampMs = int
"""UTC instant in milliseconds since the Unix epoch."""

type DurationMs = int
"""Duration in milliseconds."""

type ObservedValue = float | bool | str
"""Normalised signal value: numbers as ``float``, binary signals as ``bool``, codes as ``str``."""

HOUR_MS: DurationMs = 3_600_000
MINUTE_MS: DurationMs = 60_000


def _check_range(start: TimestampMs, end: TimestampMs, what: str) -> None:
    if end <= start:
        raise ValueError(f"{what}: end ({end}) must be after start ({start})")


# --------------------------------------------------------------------------------------
# Time ranges and the analysis window
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TimeRange:
    """Half-open, non-empty interval ``[start, end)`` in UTC ms."""

    start: TimestampMs
    end: TimestampMs

    def __post_init__(self) -> None:
        _check_range(self.start, self.end, "TimeRange")

    @property
    def duration_ms(self) -> DurationMs:
        return self.end - self.start

    def contains(self, ts: TimestampMs) -> bool:
        return self.start <= ts < self.end

    def overlaps(self, other: TimeRange) -> bool:
        return self.start < other.end and other.start < self.end

    def intersect(self, other: TimeRange) -> TimeRange | None:
        start, end = max(self.start, other.start), min(self.end, other.end)
        return TimeRange(start, end) if start < end else None


def floor_to_grid(ts: TimestampMs, grid_ms: DurationMs) -> TimestampMs:
    """Floor ``ts`` to the canonical UTC grid (e.g. whole UTC hours)."""
    if grid_ms <= 0:
        raise ValueError("grid_ms must be positive")
    return ts - (ts % grid_ms)


@dataclass(frozen=True, slots=True)
class AnalysisWindow:
    """One pipeline run over ``[context_start, end)``.

    * ``context_start = emit_from - lookback``: data before ``emit_from`` is only context.
    * ``emit_from = floor_to_grid(watermark)``: only items whose key is ``>= emit_from`` are
      returned and upserted by the runner (replace-from semantics).
    * ``end = now - settle``: the horizon; observations at or after it are ignored.
    """

    context_start: TimestampMs
    emit_from: TimestampMs
    end: TimestampMs

    def __post_init__(self) -> None:
        if not self.context_start <= self.emit_from <= self.end:
            raise ValueError(
                "AnalysisWindow requires context_start <= emit_from <= end, got "
                f"{self.context_start}, {self.emit_from}, {self.end}"
            )

    @classmethod
    def for_run(
        cls,
        *,
        watermark: TimestampMs,
        now: TimestampMs,
        lookback_ms: DurationMs,
        settle_ms: DurationMs,
        grid_ms: DurationMs,
    ) -> AnalysisWindow:
        """Build the window of a runner tick (ADR-002 §4). ``now`` is always a parameter."""
        end = now - settle_ms
        emit_from = min(floor_to_grid(watermark, grid_ms), floor_to_grid(end, grid_ms))
        return cls(context_start=emit_from - lookback_ms, emit_from=emit_from, end=end)

    @property
    def context(self) -> TimeRange | None:
        """The full computed range, or ``None`` if empty."""
        if self.end <= self.context_start:
            return None
        return TimeRange(self.context_start, self.end)

    def emits(self, key: TimestampMs) -> bool:
        """Whether an item with deterministic key ``key`` belongs to this run's output."""
        return self.emit_from <= key < self.end


# --------------------------------------------------------------------------------------
# Signals
# --------------------------------------------------------------------------------------


class ScopeKind(StrEnum):
    """What a parametrised signal role is scoped to."""

    BOILER = "boiler"
    ROOM = "room"
    ZONE = "zone"
    CIRCUIT = "circuit"
    MANIFOLD = "manifold"
    OUTDOOR = "outdoor"


class Role(StrEnum):
    """Canonical signal roles (requirements §2, technical plan §3.5)."""

    FLAME = "flame"
    OPERATING_MODE = "operating_mode"
    HEAT_DEMAND = "heat_demand"
    FLOW_SETPOINT = "flow_setpoint"
    FLOW_TEMPERATURE = "flow_temperature"
    RETURN_TEMPERATURE = "return_temperature"
    MODULATION = "modulation"
    ROOM_TEMPERATURE = "room_temperature"
    ROOM_SETPOINT = "room_setpoint"
    OUTDOOR_TEMPERATURE = "outdoor_temperature"
    GAS_CUMULATIVE = "gas_cumulative"
    ZONE_DEMAND = "zone_demand"
    VALVE_STATE = "valve_state"
    MANIFOLD_FLOW_TEMPERATURE = "manifold_flow_temperature"
    MANIFOLD_RETURN_TEMPERATURE = "manifold_return_temperature"
    FLOW_RATE = "flow_rate"
    PUMP_STATE = "pump_state"
    HEAT_METER = "heat_meter"

    @property
    def scope_kind(self) -> ScopeKind:
        """The scope kind this role is parametrised by."""
        return _ROLE_SCOPE.get(self, ScopeKind.BOILER)


_ROLE_SCOPE: dict[Role, ScopeKind] = {
    Role.ROOM_TEMPERATURE: ScopeKind.ROOM,
    Role.ROOM_SETPOINT: ScopeKind.ROOM,
    Role.OUTDOOR_TEMPERATURE: ScopeKind.OUTDOOR,
    Role.ZONE_DEMAND: ScopeKind.ZONE,
    Role.VALVE_STATE: ScopeKind.ZONE,
    Role.MANIFOLD_FLOW_TEMPERATURE: ScopeKind.MANIFOLD,
    Role.MANIFOLD_RETURN_TEMPERATURE: ScopeKind.MANIFOLD,
}

_SINGLETON_SCOPES = frozenset({ScopeKind.BOILER, ScopeKind.OUTDOOR})


@dataclass(frozen=True, slots=True, order=True)
class Scope:
    """Location a signal belongs to, e.g. ``Scope(ScopeKind.ROOM, "slaapkamer")``.

    Boiler and outdoor are singletons (``key is None``); rooms, zones, circuits and
    manifolds need a key from the installation profile.
    """

    kind: ScopeKind
    key: str | None = None

    def __post_init__(self) -> None:
        if self.kind in _SINGLETON_SCOPES:
            if self.key is not None:
                raise ValueError(f"scope {self.kind} is a singleton and takes no key")
        elif not self.key:
            raise ValueError(f"scope {self.kind} requires a key")


BOILER = Scope(ScopeKind.BOILER)
OUTDOOR = Scope(ScopeKind.OUTDOOR)


@dataclass(frozen=True, slots=True, order=True)
class SignalRef:
    """A concrete signal: a role at a scope (``flow_temperature@boiler``,
    ``room_temperature@room:slaapkamer``). Stable identity across mapping changes."""

    role: Role
    scope: Scope = BOILER

    def __post_init__(self) -> None:
        expected = self.role.scope_kind
        allowed = {expected} | ({ScopeKind.CIRCUIT} if expected is ScopeKind.BOILER else set())
        if self.scope.kind not in allowed:
            raise ValueError(f"role {self.role} cannot have scope {self.scope.kind}")

    def __str__(self) -> str:
        kind, key = self.scope.kind, self.scope.key
        suffix = str(kind) if key is None else f"{kind}:{key}"
        return f"{self.role}@{suffix}"


class ValueKind(IntEnum):
    """Provenance strength of a value; lower is weaker (plan §2.1 principle 4)."""

    ESTIMATED = 0
    DERIVED = 1
    REPORTED = 2
    MEASURED = 3


@dataclass(frozen=True, slots=True)
class Provenance:
    """Kind and source of a value. ``source`` is an HA entity id or a derivation name
    (e.g. ``"derived:boiler_delta_t"``)."""

    kind: ValueKind
    source: str

    @staticmethod
    def derive(source: str, *inputs: Provenance) -> Provenance:
        """Provenance of a value derived from ``inputs``: inherits the weakest kind, and is
        never stronger than ``DERIVED``."""
        kind = min((p.kind for p in inputs), default=ValueKind.DERIVED)
        return Provenance(min(kind, ValueKind.DERIVED), source)


# --------------------------------------------------------------------------------------
# Raw input
# --------------------------------------------------------------------------------------


class ObservationKind(StrEnum):
    """How an observation was obtained (plan §3.1, ADR-003 §4)."""

    CHANGE = "change"
    """A new state value (``state_changed`` with a different state, or a history row whose
    state differs from the previous row): a real transition. ``ts`` = HA ``last_changed``."""
    CONFIRM = "confirm"
    """Same value reported again (``last_reported`` advanced, attribute-only or
    ``force_update`` write): evidence, not a transition. ``ts`` = HA ``last_reported``."""
    POLL = "poll"
    """Value read without knowing its history (``get_states`` after (re)connect, recovery
    poll, first state of an initial import): never a transition. ``ts`` = time of the read."""


@dataclass(frozen=True, slots=True)
class Observation:
    """One raw, normalised observation of a signal.

    ``value is None`` means HA reported ``unavailable``/``unknown``. ``last_reported`` is
    HA's latest report time for this state, if known. For ``CHANGE``/``CONFIRM`` it is
    ``>= ts``; for ``POLL`` it may be *before* ``ts`` (HA last heard from the device before
    we read the state), which makes the evidence older than the read (ADR-003 §4.3).
    """

    signal: SignalRef
    ts: TimestampMs
    value: ObservedValue | None
    kind: ObservationKind
    last_reported: TimestampMs | None = None

    def __post_init__(self) -> None:
        if (
            self.last_reported is not None
            and self.last_reported < self.ts
            and self.kind is not ObservationKind.POLL
        ):
            raise ValueError("last_reported must not be before ts (except for polls)")

    @property
    def evidence_ts(self) -> TimestampMs:
        """Latest instant at which this value is known to have held (HA ``last_reported``
        if known, else ``ts``). May be before ``ts`` for a poll."""
        return self.ts if self.last_reported is None else self.last_reported

    @property
    def sort_key(self) -> tuple[SignalRef, TimestampMs, str, str]:
        """Total order used by every stage (determinism: never rely on input order)."""
        return (self.signal, self.ts, self.kind.value, repr(self.value))


class ConnectionSource(StrEnum):
    WS = "ws"
    """Our own WebSocket connection to HA: affects all signals."""
    CAN_GATEWAY = "can_gateway"
    """HA's connection to the boiler: affects signals configured as ``via_can_gateway``."""
    HISTORY = "history"
    """Coverage by an HA history import (ADR-003 §6): ``up`` starts a range whose
    observations come from the HA recorder, ``down`` ends it. Inside such a range a WS outage
    is not a gap, and staleness is not evaluated (history carries no ``last_reported``)."""


@dataclass(frozen=True, slots=True)
class ConnectionEvent:
    """State change of connection ``source`` at ``ts`` (HA time base, ADR-003 §5)."""

    ts: TimestampMs
    source: ConnectionSource
    up: bool


# --------------------------------------------------------------------------------------
# Timeline (stage 1) and quality (stage 2)
# --------------------------------------------------------------------------------------


class UnknownReason(StrEnum):
    NO_DATA = "no_data"
    """No observation at all (before first observation, or signal not mapped)."""
    STALE = "stale"
    """Older than ``max_age`` for a signal that is expected to report periodically."""
    INVALID = "invalid"
    """Unparseable / wrong type."""
    IMPLAUSIBLE = "implausible"
    """Outside the plausibility bounds of the role."""
    DISCONNECTED = "disconnected"
    """Our WebSocket or the CAN gateway was down."""
    UNAVAILABLE = "unavailable"
    """HA reported ``unavailable``/``unknown``."""


@dataclass(frozen=True, slots=True)
class ValueInterval:
    """``value`` holds during ``[start, end)``.

    One interval per accepted observation (intervals are not merged), so ``observed_at``
    (the evidence time of the backing observation) and ``origin`` stay available for
    sampling alignment and transition detection. ``start`` may be later than
    ``observed_at`` when the interval was clipped at the window start.
    """

    start: TimestampMs
    end: TimestampMs
    value: ObservedValue
    provenance: Provenance
    observed_at: TimestampMs
    origin: ObservationKind

    def __post_init__(self) -> None:
        _check_range(self.start, self.end, "ValueInterval")
        if self.observed_at >= self.end:
            raise ValueError("ValueInterval: observed_at must be before end")


@dataclass(frozen=True, slots=True)
class UnknownInterval:
    """The signal's value is unknown during ``[start, end)``. Never treated as 'off'."""

    start: TimestampMs
    end: TimestampMs
    reason: UnknownReason

    def __post_init__(self) -> None:
        _check_range(self.start, self.end, "UnknownInterval")


type TimelineInterval = ValueInterval | UnknownInterval


@dataclass(frozen=True, slots=True)
class SignalTimeline:
    """Gap-free partition of ``span`` for one signal into value and unknown intervals.

    Invariant (checked): ``intervals`` are sorted, non-overlapping, contiguous and cover
    exactly ``span``.
    """

    signal: SignalRef
    span: TimeRange
    intervals: tuple[TimelineInterval, ...]
    _starts: tuple[TimestampMs, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.intervals:
            raise ValueError("SignalTimeline must cover its span (no intervals given)")
        cursor = self.span.start
        for interval in self.intervals:
            if interval.start != cursor:
                raise ValueError(
                    f"SignalTimeline {self.signal}: gap or overlap at {cursor} "
                    f"(next interval starts at {interval.start})"
                )
            cursor = interval.end
        if cursor != self.span.end:
            raise ValueError(f"SignalTimeline {self.signal}: ends at {cursor}, span ends later")
        object.__setattr__(self, "_starts", tuple(i.start for i in self.intervals))

    @property
    def values(self) -> tuple[ValueInterval, ...]:
        return tuple(i for i in self.intervals if isinstance(i, ValueInterval))

    @property
    def unknowns(self) -> tuple[UnknownInterval, ...]:
        return tuple(i for i in self.intervals if isinstance(i, UnknownInterval))

    def at(self, ts: TimestampMs) -> TimelineInterval | None:
        """Interval containing ``ts``, or ``None`` outside the span."""
        if not self.span.contains(ts):
            return None
        return self.intervals[bisect.bisect_right(self._starts, ts) - 1]

    def value_at(self, ts: TimestampMs) -> ObservedValue | None:
        """Known value at ``ts``; ``None`` if unknown or outside the span."""
        interval = self.at(ts)
        return interval.value if isinstance(interval, ValueInterval) else None

    def overlapping(self, rng: TimeRange) -> Iterator[TimelineInterval]:
        """Intervals overlapping ``rng`` (unclipped), in time order."""
        first = max(bisect.bisect_right(self._starts, rng.start) - 1, 0)
        for interval in self.intervals[first:]:
            if interval.start >= rng.end:
                break
            if interval.end > rng.start:
                yield interval

    def known_ms(self, rng: TimeRange) -> DurationMs:
        """Milliseconds within ``rng`` with a known value."""
        total = 0
        for interval in self.overlapping(rng):
            if isinstance(interval, ValueInterval):
                total += min(interval.end, rng.end) - max(interval.start, rng.start)
        return total

    def coverage(self, rng: TimeRange) -> float:
        """Fraction of ``rng`` with a known value (time outside the span counts unknown)."""
        return self.known_ms(rng) / rng.duration_ms


class QualityEventKind(StrEnum):
    """Kinds of data-quality events (ADR-003 §8)."""

    DATA_GAP = "data_gap"
    """Signal has no data (``UnknownReason.NO_DATA``)."""
    STALE = "stale"
    """Heartbeat signal older than ``max_age`` (``UnknownReason.STALE``)."""
    INVALID = "invalid"
    IMPLAUSIBLE = "implausible"
    UNAVAILABLE = "unavailable"
    """HA reported ``unavailable``/``unknown``."""
    CONNECTION_LOST = "connection_lost"
    """A connection source was down; one event per source (``source``), not per signal."""
    COUNTER_RESET = "counter_reset"
    """Point event (``start == end``) where a cumulative counter decreased."""
    DUPLICATE = "duplicate"
    """Exact duplicate observations dropped; per signal per grid bucket, with ``count``."""
    MISALIGNED = "misaligned"
    """Two signals were combined (e.g. flow/return) with evidence times beyond tolerance."""


@dataclass(frozen=True, slots=True)
class QualityEvent:
    """Detected data-quality event. ``end is None`` while ongoing at the horizon.

    Deterministic key: :attr:`key` = ``(kind, signal, other_signal, source, start)``;
    interval events are split on the canonical grid (ADR-002 §4.5) and merged by readers.

    * ``source``: the connection source (only and always for ``CONNECTION_LOST``).
    * ``other_signal``: the second signal of a pair (only and always for ``MISALIGNED``).
    * ``count``: number of affected observations (required for ``DUPLICATE``).
    * ``detail``: short machine-readable detail, e.g. ``"derived"`` for a gateway outage
      inferred from stale heartbeat signals, or ``"1234.5->0.4"`` for a counter reset.
    """

    kind: QualityEventKind
    signal: SignalRef | None
    start: TimestampMs
    end: TimestampMs | None
    detail: str = ""
    final: bool = False
    source: ConnectionSource | None = None
    other_signal: SignalRef | None = None
    count: int | None = None

    def __post_init__(self) -> None:
        if self.end is not None and self.end < self.start:
            raise ValueError("QualityEvent: end before start")
        if self.end is None and self.final:
            raise ValueError("QualityEvent: an ongoing event cannot be final")
        if (self.kind is QualityEventKind.CONNECTION_LOST) != (self.source is not None):
            raise ValueError("QualityEvent: source is required for (only) CONNECTION_LOST")
        if self.kind is QualityEventKind.CONNECTION_LOST and self.signal is not None:
            raise ValueError("QualityEvent: CONNECTION_LOST is per source, not per signal")
        if (self.kind is QualityEventKind.MISALIGNED) != (self.other_signal is not None):
            raise ValueError("QualityEvent: other_signal is required for (only) MISALIGNED")
        if self.count is not None and self.count < 1:
            raise ValueError("QualityEvent: count must be >= 1")
        if self.kind is QualityEventKind.DUPLICATE and self.count is None:
            raise ValueError("QualityEvent: DUPLICATE requires a count")
        if self.kind is QualityEventKind.COUNTER_RESET and self.end != self.start:
            raise ValueError("QualityEvent: COUNTER_RESET is a point event (end == start)")

    @property
    def key(self) -> tuple[str, str, str, str, TimestampMs]:
        """Deterministic storage key ``(kind, signal, other_signal, source, start)``."""
        return (
            self.kind.value,
            "" if self.signal is None else str(self.signal),
            "" if self.other_signal is None else str(self.other_signal),
            "" if self.source is None else self.source.value,
            self.start,
        )


class Alignment(StrEnum):
    """Result of the sampling-tolerance check when combining two signals (ADR-002 §7)."""

    ALIGNED = "aligned"
    """Both evidence times within tolerance."""
    ASSUMED_UNCHANGED = "assumed_unchanged"
    """At least one signal reports only on change; its value is assumed to still hold."""
    MISALIGNED = "misaligned"
    """Evidence times differ more than the tolerance: not combined, quality event raised."""


@dataclass(frozen=True, slots=True)
class PairSample:
    """Two signal values at one instant plus the alignment verdict."""

    ts: TimestampMs
    a: ObservedValue | None
    b: ObservedValue | None
    alignment: Alignment | None
    """``None`` when either value is unknown (then the pair is unknown, not misaligned)."""


# --------------------------------------------------------------------------------------
# Modes (stage 3)
# --------------------------------------------------------------------------------------


class Mode(StrEnum):
    CH = "ch"
    """Central heating."""
    DHW = "dhw"
    """Domestic hot water."""
    STANDBY = "standby"
    AFTERRUN = "afterrun"
    FAULT_BLOCKING = "fault_blocking"
    UNKNOWN = "unknown"


class ModeCertainty(StrEnum):
    DIRECT = "direct"
    """From the operating-mode / status-code signal."""
    INFERRED = "inferred"
    """Inferred from flame, pump, demand and flow setpoint without a mode signal (limited)."""
    NONE = "none"
    """Mode is unknown."""


@dataclass(frozen=True, slots=True)
class ModeSegment:
    """Operating mode during ``[start, end)``; split on the canonical grid. Key: ``start``."""

    start: TimestampMs
    end: TimestampMs
    mode: Mode
    certainty: ModeCertainty
    sources: tuple[SignalRef, ...] = ()
    final: bool = False

    def __post_init__(self) -> None:
        _check_range(self.start, self.end, "ModeSegment")
        if (self.mode is Mode.UNKNOWN) != (self.certainty is ModeCertainty.NONE):
            raise ValueError("ModeSegment: mode UNKNOWN iff certainty NONE")


# --------------------------------------------------------------------------------------
# Burner cycles (stage 4)
# --------------------------------------------------------------------------------------


class EndReason(StrEnum):
    STOP_DURING_DEMAND = "stop_during_demand"
    DEMAND_ENDED = "demand_ended"
    DHW_ENDED = "dhw_ended"
    DATA_GAP = "data_gap"
    UNDETERMINED = "undetermined"
    """Flame-off was observed but heat demand around the stop is unknown or not mapped, so
    neither ``STOP_DURING_DEMAND`` nor ``DEMAND_ENDED`` can be claimed (FR-04, FR-16)."""


class CyclePhase(StrEnum):
    STARTUP = "startup"
    STABLE = "stable"
    AFTERRUN = "afterrun"


@dataclass(frozen=True, slots=True)
class PhaseSpan:
    """One phase of a cycle. ``AFTERRUN`` starts at flame-off and may end after the cycle."""

    phase: CyclePhase
    start: TimestampMs
    end: TimestampMs

    def __post_init__(self) -> None:
        _check_range(self.start, self.end, "PhaseSpan")


@dataclass(frozen=True, slots=True)
class CycleAggregates:
    """Per-cycle aggregates over the burning part. ``None`` = signal unknown / not mapped."""

    flow_setpoint_c: float | None = None
    flow_max_c: float | None = None
    flow_mean_c: float | None = None
    return_mean_c: float | None = None
    modulation_mean_pct: float | None = None
    modulation_min_pct: float | None = None
    heat_demand_during: bool | None = None
    heat_demand_after_stop: bool | None = None
    signal_coverage: float = 0.0
    """Fraction of the cycle where flow, return and modulation were all known."""

    def __post_init__(self) -> None:
        if not 0.0 <= self.signal_coverage <= 1.0:
            raise ValueError("CycleAggregates: signal_coverage must be within [0, 1]")


@dataclass(frozen=True, slots=True)
class BurnerCycle:
    """A burner period (FR-12). Deterministic key: ``start``.

    * ``end is None``: still burning at the horizon (open, provisional).
    * ``start_observed``: ``False`` if the burner was already on when data (re)appeared;
      such a cycle never counts as a start (FR-08).
    * ``complete``: both boundaries are observed transitions and the flame was known
      throughout. Incomplete durations are lower bounds (UI: "≥ 4:00").
    """

    start: TimestampMs
    end: TimestampMs | None
    duration_ms: DurationMs
    """Exact duration if complete, otherwise a lower bound."""
    complete: bool
    start_observed: bool
    mode: Mode
    end_reason: EndReason | None
    phases: tuple[PhaseSpan, ...] = ()
    aggregates: CycleAggregates = field(default_factory=CycleAggregates)
    pause_before_ms: DurationMs | None = None
    """Pause since the previous cycle's end if flame was known-off throughout and the pause is
    at most ``max_pause_ms``; else ``None``."""
    final: bool = False

    def __post_init__(self) -> None:
        if self.duration_ms < 0:
            raise ValueError("BurnerCycle: negative duration")
        if self.end is None:
            if self.end_reason is not None or self.complete or self.final:
                raise ValueError("BurnerCycle: an open cycle has no end reason and is provisional")
        else:
            if self.end <= self.start:
                raise ValueError("BurnerCycle: end must be after start")
            if self.end_reason is None:
                raise ValueError("BurnerCycle: a closed cycle needs an end reason")
            if self.complete and self.duration_ms != self.end - self.start:
                raise ValueError("BurnerCycle: complete cycle duration must equal end - start")
        if self.complete and (not self.start_observed or self.end_reason is EndReason.DATA_GAP):
            raise ValueError("BurnerCycle: complete requires observed start and end")
        if self.pause_before_ms is not None and self.pause_before_ms < 0:
            raise ValueError("BurnerCycle: negative pause")

    @property
    def counts_as_start(self) -> bool:
        return self.start_observed

    @property
    def key(self) -> TimestampMs:
        return self.start


# --------------------------------------------------------------------------------------
# Metrics (stage 5)
# --------------------------------------------------------------------------------------


class MetricName(StrEnum):
    STARTS = "starts"
    STARTS_PER_HOUR = "starts_per_hour"
    BURN_TIME = "burn_time"
    BURN_DURATION_MEAN = "burn_duration_mean"
    BURN_DURATION_MEDIAN = "burn_duration_median"
    SHORT_CYCLES = "short_cycles"
    SHORT_CYCLE_SHARE = "short_cycle_share"
    PAUSE_DURATION_MEDIAN = "pause_duration_median"
    OBSERVED_TIME = "observed_time"
    HEAT_DEMAND_TIME = "heat_demand_time"
    OVERSHOOT = "overshoot"
    HEATING_RATE = "heating_rate"
    BOILER_DELTA_T_STABLE = "boiler_delta_t_stable"
    FLOW_MEAN_STABLE = "flow_mean_stable"


class MetricWindowKind(StrEnum):
    HOUR = "hour"
    """UTC hour bucket (coincides with a local hour: Amsterdam offsets are whole hours)."""
    DAY = "day"
    """Europe/Amsterdam calendar day (23 h or 25 h on DST days)."""
    CYCLE = "cycle"
    """One burner cycle (or one of its phases)."""
    PERIOD = "period"
    """Arbitrary period, e.g. a before/after evaluation or a rolling 6 h window."""


@dataclass(frozen=True, slots=True)
class MetricWindow:
    kind: MetricWindowKind
    range: TimeRange
    cycle_start: TimestampMs | None = None
    """Key of the cycle for ``CYCLE`` windows."""

    def __post_init__(self) -> None:
        if (self.kind is MetricWindowKind.CYCLE) != (self.cycle_start is not None):
            raise ValueError("MetricWindow: cycle_start is required for (only) CYCLE windows")


@dataclass(frozen=True, slots=True)
class MetricValue:
    """A metric with its time basis and coverage (FR-11, FR-13).

    ``value is None`` when the time basis is insufficient. ``time_basis_seconds`` is the
    observed time the value is based on (e.g. observed CH-demand hours for starts per hour);
    ``coverage`` is ``time_basis / window length`` in ``[0, 1]``.
    Key: ``(name, mode, window.kind, window.range.start, window.cycle_start)``.
    """

    name: MetricName
    window: MetricWindow
    value: float | None
    unit: str
    time_basis_seconds: float
    coverage: float
    mode: Mode | None = None
    """Mode filter the metric was computed for (e.g. ``CH``), ``None`` = all."""
    provenance_kind: ValueKind = ValueKind.DERIVED
    final: bool = False

    def __post_init__(self) -> None:
        if self.time_basis_seconds < 0:
            raise ValueError("MetricValue: negative time basis")
        if not 0.0 <= self.coverage <= 1.0:
            raise ValueError("MetricValue: coverage must be within [0, 1]")
        if self.time_basis_seconds * 1000 > self.window.range.duration_ms + 1e-6:
            raise ValueError("MetricValue: time basis exceeds window length")


# --------------------------------------------------------------------------------------
# Configuration snapshot and result
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SignalConfig:
    """Per-signal settings from the signal mapping (store) as seen by the pipeline."""

    signal: SignalRef
    provenance: Provenance
    heartbeat_expected: bool = False
    """The integration reports this signal periodically even without change (HA
    ``last_reported`` advances), so its age is meaningful (ADR-003 §3)."""
    max_age_ms: DurationMs | None = None
    """Required with, and only used with, ``heartbeat_expected`` (ADR-003 §3)."""
    plausible_min: float | None = None
    plausible_max: float | None = None
    cumulative: bool = False
    via_can_gateway: bool = False

    def __post_init__(self) -> None:
        if self.heartbeat_expected and (self.max_age_ms is None or self.max_age_ms <= 0):
            raise ValueError("SignalConfig: heartbeat_expected requires a positive max_age_ms")


@dataclass(frozen=True, slots=True)
class PairTolerance:
    a: SignalRef
    b: SignalRef
    tolerance_ms: DurationMs


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Immutable configuration snapshot for one run. Part of the determinism contract:
    chunked == whole only holds for the same snapshot (``config_hash``)."""

    signals: tuple[SignalConfig, ...]
    mode_mapping: tuple[tuple[str, Mode], ...] = ()
    """Status/mode code → mode (Calenta Ace default after the CAN inventory, #5)."""
    pair_tolerances: tuple[PairTolerance, ...] = ()
    default_pair_tolerance_ms: DurationMs = 30_000
    lookback_ms: DurationMs = 6 * HOUR_MS
    settle_ms: DurationMs = 2 * MINUTE_MS
    grid_ms: DurationMs = HOUR_MS
    end_reason_lookahead_ms: DurationMs = MINUTE_MS
    max_pause_ms: DurationMs = HOUR_MS
    startup_max_ms: DurationMs = 3 * MINUTE_MS
    startup_flow_margin_k: float = 2.0
    afterrun_max_ms: DurationMs = 15 * MINUTE_MS
    derive_gateway_outage: bool = True
    """Treat the CAN gateway as down while *all* heartbeat signals ``via_can_gateway`` are
    stale (ADR-003 §5.3). No effect without such signals."""
    config_hash: str = ""

    def __post_init__(self) -> None:
        context_needed = max(self.max_pause_ms, self.afterrun_max_ms, self.startup_max_ms)
        if self.lookback_ms < context_needed + self.grid_ms:
            raise ValueError(
                "PipelineConfig: lookback_ms must be >= max stage context + grid_ms (ADR-002 §5)"
            )
        if self.end_reason_lookahead_ms > self.settle_ms:
            raise ValueError("PipelineConfig: end_reason_lookahead_ms must be <= settle_ms")
        if self.grid_ms <= 0 or (HOUR_MS % self.grid_ms and self.grid_ms % HOUR_MS):
            raise ValueError("PipelineConfig: grid_ms must divide or be a multiple of one hour")


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Output of one run: only items with key in ``[window.emit_from, window.end)``.

    The runner upserts them with replace-from semantics (delete derived rows with key
    ``>= emit_from``, insert these) in one transaction and stores ``next_watermark``.
    """

    window: AnalysisWindow
    next_watermark: TimestampMs
    timelines: tuple[SignalTimeline, ...]
    quality_events: tuple[QualityEvent, ...]
    mode_segments: tuple[ModeSegment, ...]
    cycles: tuple[BurnerCycle, ...]
    metrics: tuple[MetricValue, ...]
    config_hash: str = ""
