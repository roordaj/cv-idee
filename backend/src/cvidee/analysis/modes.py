"""Stage 3 — operating modes (ADR-002 §3.3, FR-09). Pure: no I/O, no wall clock.

Decision per instant ``t`` (the result does not depend on input order):

1. **Device-reported.** The operating-mode/status signal is known at ``t`` and its code is in
   ``config.mode_mapping`` → that mode with certainty ``DIRECT`` and source
   ``operating_mode@boiler``. This is the only way to get ``FAULT_BLOCKING``: faults and
   blockings are shown as device messages with their source (requirements §8), never inferred.
2. **Inferred** (no mode signal, signal unknown, or an unmapped code) with certainty
   ``INFERRED`` ("beperkte zekerheid"). Heat demand comes from the heat-demand signal, or,
   when that is not known, from the flow setpoint (``>= config.demand_flow_setpoint_min_c``).

   ======== ======== =====================================================================
   flame    demand   mode
   ======== ======== =====================================================================
   on       yes      ``CH``
   on       no       ``CH`` within ``afterrun_max_ms`` after demand was last seen during
                     this burn (the burner winds down after the thermostat stopped), else
                     ``DHW``: a combi boiler burning without heat demand is heating tap
                     water, so it never pollutes CH statistics (scenario 4)
   off      yes      ``CH`` (burner pause during demand)
   off      no       ``AFTERRUN`` while the pump runs within ``afterrun_max_ms`` after a
                     known flame-off (ended by the first known pump-off); ``STANDBY``
                     otherwise or when no pump signal is mapped
   ======== ======== =====================================================================

3. **Unknown.** Whenever a signal needed for the decision above is unknown (flame unknown;
   demand unknown; pump mapped but unknown inside the afterrun window) → ``UNKNOWN`` with
   certainty ``NONE``. Unknown time is never standby (ADR-002 §8).

Every look-back (afterrun window, demand grace) is bounded by ``config.afterrun_max_ms``,
which ``PipelineConfig`` guarantees to fit in the lookback, so chunked == whole holds
(ADR-002 §5, §6).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import pairwise

from cvidee.analysis.types import (
    AnalysisWindow,
    DurationMs,
    Mode,
    ModeCertainty,
    ModeSegment,
    ObservedValue,
    PipelineConfig,
    Role,
    SignalRef,
    SignalTimeline,
    TimestampMs,
    floor_to_grid,
)

OPERATING_MODE = SignalRef(Role.OPERATING_MODE)
FLAME = SignalRef(Role.FLAME)
HEAT_DEMAND = SignalRef(Role.HEAT_DEMAND)
FLOW_SETPOINT = SignalRef(Role.FLOW_SETPOINT)
PUMP = SignalRef(Role.PUMP_STATE)

_INPUTS = (OPERATING_MODE, FLAME, HEAT_DEMAND, FLOW_SETPOINT, PUMP)
_TRUE_STRINGS = frozenset({"on", "true", "1"})
_FALSE_STRINGS = frozenset({"off", "false", "0"})


# --------------------------------------------------------------------------------------
# Value helpers
# --------------------------------------------------------------------------------------


def _as_bool(value: ObservedValue | None) -> bool | None:
    if value is None:
        return None
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


def _as_float(value: ObservedValue | None) -> float | None:
    if value is None or isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return None if math.isnan(number) else number


def mode_code(value: ObservedValue) -> str | None:
    """Normalise a status-signal value to a mapping code: stripped strings as-is, integral
    numbers without decimals (``1.0`` → ``"1"``); booleans, NaN and fractional numbers are
    not codes (``None``)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        if math.isnan(value) or math.isinf(value) or value != int(value):
            return None
        return str(int(value))
    code = value.strip()
    return code or None


def map_mode_code(code: str, mapping: Sequence[tuple[str, Mode]]) -> Mode | None:
    """Map a status/mode code to a mode; ``None`` for unmapped codes.

    Codes are compared after stripping whitespace; the first matching entry wins. An
    unmapped code is not evidence of any mode: :func:`classify_modes` then falls back to
    inference (``INFERRED``, or ``UNKNOWN`` if the inference signals are unknown).
    """
    wanted = code.strip()
    for candidate, mode in mapping:
        if candidate.strip() == wanted:
            return mode
    return None


# --------------------------------------------------------------------------------------
# Segments: merging and the canonical grid
# --------------------------------------------------------------------------------------


def _same_content(a: ModeSegment, b: ModeSegment) -> bool:
    return a.mode is b.mode and a.certainty is b.certainty and a.sources == b.sources


def merge_segments(segments: Iterable[ModeSegment]) -> tuple[ModeSegment, ...]:
    """Merge adjacent segments with equal mode, certainty and sources (the reader side of
    ADR-002 §4.5). A merged segment is ``final`` only if all its parts are."""
    merged: list[ModeSegment] = []
    for segment in sorted(segments, key=lambda s: (s.start, s.end)):
        if merged and merged[-1].end == segment.start and _same_content(merged[-1], segment):
            last = merged[-1]
            merged[-1] = ModeSegment(
                last.start,
                segment.end,
                last.mode,
                last.certainty,
                last.sources,
                last.final and segment.final,
            )
        else:
            merged.append(segment)
    return tuple(merged)


def split_on_grid(segments: Sequence[ModeSegment], grid_ms: DurationMs) -> tuple[ModeSegment, ...]:
    """Split segments at canonical UTC grid boundaries (ADR-002 §4.5) so that keys
    (``start``) do not depend on where a run's window started."""
    result: list[ModeSegment] = []
    for segment in sorted(segments, key=lambda s: (s.start, s.end)):
        cursor = segment.start
        while cursor < segment.end:
            stop = min(segment.end, floor_to_grid(cursor, grid_ms) + grid_ms)
            result.append(
                ModeSegment(
                    cursor, stop, segment.mode, segment.certainty, segment.sources, segment.final
                )
            )
            cursor = stop
    return tuple(result)


# --------------------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Inputs:
    """Signal values on one elementary piece (``None`` = unknown or not mapped)."""

    code_mode: Mode | None
    flame: bool | None
    demand: bool | None
    demand_source: SignalRef | None
    pump: bool | None


@dataclass(slots=True)
class _State:
    """Bounded history needed for afterrun and the demand grace while burning."""

    prev_flame: bool | None = None
    flame_off_since: TimestampMs | None = None
    """Start of the current known flame-off stretch, if it began with a known flame-on."""
    pump_seen_off: bool = False
    """The pump was known off since ``flame_off_since`` (ends the afterrun)."""
    demand_on_until: TimestampMs | None = None
    """End of the last known heat demand during the current known flame-on stretch."""


def _decision(
    inputs: _Inputs,
    state: _State,
    t: TimestampMs,
    pump_mapped: bool,
    config: PipelineConfig,
) -> tuple[Mode, ModeCertainty, tuple[SignalRef, ...]]:
    if inputs.code_mode is not None:
        return inputs.code_mode, ModeCertainty.DIRECT, (OPERATING_MODE,)

    unknown = (Mode.UNKNOWN, ModeCertainty.NONE, ())
    if inputs.flame is None or inputs.demand is None or inputs.demand_source is None:
        return unknown
    used: tuple[SignalRef, ...] = (FLAME, inputs.demand_source)

    mode: Mode
    if inputs.demand:
        mode = Mode.CH
    elif inputs.flame:
        grace = state.demand_on_until is not None and t < state.demand_on_until + (
            config.afterrun_max_ms
        )
        mode = Mode.CH if grace else Mode.DHW
    else:
        in_window = (
            state.flame_off_since is not None
            and t < state.flame_off_since + config.afterrun_max_ms
            and not state.pump_seen_off
        )
        if in_window and pump_mapped and inputs.pump is None:
            return unknown
        if inputs.pump is not None:
            used = (*used, PUMP)
        mode = Mode.AFTERRUN if in_window and inputs.pump else Mode.STANDBY
    return mode, ModeCertainty.INFERRED, tuple(sorted(used))


def _read(
    timelines: dict[SignalRef, SignalTimeline], ts: TimestampMs, config: PipelineConfig
) -> _Inputs:
    def value(signal: SignalRef) -> ObservedValue | None:
        timeline = timelines.get(signal)
        return None if timeline is None else timeline.value_at(ts)

    raw_code = value(OPERATING_MODE)
    code = None if raw_code is None else mode_code(raw_code)
    code_mode = None if code is None else map_mode_code(code, config.mode_mapping)

    demand = _as_bool(value(HEAT_DEMAND))
    demand_source: SignalRef | None = HEAT_DEMAND
    if demand is None:
        setpoint = _as_float(value(FLOW_SETPOINT))
        demand = None if setpoint is None else setpoint >= config.demand_flow_setpoint_min_c
        demand_source = None if setpoint is None else FLOW_SETPOINT
    return _Inputs(code_mode, _as_bool(value(FLAME)), demand, demand_source, _as_bool(value(PUMP)))


def classify_modes(
    timelines: Sequence[SignalTimeline],
    config: PipelineConfig,
    window: AnalysisWindow,
) -> tuple[ModeSegment, ...]:
    """Partition ``window.context`` into mode segments.

    * With an operating-mode signal: mode from :func:`map_mode_code`, certainty ``DIRECT``.
    * Without it: inferred from flame, heat demand, flow setpoint and pump state
      (certainty ``INFERRED``, "beperkte zekerheid"); see the module docstring.
    * ``AFTERRUN``: pump running / afterrun status after flame-off without demand, at most
      ``config.afterrun_max_ms``.
    * Any instant where the signals needed for a decision are unknown → ``UNKNOWN`` with
      certainty ``NONE``; unknown is never classified as standby.
    * Adjacent equal segments are merged, then split on the canonical grid
      (:func:`split_on_grid`).

    Time outside a timeline's span counts as unknown. ``final`` flags are set by the
    pipeline.

    Returns:
        Contiguous segments covering ``window.context``, sorted by ``start``.
    """
    rng = window.context
    if rng is None:
        return ()
    by_signal = {t.signal: t for t in timelines if t.signal in _INPUTS}
    starts: set[TimestampMs] = {rng.start}
    for timeline in by_signal.values():
        starts.update(i.start for i in timeline.overlapping(rng) if rng.contains(i.start))
        if rng.contains(timeline.span.end):
            starts.add(timeline.span.end)
    boundaries = [*sorted(starts), rng.end]
    pump_mapped = PUMP in by_signal
    afterrun = config.afterrun_max_ms

    state = _State()
    raw: list[ModeSegment] = []
    for piece_start, piece_end in pairwise(boundaries):
        inputs = _read(by_signal, piece_start, config)

        # Update the bounded history with this piece's flame state.
        if inputs.flame is True:
            if state.prev_flame is not True:
                state.demand_on_until = None
            state.flame_off_since = None
        elif inputs.flame is False:
            if state.prev_flame is True:
                state.flame_off_since = piece_start
                state.pump_seen_off = False
            state.demand_on_until = None
        else:
            state.flame_off_since = None
            state.demand_on_until = None
        state.prev_flame = inputs.flame

        # Timers expiring inside this piece split it.
        cuts = {piece_start, piece_end}
        for since in (state.flame_off_since, state.demand_on_until):
            if since is not None and piece_start < since + afterrun < piece_end:
                cuts.add(since + afterrun)
        points = sorted(cuts)
        for start, end in pairwise(points):
            mode, certainty, sources = _decision(inputs, state, start, pump_mapped, config)
            raw.append(ModeSegment(start, end, mode, certainty, sources))

        if inputs.flame is True and inputs.demand is True:
            state.demand_on_until = piece_end
        if inputs.flame is False and inputs.pump is False:
            state.pump_seen_off = True

    return split_on_grid(merge_segments(raw), config.grid_ms)
