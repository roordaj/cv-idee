"""Stage 4 — burner cycles (ADR-002 §3.4, FR-12, FR-15, FR-16).

Pure: no I/O, no wall clock. Every function only looks at the timelines and mode segments it
is given and at ``window``; the result does not depend on input order.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from cvidee.analysis.types import (
    AnalysisWindow,
    BurnerCycle,
    CycleAggregates,
    CyclePhase,
    DurationMs,
    EndReason,
    Mode,
    ModeSegment,
    ObservationKind,
    ObservedValue,
    PhaseSpan,
    PipelineConfig,
    Role,
    SignalRef,
    SignalTimeline,
    TimeRange,
    TimestampMs,
    ValueInterval,
)

FLAME = SignalRef(Role.FLAME)
HEAT_DEMAND = SignalRef(Role.HEAT_DEMAND)
FLOW = SignalRef(Role.FLOW_TEMPERATURE)
RETURN = SignalRef(Role.RETURN_TEMPERATURE)
FLOW_SETPOINT = SignalRef(Role.FLOW_SETPOINT)
MODULATION = SignalRef(Role.MODULATION)

_TRUE_STRINGS = frozenset({"on", "true", "1"})
_FALSE_STRINGS = frozenset({"off", "false", "0"})


# --------------------------------------------------------------------------------------
# Value helpers
# --------------------------------------------------------------------------------------


def _as_bool(value: ObservedValue) -> bool | None:
    """Binary interpretation of a normalised value; ``None`` if it is not binary."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return None if math.isnan(value) else value != 0
    lowered = value.strip().lower()
    if lowered in _TRUE_STRINGS:
        return True
    if lowered in _FALSE_STRINGS:
        return False
    return None


def _as_float(value: ObservedValue) -> float | None:
    """Numeric interpretation of a normalised value; ``None`` for non-numeric values."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return None if math.isnan(number) else number


def _find(timelines: Iterable[SignalTimeline], signal: SignalRef) -> SignalTimeline | None:
    for timeline in timelines:
        if timeline.signal == signal:
            return timeline
    return None


@dataclass(frozen=True, slots=True)
class _Piece:
    """A clipped ``[start, end)`` part of a timeline with its value (``None`` = unknown)."""

    start: TimestampMs
    end: TimestampMs
    value: ObservedValue | None


def _pieces(timeline: SignalTimeline | None, rng: TimeRange) -> list[_Piece]:
    """``rng`` partitioned by ``timeline``; time outside the span (or no timeline) is unknown."""
    if timeline is None:
        return [_Piece(rng.start, rng.end, None)]
    pieces: list[_Piece] = []
    cursor = rng.start
    for interval in timeline.overlapping(rng):
        start, end = max(interval.start, rng.start), min(interval.end, rng.end)
        if start > cursor:
            pieces.append(_Piece(cursor, start, None))
        value = interval.value if isinstance(interval, ValueInterval) else None
        pieces.append(_Piece(start, end, value))
        cursor = end
    if cursor < rng.end:
        pieces.append(_Piece(cursor, rng.end, None))
    return pieces


def _binary_over(timeline: SignalTimeline | None, rng: TimeRange) -> bool | None:
    """``True`` if known-true throughout ``rng``, ``False`` if known-false at some point,
    ``None`` otherwise (unknown somewhere and never known-false)."""
    states = [None if p.value is None else _as_bool(p.value) for p in _pieces(timeline, rng)]
    if False in states:
        return False
    if all(s is True for s in states):
        return True
    return None


# --------------------------------------------------------------------------------------
# Stage entry point
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Run:
    """A maximal run of known flame-on time within the analysed range."""

    start: TimestampMs
    end: TimestampMs
    start_observed: bool
    stop_observed: bool
    """The run ended at a known flame-off with ``origin == CHANGE``."""
    open: bool
    """The flame was still on at the end of the analysed range."""
    known_off_before: bool
    """The flame was known-off since the previous run ended (no unknown time in between)."""


def _flame_runs(flame: SignalTimeline, rng: TimeRange) -> list[_Run]:
    runs: list[_Run] = []
    intervals = [(max(i.start, rng.start), min(i.end, rng.end), i) for i in flame.overlapping(rng)]
    run_start: TimestampMs | None = None
    start_observed = False
    known_off_before = False
    prev_known_off = False
    """Whether the interval just before the current one was a known flame-off."""
    off_since_run = False
    """Known-off without any unknown time since the previous run ended."""
    have_prev_run = False

    for start, _end, interval in intervals:
        state = _as_bool(interval.value) if isinstance(interval, ValueInterval) else None
        if state is True:
            if run_start is None:
                run_start = start
                start_observed = (
                    prev_known_off
                    and isinstance(interval, ValueInterval)
                    and interval.origin is ObservationKind.CHANGE
                )
                known_off_before = have_prev_run and off_since_run
            prev_known_off = False
            continue
        if run_start is not None:
            stop_observed = (
                state is False
                and isinstance(interval, ValueInterval)
                and interval.origin is ObservationKind.CHANGE
            )
            runs.append(
                _Run(run_start, start, start_observed, stop_observed, False, known_off_before)
            )
            run_start = None
            have_prev_run = True
            # Pauses are only measured from an observed stop.
            off_since_run = stop_observed
        if state is False:
            prev_known_off = True
        else:
            prev_known_off = False
            off_since_run = False

    if run_start is not None:
        runs.append(_Run(run_start, rng.end, start_observed, False, True, known_off_before))
    return runs


def _cycle_mode(burning: TimeRange, modes: Sequence[ModeSegment]) -> Mode:
    overlapping = {m.mode for m in modes if m.start < burning.end and burning.start < m.end}
    if Mode.DHW in overlapping:
        return Mode.DHW
    if Mode.CH in overlapping:
        return Mode.CH
    return Mode.UNKNOWN


def detect_cycles(
    timelines: Sequence[SignalTimeline],
    modes: Sequence[ModeSegment],
    config: PipelineConfig,
    window: AnalysisWindow,
) -> tuple[BurnerCycle, ...]:
    """Reconstruct burner cycles from the flame timeline.

    * Start: a flame-on ``ValueInterval`` with ``origin == CHANGE`` directly preceded by a
      known flame-off interval → ``start_observed=True``. Flame on after unknown time, at the
      window start, or from a ``POLL``/``CONFIRM`` → a cycle with ``start_observed=False``
      (no artificial start after reconnect, FR-08).
    * End: first known flame-off → ``end`` with an :class:`EndReason` from
      :func:`classify_end_reason`. Flame becomes unknown while on → ``end`` = start of the
      unknown interval, ``end_reason=DATA_GAP``, ``complete=False`` and the duration is a
      lower bound. Still on at ``window.end`` → ``end=None`` (open, provisional) with
      duration ``window.end - start`` as lower bound.
    * A flame-off that is only seen via a ``POLL``/``CONFIRM`` right after flame-on is not an
      observed transition either: the cycle ends there with ``DATA_GAP`` (known burning time
      as lower bound).
    * Mode: ``DHW`` if any DHW segment overlaps the burning part, else ``CH`` if CH
      overlaps, else ``UNKNOWN``.
    * ``pause_before_ms``: only if the previous cycle ended at most ``config.max_pause_ms``
      earlier and the flame was known-off in between; otherwise ``None``. Both boundaries of
      the pause must be observed transitions (previous stop and this start).
    * Phases via :func:`cycle_phases`, aggregates via :func:`cycle_aggregates`;
      ``heat_demand_after_stop`` is only set for an observed stop (same evidence as the end
      reason).

    All cycles in ``window.context`` are returned (also those keyed before
    ``window.emit_from``, which the pipeline drops); a cycle burning at
    ``window.context_start`` is clipped there and has ``start_observed=False``.

    Returns:
        Cycles sorted by ``start``; ``final`` flags are set by the pipeline.
    """
    rng = window.context
    flame = _find(timelines, FLAME)
    if rng is None or flame is None:
        return ()
    demand = _find(timelines, HEAT_DEMAND)
    flow = _find(timelines, FLOW)
    setpoint = _find(timelines, FLOW_SETPOINT)
    ordered_modes = sorted(modes, key=lambda m: (m.start, m.end))

    cycles: list[BurnerCycle] = []
    previous_end: TimestampMs | None = None
    for run in _flame_runs(flame, rng):
        burning = TimeRange(run.start, run.end)
        mode = _cycle_mode(burning, ordered_modes)
        end: TimestampMs | None
        if run.open:
            end, end_reason = None, None
        elif run.stop_observed:
            end, end_reason = run.end, classify_end_reason(run.end, mode, demand, config)
        else:
            end, end_reason = run.end, EndReason.DATA_GAP
        complete = run.start_observed and run.stop_observed

        pause: DurationMs | None = None
        if (
            run.start_observed
            and run.known_off_before
            and previous_end is not None
            and run.start - previous_end <= config.max_pause_ms
        ):
            pause = run.start - previous_end

        aggregates = cycle_aggregates(burning, timelines, config)
        if run.stop_observed:
            after = _binary_over(
                demand, TimeRange(run.end, run.end + config.end_reason_lookahead_ms)
            )
            aggregates = dataclasses.replace(aggregates, heat_demand_after_stop=after)

        phases = cycle_phases(burning, flow, setpoint, ordered_modes, config)
        if not run.stop_observed:
            # No observed flame-off: an afterrun cannot be attributed to this cycle.
            phases = tuple(p for p in phases if p.phase is not CyclePhase.AFTERRUN)

        cycles.append(
            BurnerCycle(
                start=run.start,
                end=end,
                duration_ms=run.end - run.start,
                complete=complete,
                start_observed=run.start_observed,
                mode=mode,
                end_reason=end_reason,
                phases=phases,
                aggregates=aggregates,
                pause_before_ms=pause,
            )
        )
        previous_end = run.end
    return tuple(cycles)


def cycle_settles_at(cycle: BurnerCycle, config: PipelineConfig) -> TimestampMs | None:
    """Earliest horizon from which ``cycle`` no longer changes when more data arrives.

    ``None`` for an open cycle. Otherwise ``end`` plus the furthest look past the end that
    this stage does: the end-reason lookahead and the afterrun phase (at most
    ``afterrun_max_ms``). The pipeline treats a cycle as non-final while
    ``cycle_settles_at(...) > window.end`` (extends ADR-002 §4.3, which only names the
    lookahead).
    """
    if cycle.end is None:
        return None
    return cycle.end + max(config.end_reason_lookahead_ms, config.afterrun_max_ms)


# --------------------------------------------------------------------------------------
# End reason, phases and aggregates
# --------------------------------------------------------------------------------------


def classify_end_reason(
    stop: TimestampMs,
    mode: Mode,
    heat_demand: SignalTimeline | None,
    config: PipelineConfig,
) -> EndReason:
    """Why the burner stopped at the observed flame-off transition ``stop``.

    * ``DHW`` cycle → ``DHW_ENDED``.
    * Heat demand known and present throughout
      ``[stop, stop + config.end_reason_lookahead_ms)`` → ``STOP_DURING_DEMAND``.
    * Heat demand known and absent at some point in that range (ended at or before the stop
      within the lookahead) → ``DEMAND_ENDED``.
    * Heat demand unknown around the stop or not mapped → ``UNDETERMINED``: rules never
      claim a stop during demand without evidence (ADR-002 §3.4).

    Time beyond the timeline's span (e.g. after the horizon) counts as unknown.
    ``DATA_GAP`` is never returned here; it is assigned when the flame itself is unknown.
    """
    if mode is Mode.DHW:
        return EndReason.DHW_ENDED
    lookahead = max(config.end_reason_lookahead_ms, 1)
    demand = _binary_over(heat_demand, TimeRange(stop, stop + lookahead))
    if demand is True:
        return EndReason.STOP_DURING_DEMAND
    if demand is False:
        return EndReason.DEMAND_ENDED
    return EndReason.UNDETERMINED


def _startup_end(
    cycle_range: TimeRange,
    flow: SignalTimeline | None,
    flow_setpoint: SignalTimeline | None,
    config: PipelineConfig,
) -> TimestampMs:
    limit = min(cycle_range.end, cycle_range.start + config.startup_max_ms)
    if limit <= cycle_range.start or flow is None or flow_setpoint is None:
        return limit
    rng = TimeRange(cycle_range.start, limit)
    boundaries = sorted(
        {rng.start}
        | {p.start for p in _pieces(flow, rng)}
        | {p.start for p in _pieces(flow_setpoint, rng)}
    )
    for ts in boundaries:
        flow_c = flow.value_at(ts)
        setpoint_c = flow_setpoint.value_at(ts)
        if flow_c is None or setpoint_c is None:
            continue
        f, s = _as_float(flow_c), _as_float(setpoint_c)
        if f is not None and s is not None and f >= s - config.startup_flow_margin_k:
            return ts
    return limit


def _afterrun_end(
    stop: TimestampMs, modes: Sequence[ModeSegment], config: PipelineConfig
) -> TimestampMs | None:
    """End of the contiguous ``AFTERRUN`` mode run that starts within the end-reason
    lookahead after ``stop`` (or already covers ``stop``); ``None`` if there is none."""
    ordered = sorted(modes, key=lambda m: (m.start, m.end))
    latest_begin = stop + config.end_reason_lookahead_ms
    cap = stop + config.afterrun_max_ms
    end: TimestampMs | None = None
    for segment in ordered:
        if segment.end <= stop:
            continue
        if end is None:
            if segment.start > latest_begin:
                break
            if segment.mode is Mode.AFTERRUN:
                end = segment.end
            continue
        if segment.start == end and segment.mode is Mode.AFTERRUN:
            end = segment.end
        elif segment.start >= end:
            break
    if end is None:
        return None
    return min(end, cap)


def cycle_phases(
    cycle_range: TimeRange,
    flow: SignalTimeline | None,
    flow_setpoint: SignalTimeline | None,
    modes: Sequence[ModeSegment],
    config: PipelineConfig,
) -> tuple[PhaseSpan, ...]:
    """Split a cycle into phases (FR-15).

    * ``STARTUP``: from start until flow reaches ``setpoint - startup_flow_margin_k`` or
      ``startup_max_ms`` has elapsed, whichever comes first. Unknown flow or setpoint never
      ends the startup early (conservative: startup is never counted as stable). Absent
      if the flow is already at the threshold at the start.
    * ``STABLE``: rest of the burning part (absent for very short cycles).
    * ``AFTERRUN``: from flame-off (``cycle_range.end``) while the mode is ``AFTERRUN``
      (may extend past the cycle end, at most ``afterrun_max_ms``). The afterrun mode may
      begin up to ``end_reason_lookahead_ms`` after the flame-off, because the mode signal
      and the flame signal are reported separately.
    """
    phases: list[PhaseSpan] = []
    startup_end = _startup_end(cycle_range, flow, flow_setpoint, config)
    if startup_end > cycle_range.start:
        phases.append(PhaseSpan(CyclePhase.STARTUP, cycle_range.start, startup_end))
    if cycle_range.end > startup_end:
        phases.append(PhaseSpan(CyclePhase.STABLE, startup_end, cycle_range.end))
    afterrun_end = _afterrun_end(cycle_range.end, modes, config)
    if afterrun_end is not None and afterrun_end > cycle_range.end:
        phases.append(PhaseSpan(CyclePhase.AFTERRUN, cycle_range.end, afterrun_end))
    return tuple(phases)


@dataclass(frozen=True, slots=True)
class _NumericStats:
    mean: float | None
    minimum: float | None
    maximum: float | None


def _numeric_stats(timeline: SignalTimeline | None, rng: TimeRange) -> _NumericStats:
    weighted: list[float] = []
    known_ms = 0
    values: list[float] = []
    for piece in _pieces(timeline, rng):
        number = None if piece.value is None else _as_float(piece.value)
        if number is None:
            continue
        duration = piece.end - piece.start
        weighted.append(number * duration)
        known_ms += duration
        values.append(number)
    if not values:
        return _NumericStats(None, None, None)
    return _NumericStats(math.fsum(weighted) / known_ms, min(values), max(values))


def _known_mask(timeline: SignalTimeline | None, rng: TimeRange) -> list[tuple[int, int]]:
    """Known (numeric) sub-ranges of ``rng`` as ``(start, end)`` pairs in time order."""
    return [
        (p.start, p.end)
        for p in _pieces(timeline, rng)
        if p.value is not None and _as_float(p.value) is not None
    ]


def _intersect_masks(a: list[tuple[int, int]], b: list[tuple[int, int]]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    i = j = 0
    while i < len(a) and j < len(b):
        start, end = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if start < end:
            result.append((start, end))
        if a[i][1] <= b[j][1]:
            i += 1
        else:
            j += 1
    return result


def cycle_aggregates(
    cycle_range: TimeRange,
    timelines: Sequence[SignalTimeline],
    config: PipelineConfig,
) -> CycleAggregates:
    """Per-cycle aggregates over the burning part using only known time. Time-weighted means
    are summed in time order with ``math.fsum`` (determinism).

    * ``flow_setpoint_c``: time-weighted mean flow setpoint while burning.
    * ``heat_demand_during``: ``True`` if demand was known-present at some point while
      burning, ``False`` if it was only ever known-absent, ``None`` if never known.
    * ``heat_demand_after_stop`` is left ``None`` here: it needs an observed stop and is set
      by :func:`detect_cycles`.
    * ``signal_coverage``: fraction of the burning part where flow, return and modulation
      were all known (``0.0`` if any is not mapped).
    """
    del config  # thresholds are not needed for the aggregates themselves
    flow = _find(timelines, FLOW)
    ret = _find(timelines, RETURN)
    modulation = _find(timelines, MODULATION)
    setpoint = _find(timelines, FLOW_SETPOINT)
    demand = _find(timelines, HEAT_DEMAND)

    flow_stats = _numeric_stats(flow, cycle_range)
    mod_stats = _numeric_stats(modulation, cycle_range)

    demand_states = {_as_bool(p.value) for p in _pieces(demand, cycle_range) if p.value is not None}
    demand_during: bool | None
    if True in demand_states:
        demand_during = True
    elif False in demand_states:
        demand_during = False
    else:
        demand_during = None

    mask = _intersect_masks(
        _intersect_masks(_known_mask(flow, cycle_range), _known_mask(ret, cycle_range)),
        _known_mask(modulation, cycle_range),
    )
    covered = sum(end - start for start, end in mask)

    return CycleAggregates(
        flow_setpoint_c=_numeric_stats(setpoint, cycle_range).mean,
        flow_max_c=flow_stats.maximum,
        flow_mean_c=flow_stats.mean,
        return_mean_c=_numeric_stats(ret, cycle_range).mean,
        modulation_mean_pct=mod_stats.mean,
        modulation_min_pct=mod_stats.minimum,
        heat_demand_during=demand_during,
        heat_demand_after_stop=None,
        signal_coverage=min(1.0, covered / cycle_range.duration_ms),
    )
