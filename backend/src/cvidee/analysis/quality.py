"""Stage 2 — data quality: plausibility, counter resets, alignment, coverage (ADR-002 §3.2).

FR-07, FR-08, FR-11. Pure: no I/O, no wall clock.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from cvidee.analysis.timeline import ConnectionOutages
from cvidee.analysis.types import (
    HOUR_MS,
    Alignment,
    AnalysisWindow,
    ConnectionSource,
    DurationMs,
    Observation,
    ObservationKind,
    ObservedValue,
    PairSample,
    PipelineConfig,
    Provenance,
    QualityEvent,
    QualityEventKind,
    Role,
    SignalConfig,
    SignalRef,
    SignalTimeline,
    TimelineInterval,
    TimeRange,
    TimestampMs,
    UnknownInterval,
    UnknownReason,
    ValueInterval,
    ValueKind,
    floor_to_grid,
)

DEFAULT_PLAUSIBILITY: dict[Role, tuple[float | None, float | None]] = {
    Role.FLOW_SETPOINT: (-10.0, 120.0),
    Role.FLOW_TEMPERATURE: (-10.0, 120.0),
    Role.RETURN_TEMPERATURE: (-10.0, 120.0),
    Role.MODULATION: (0.0, 100.0),
    Role.ROOM_TEMPERATURE: (-10.0, 45.0),
    Role.ROOM_SETPOINT: (4.0, 35.0),
    Role.OUTDOOR_TEMPERATURE: (-40.0, 55.0),
    Role.GAS_CUMULATIVE: (0.0, None),
    Role.MANIFOLD_FLOW_TEMPERATURE: (-10.0, 120.0),
    Role.MANIFOLD_RETURN_TEMPERATURE: (-10.0, 120.0),
    Role.FLOW_RATE: (0.0, 10_000.0),
    Role.HEAT_METER: (0.0, None),
}
"""Plausibility bounds per role, used for a bound the signal config leaves ``None``."""

_BOOLEAN_ROLES = frozenset({Role.FLAME, Role.HEAT_DEMAND, Role.ZONE_DEMAND, Role.PUMP_STATE})
_FREE_ROLES = frozenset({Role.OPERATING_MODE, Role.VALVE_STATE})
RESOLUTION_WINDOW_MS: DurationMs = 24 * HOUR_MS
"""Look-back for the median update interval (ADR-003 §3.2)."""


@dataclass(frozen=True, slots=True)
class QualityResult:
    """Timelines after quality checks plus the detected events."""

    timelines: tuple[SignalTimeline, ...]
    events: tuple[QualityEvent, ...]


def plausible_bounds(cfg: SignalConfig) -> tuple[float | None, float | None]:
    """Effective plausibility bounds: configured value, else the role default."""
    d_min, d_max = DEFAULT_PLAUSIBILITY.get(cfg.signal.role, (None, None))
    return (
        d_min if cfg.plausible_min is None else cfg.plausible_min,
        d_max if cfg.plausible_max is None else cfg.plausible_max,
    )


def _fmt(value: float | None) -> str:
    return "" if value is None else f"{value:g}"


def _type_ok(role: Role, value: ObservedValue) -> bool:
    if role in _BOOLEAN_ROLES:
        return isinstance(value, bool)
    if role in _FREE_ROLES:
        return True
    return isinstance(value, float | int) and not isinstance(value, bool) and math.isfinite(value)


def _split_on_grid(start: TimestampMs, end: TimestampMs, grid_ms: DurationMs) -> list[TimeRange]:
    pieces: list[TimeRange] = []
    cursor = start
    while cursor < end:
        boundary = min(floor_to_grid(cursor, grid_ms) + grid_ms, end)
        pieces.append(TimeRange(cursor, boundary))
        cursor = boundary
    return pieces


def _interval_events(
    kind: QualityEventKind,
    start: TimestampMs,
    end: TimestampMs,
    window: AnalysisWindow,
    grid_ms: DurationMs,
    *,
    signal: SignalRef | None = None,
    source: ConnectionSource | None = None,
    detail: str = "",
) -> list[QualityEvent]:
    """One event per grid bucket; the last gets ``end=None`` if it runs to the horizon."""
    events: list[QualityEvent] = []
    for piece in _split_on_grid(start, end, grid_ms):
        ongoing = piece.end == window.end and end == window.end
        events.append(
            QualityEvent(
                kind=kind,
                signal=signal,
                start=piece.start,
                end=None if ongoing else piece.end,
                detail=detail,
                source=source,
            )
        )
    return events


_UNKNOWN_KIND = {
    UnknownReason.NO_DATA: QualityEventKind.DATA_GAP,
    UnknownReason.STALE: QualityEventKind.STALE,
    UnknownReason.INVALID: QualityEventKind.INVALID,
    UnknownReason.IMPLAUSIBLE: QualityEventKind.IMPLAUSIBLE,
    UnknownReason.UNAVAILABLE: QualityEventKind.UNAVAILABLE,
}


def _check_value(cfg: SignalConfig, interval: ValueInterval) -> tuple[UnknownReason, str] | None:
    """Reason and detail if the value is invalid or implausible, else ``None``."""
    value = interval.value
    if not _type_ok(cfg.signal.role, value):
        return UnknownReason.INVALID, str(value)[:40]
    if isinstance(value, float | int) and not isinstance(value, bool):
        low, high = plausible_bounds(cfg)
        if (low is not None and value < low) or (high is not None and value > high):
            return UnknownReason.IMPLAUSIBLE, f"{_fmt(low)}..{_fmt(high)}"
    return None


def apply_quality(
    timelines: Sequence[SignalTimeline],
    config: PipelineConfig,
    window: AnalysisWindow,
    outages: ConnectionOutages | None = None,
) -> QualityResult:
    """Apply quality rules to the stage-1 timelines.

    * Values outside ``[plausible_min, plausible_max]`` (role defaults for unset bounds,
      :data:`DEFAULT_PLAUSIBILITY`) become ``UnknownInterval(IMPLAUSIBLE)``; values of the
      wrong type become ``INVALID``.
    * Every unknown interval yields a :class:`QualityEvent` (kind from its reason;
      consecutive intervals with the same reason form one event), split on the canonical
      grid (``config.grid_ms``) with key ``(kind, signal, other_signal, source, start)``.
      An event still open at ``window.end`` has ``end=None``. ``DISCONNECTED`` yields no
      per-signal event: ``CONNECTION_LOST`` is reported once per source from ``outages``
      (the result of :func:`cvidee.analysis.timeline.build_stage1`).
    * Counter resets (:func:`detect_counter_resets`) are reported, never turned into
      negative consumption.
    * Misaligned combinations are detected by consumers via :func:`align_pair` (they know
      which combinations they need) and reported with :func:`misaligned_events`.
    * Duplicates are reported by :func:`duplicate_events` (stage 1 drops them silently).

    ``final`` flags are left ``False``; the pipeline sets them from the next watermark.
    """
    configs = {c.signal: c for c in config.signals}
    out_timelines: list[SignalTimeline] = []
    events: list[QualityEvent] = []
    for timeline in timelines:
        cfg = configs.get(timeline.signal) or SignalConfig(
            timeline.signal, provenance=_dummy_provenance(timeline)
        )
        intervals: list[TimelineInterval] = []
        details: dict[int, str] = {}
        for interval in timeline.intervals:
            if isinstance(interval, ValueInterval):
                problem = _check_value(cfg, interval)
                if problem is not None:
                    reason, detail = problem
                    details[len(intervals)] = detail
                    intervals.append(UnknownInterval(interval.start, interval.end, reason))
                    continue
            intervals.append(interval)
        # merge adjacent unknowns with the same reason (keeping the first detail)
        merged: list[TimelineInterval] = []
        merged_details: list[str] = []
        for index, interval in enumerate(intervals):
            last = merged[-1] if merged else None
            if (
                isinstance(interval, UnknownInterval)
                and isinstance(last, UnknownInterval)
                and last.reason is interval.reason
            ):
                merged[-1] = UnknownInterval(last.start, interval.end, last.reason)
                continue
            merged.append(interval)
            merged_details.append(details.get(index, ""))
        new = SignalTimeline(timeline.signal, timeline.span, tuple(merged))
        out_timelines.append(new)
        for interval, detail in zip(merged, merged_details, strict=True):
            if not isinstance(interval, UnknownInterval):
                continue
            kind = _UNKNOWN_KIND.get(interval.reason)
            if kind is None:
                continue
            if interval.reason is UnknownReason.STALE and cfg.max_age_ms is not None:
                detail = f"max_age_s={cfg.max_age_ms / 1000:g}"
            events.extend(
                _interval_events(
                    kind,
                    interval.start,
                    interval.end,
                    window,
                    config.grid_ms,
                    signal=timeline.signal,
                    detail=detail,
                )
            )
        if cfg.cumulative:
            events.extend(detect_counter_resets(new))
    if outages is not None:
        events.extend(connection_events(outages, config, window))
    events.sort(key=lambda e: (e.start, e.key))
    return QualityResult(tuple(out_timelines), tuple(events))


def _dummy_provenance(timeline: SignalTimeline) -> Provenance:
    return Provenance(ValueKind.MEASURED, str(timeline.signal))


def connection_events(
    outages: ConnectionOutages, config: PipelineConfig, window: AnalysisWindow
) -> list[QualityEvent]:
    """``CONNECTION_LOST`` events: one per source (not per signal), split on the grid.

    Derived gateway outages carry ``detail="derived"``. ``HISTORY`` yields no event."""
    events: list[QualityEvent] = []
    groups = (
        (ConnectionSource.WS, outages.ws, ""),
        (ConnectionSource.CAN_GATEWAY, outages.gateway, ""),
        (ConnectionSource.CAN_GATEWAY, outages.derived_gateway, "derived"),
    )
    for source, ranges, detail in groups:
        for rng in ranges:
            events.extend(
                _interval_events(
                    QualityEventKind.CONNECTION_LOST,
                    rng.start,
                    rng.end,
                    window,
                    config.grid_ms,
                    source=source,
                    detail=detail,
                )
            )
    return events


def duplicate_events(
    observations: Sequence[Observation], config: PipelineConfig, window: AnalysisWindow
) -> tuple[QualityEvent, ...]:
    """``DUPLICATE`` events: exact ``(signal, ts, value)`` duplicates, one event per signal
    per grid bucket with ``count`` = number of dropped observations."""
    ctx = window.context
    if ctx is None:
        return ()
    configured = {c.signal for c in config.signals}
    groups: dict[tuple[SignalRef, TimestampMs, str], int] = defaultdict(int)
    for obs in observations:
        if obs.signal in configured and ctx.contains(obs.ts):
            groups[(obs.signal, obs.ts, repr(obs.value))] += 1
    counts: dict[tuple[SignalRef, TimestampMs], int] = defaultdict(int)
    for (signal, ts, _), n in groups.items():
        if n > 1:
            counts[(signal, floor_to_grid(ts, config.grid_ms))] += n - 1
    events = [
        QualityEvent(
            QualityEventKind.DUPLICATE,
            signal,
            bucket,
            bucket + config.grid_ms,
            count=n,
        )
        for (signal, bucket), n in counts.items()
    ]
    return tuple(sorted(events, key=lambda e: (e.start, e.key)))


@dataclass(frozen=True, slots=True)
class CounterSegment:
    """A run of a cumulative counter without reset: consumption is ``last - first`` (>= 0)."""

    start: TimestampMs
    end: TimestampMs
    first: float
    last: float

    @property
    def consumption(self) -> float:
        return self.last - self.first


def _counter_values(timeline: SignalTimeline) -> list[ValueInterval]:
    return [
        i
        for i in timeline.intervals
        if isinstance(i, ValueInterval)
        and isinstance(i.value, float | int)
        and not isinstance(i.value, bool)
    ]


def counter_segments(timeline: SignalTimeline) -> tuple[CounterSegment, ...]:
    """Split a cumulative counter at its resets. Consumption across a reset is never
    negative: it is counted per segment (FR-08)."""
    segments: list[CounterSegment] = []
    current: CounterSegment | None = None
    for interval in _counter_values(timeline):
        value = float(interval.value)
        if current is None or value < current.last:
            if current is not None:
                segments.append(current)
            current = CounterSegment(interval.start, interval.end, value, value)
        else:
            current = CounterSegment(current.start, interval.end, current.first, value)
    if current is not None:
        segments.append(current)
    return tuple(segments)


def counter_consumption(timeline: SignalTimeline) -> float:
    """Total consumption of a cumulative counter over the timeline, never negative."""
    return sum(s.consumption for s in counter_segments(timeline))


def detect_counter_resets(timeline: SignalTimeline) -> tuple[QualityEvent, ...]:
    """Detect resets of a cumulative counter (e.g. gas): a decrease starts a new segment.

    Consumption across a reset is computed per segment (FR-08: never negative); see
    :func:`counter_segments`. A reset is a point event at the start of the lower value.
    """
    events: list[QualityEvent] = []
    previous: ValueInterval | None = None
    for interval in _counter_values(timeline):
        if previous is not None and float(interval.value) < float(previous.value):
            events.append(
                QualityEvent(
                    QualityEventKind.COUNTER_RESET,
                    timeline.signal,
                    interval.start,
                    interval.start,
                    detail=f"{float(previous.value)!r}->{float(interval.value)!r}",
                )
            )
        previous = interval
    return tuple(events)


def pair_tolerance(config: PipelineConfig, a: SignalRef, b: SignalRef) -> DurationMs:
    """Sampling tolerance for combining ``a`` and ``b`` (order-insensitive); falls back to
    ``config.default_pair_tolerance_ms``."""
    for pair in config.pair_tolerances:
        if {pair.a, pair.b} == {a, b}:
            return pair.tolerance_ms
    return config.default_pair_tolerance_ms


def _evidence(timeline: SignalTimeline, ts: TimestampMs) -> tuple[TimestampMs, TimestampMs] | None:
    """``(E, C)`` of the signal at ``ts`` (ADR-003 §8), ``None`` if unknown there."""
    interval = timeline.at(ts)
    if not isinstance(interval, ValueInterval):
        return None
    if interval.origin is not ObservationKind.CONFIRM:
        return interval.observed_at, interval.observed_at
    for candidate in reversed(timeline.intervals):
        if (
            isinstance(candidate, ValueInterval)
            and candidate.start <= ts
            and candidate.origin is not ObservationKind.CONFIRM
        ):
            return interval.observed_at, candidate.observed_at
    return interval.observed_at, interval.observed_at


def _verdict(
    a: SignalTimeline,
    b: SignalTimeline,
    ts: TimestampMs,
    tolerance_ms: DurationMs,
    a_heartbeat: bool,
    b_heartbeat: bool,
) -> tuple[Alignment, int] | None:
    """Alignment and skew in ms at ``ts``; ``None`` if either signal is unknown."""
    ea = _evidence(a, ts)
    eb = _evidence(b, ts)
    if ea is None or eb is None:
        return None
    (e_a, c_a), (e_b, c_b) = ea, eb
    if a_heartbeat and b_heartbeat:
        skew = abs(e_a - e_b)
        return (Alignment.ALIGNED if skew <= tolerance_ms else Alignment.MISALIGNED), skew
    skew = 0
    if not a_heartbeat:
        skew = max(skew, c_b - e_a)
    if not b_heartbeat:
        skew = max(skew, c_a - e_b)
    return (Alignment.MISALIGNED if skew > tolerance_ms else Alignment.ASSUMED_UNCHANGED), skew


def align_pair(
    a: SignalTimeline,
    b: SignalTimeline,
    ts: TimestampMs,
    tolerance_ms: DurationMs,
    *,
    a_heartbeat: bool,
    b_heartbeat: bool,
) -> PairSample:
    """Sample two signals at ``ts`` and judge whether they may be combined (FR-07).

    * Either value unknown → ``alignment=None`` (the pair is unknown, not misaligned).
    * Both heartbeat signals and ``|observed_at_a - observed_at_b| <= tolerance_ms`` →
      ``ALIGNED``.
    * Both heartbeat signals beyond tolerance → ``MISALIGNED``: callers must not combine
      the values and report a ``QualityEvent(MISALIGNED)``.
    * At least one change-only signal → ``ASSUMED_UNCHANGED`` (combined, weaker certainty),
      unless the change-only value is older than the other signal's last *change* by more
      than the tolerance while the other one changed (then ``MISALIGNED``) — see ADR-002 §7.

    Formally (ADR-003 §7): with ``E`` = ``observed_at`` of the interval at ``ts`` and ``C`` =
    ``observed_at`` of the latest interval at or before ``ts`` with origin ``CHANGE`` or
    ``POLL``: for a change-only ``x`` and the other signal ``y``, ``C_y - E_x > tolerance``
    → ``MISALIGNED``. Callers pass ``*_heartbeat=False`` for intervals inside ``HISTORY``
    coverage (no confirmations there).
    """
    verdict = _verdict(a, b, ts, tolerance_ms, a_heartbeat, b_heartbeat)
    return PairSample(ts, a.value_at(ts), b.value_at(ts), None if verdict is None else verdict[0])


def misaligned_events(
    a: SignalTimeline,
    b: SignalTimeline,
    rng: TimeRange,
    tolerance_ms: DurationMs,
    window: AnalysisWindow,
    grid_ms: DurationMs,
    *,
    a_heartbeat: bool,
    b_heartbeat: bool,
) -> tuple[QualityEvent, ...]:
    """``MISALIGNED`` events for combining ``a`` and ``b`` over ``rng`` (ADR-003 §8).

    Samples at ``rng.start`` and every interval boundary of ``a`` or ``b`` inside ``rng``.
    Consecutive misaligned samples form one event (from the first misaligned sample to the
    end of the last one's sample interval), split on the grid; ``detail`` is
    ``max_skew_ms=<n>`` over the event. ``a``/``b`` are ordered by ``SignalRef``.
    """
    if b.signal < a.signal:
        a, b = b, a
        a_heartbeat, b_heartbeat = b_heartbeat, a_heartbeat
    points = {rng.start}
    for tl in (a, b):
        for interval in tl.intervals:
            if rng.start < interval.start < rng.end:
                points.add(interval.start)
    ordered = sorted(points)
    runs: list[tuple[TimestampMs, TimestampMs, int]] = []
    for index, ts in enumerate(ordered):
        sample_end = ordered[index + 1] if index + 1 < len(ordered) else rng.end
        verdict = _verdict(a, b, ts, tolerance_ms, a_heartbeat, b_heartbeat)
        if verdict is None or verdict[0] is not Alignment.MISALIGNED:
            continue
        if runs and runs[-1][1] == ts:
            runs[-1] = (runs[-1][0], sample_end, max(runs[-1][2], verdict[1]))
        else:
            runs.append((ts, sample_end, verdict[1]))
    events: list[QualityEvent] = []
    for start, end, skew in runs:
        for piece in _split_on_grid(start, end, grid_ms):
            ongoing = piece.end == window.end and end == window.end
            events.append(
                QualityEvent(
                    QualityEventKind.MISALIGNED,
                    a.signal,
                    piece.start,
                    None if ongoing else piece.end,
                    detail=f"max_skew_ms={skew}",
                    other_signal=b.signal,
                )
            )
    return tuple(events)


def coverage_by_signal(
    timelines: Sequence[SignalTimeline], window: AnalysisWindow
) -> dict[SignalRef, float]:
    """Known fraction per signal over ``[window.emit_from, window.end)`` (FR-11)."""
    if window.emit_from >= window.end:
        return {tl.signal: 0.0 for tl in timelines}
    rng = TimeRange(window.emit_from, window.end)
    return {tl.signal: tl.coverage(rng) for tl in timelines}


def update_interval_median_ms(
    observations: Sequence[Observation], signal: SignalRef, window: AnalysisWindow
) -> DurationMs | None:
    """Resolution of a signal: median interval between successive ``CHANGE``/``CONFIRM``
    observations over the last 24 h before ``window.end`` (ADR-003 §3.2), or ``None`` if
    there are fewer than two."""
    low = window.end - RESOLUTION_WINDOW_MS
    stamps = sorted(
        {
            o.ts
            for o in observations
            if o.signal == signal
            and o.kind is not ObservationKind.POLL
            and low <= o.ts < window.end
        }
    )
    if len(stamps) < 2:
        return None
    return round(statistics.median(b - a for a, b in pairwise(stamps)))
