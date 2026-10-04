"""Stage 4 — burner cycles (FR-12, FR-15, FR-16; ADR-002 §3.4, §4.4, §6).

Timelines and mode segments are built by hand: stages 1-3 are not under test here.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from cvidee.analysis.cycles import (
    classify_end_reason,
    cycle_aggregates,
    cycle_phases,
    cycle_settles_at,
    detect_cycles,
)
from cvidee.analysis.types import (
    HOUR_MS,
    MINUTE_MS,
    AnalysisWindow,
    BurnerCycle,
    CyclePhase,
    EndReason,
    Mode,
    ModeCertainty,
    ModeSegment,
    ObservationKind,
    ObservedValue,
    PhaseSpan,
    PipelineConfig,
    Provenance,
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

T0: TimestampMs = 1_790_000_000_000 - (1_790_000_000_000 % HOUR_MS)
"""A whole UTC hour in late Sept 2026."""
M = MINUTE_MS
S = 1_000

FLAME = SignalRef(Role.FLAME)
DEMAND = SignalRef(Role.HEAT_DEMAND)
FLOW = SignalRef(Role.FLOW_TEMPERATURE)
RETURN = SignalRef(Role.RETURN_TEMPERATURE)
SETPOINT = SignalRef(Role.FLOW_SETPOINT)
MODULATION = SignalRef(Role.MODULATION)

CONFIG = PipelineConfig(
    signals=tuple(
        SignalConfig(s, Provenance(ValueKind.REPORTED, f"sensor.{s.role}"))
        for s in (FLAME, DEMAND, FLOW, RETURN, SETPOINT, MODULATION)
    ),
    config_hash="test",
)

CHANGE, POLL, CONFIRM = ObservationKind.CHANGE, ObservationKind.POLL, ObservationKind.CONFIRM

type Step = tuple[TimestampMs, ObservedValue | None, ObservationKind]
"""``(ts, value, kind)``; ``value is None`` = unknown (data gap) from ``ts``."""


# --------------------------------------------------------------------------------------
# Hand-built inputs
# --------------------------------------------------------------------------------------


def timeline(signal: SignalRef, span: TimeRange, steps: Sequence[Step]) -> SignalTimeline:
    """Timeline of ``steps`` over ``span``, as stage 1 would build it.

    Each step holds until the next one; the last step before ``span.start`` is the carry-in
    (clipped to ``span.start``, keeping ``observed_at`` and ``origin``); before the first step
    the value is unknown (``NO_DATA``); ``None`` values are ``DISCONNECTED``.
    """
    ordered = sorted(steps, key=lambda s: s[0])
    carry = [s for s in ordered if s[0] < span.start][-1:]
    inside = [s for s in ordered if span.start <= s[0] < span.end]
    prov = Provenance(ValueKind.REPORTED, f"sensor.{signal.role}")
    intervals: list[TimelineInterval] = []
    first = inside[0][0] if inside else span.end
    if not carry and first > span.start:
        intervals.append(UnknownInterval(span.start, first, UnknownReason.NO_DATA))
    chosen = carry + inside
    for k, (ts, value, kind) in enumerate(chosen):
        start = max(ts, span.start)
        end = chosen[k + 1][0] if k + 1 < len(chosen) else span.end
        if end <= start:
            continue
        if value is None:
            intervals.append(UnknownInterval(start, end, UnknownReason.DISCONNECTED))
        else:
            intervals.append(ValueInterval(start, end, value, prov, ts, kind))
    return SignalTimeline(signal, span, tuple(intervals))


def segments(
    parts: Sequence[tuple[TimestampMs, Mode]], span: TimeRange, grid: int = HOUR_MS
) -> list[ModeSegment]:
    """Mode segments from ``(start, mode)`` change points, clipped to ``span`` and split on
    the canonical grid like stage 3 does."""
    ordered = sorted(parts)
    result: list[ModeSegment] = []
    for k, (start, mode) in enumerate(ordered):
        end = ordered[k + 1][0] if k + 1 < len(ordered) else span.end
        start, end = max(start, span.start), min(end, span.end)
        cursor = start
        while cursor < end:
            stop = min(end, floor_to_grid(cursor, grid) + grid)
            certainty = ModeCertainty.NONE if mode is Mode.UNKNOWN else ModeCertainty.DIRECT
            result.append(ModeSegment(cursor, stop, mode, certainty))
            cursor = stop
    return result


def window(end: TimestampMs, start: TimestampMs = T0) -> AnalysisWindow:
    return AnalysisWindow(context_start=start, emit_from=start, end=end)


def run(
    flame: Sequence[Step],
    end: TimestampMs,
    *,
    demand: Sequence[Step] | None = None,
    modes: Sequence[tuple[TimestampMs, Mode]] = (),
    extra: Sequence[tuple[SignalRef, Sequence[Step]]] = (),
    config: PipelineConfig = CONFIG,
    start: TimestampMs = T0,
) -> tuple[BurnerCycle, ...]:
    w = window(end, start)
    span = TimeRange(w.context_start, w.end)
    timelines = [timeline(FLAME, span, flame)]
    if demand is not None:
        timelines.append(timeline(DEMAND, span, demand))
    timelines += [timeline(signal, span, steps) for signal, steps in extra]
    return detect_cycles(timelines, segments(modes, span), config, w)


def on_off(*pairs: tuple[int, int]) -> list[Step]:
    """Flame steps: off (poll) at T0, then on/off changes at the given minute offsets."""
    steps: list[Step] = [(T0, False, POLL)]
    for on, off in pairs:
        steps += [(T0 + on * M, True, CHANGE), (T0 + off * M, False, CHANGE)]
    return steps


ALWAYS_DEMAND: list[Step] = [(T0, True, POLL)]


# --------------------------------------------------------------------------------------
# Periods (FR-12)
# --------------------------------------------------------------------------------------


class TestPeriods:
    def test_known_sequence_gives_exact_periods(self) -> None:
        cycles = run(
            on_off((10, 13), (20, 30), (95, 102)),
            T0 + 3 * HOUR_MS,
            demand=ALWAYS_DEMAND,
            modes=[(T0, Mode.CH)],
        )
        assert [(c.start, c.end, c.duration_ms) for c in cycles] == [
            (T0 + 10 * M, T0 + 13 * M, 3 * M),
            (T0 + 20 * M, T0 + 30 * M, 10 * M),
            (T0 + 95 * M, T0 + 102 * M, 7 * M),
        ]
        assert all(c.complete and c.start_observed and c.counts_as_start for c in cycles)
        assert all(c.mode is Mode.CH for c in cycles)
        assert [c.end_reason for c in cycles] == [EndReason.STOP_DURING_DEMAND] * 3
        # 7 min pause; 65 min exceeds max_pause_ms (60 min): standby is never a pause.
        assert [c.pause_before_ms for c in cycles] == [None, 7 * M, None]
        assert not any(c.final for c in cycles)

    def test_no_flame_timeline_gives_no_cycles(self) -> None:
        w = window(T0 + HOUR_MS)
        demand = timeline(DEMAND, TimeRange(T0, T0 + HOUR_MS), ALWAYS_DEMAND)
        assert detect_cycles([demand], [], CONFIG, w) == ()

    def test_empty_window_gives_no_cycles(self) -> None:
        w = AnalysisWindow(T0, T0, T0)
        assert detect_cycles([], [], CONFIG, w) == ()

    def test_confirm_and_repeated_on_do_not_split_a_cycle(self) -> None:
        flame: list[Step] = [
            (T0, False, POLL),
            (T0 + 10 * M, True, CHANGE),
            (T0 + 12 * M, True, CONFIRM),
            (T0 + 14 * M, True, CHANGE),
            (T0 + 16 * M, False, CHANGE),
        ]
        (cycle,) = run(flame, T0 + HOUR_MS, demand=ALWAYS_DEMAND)
        assert (cycle.start, cycle.end, cycle.complete) == (T0 + 10 * M, T0 + 16 * M, True)

    def test_numeric_and_string_flame_values(self) -> None:
        flame: list[Step] = [
            (T0, "off", POLL),
            (T0 + 5 * M, "on", CHANGE),
            (T0 + 8 * M, 0.0, CHANGE),
            (T0 + 9 * M, 1.0, CHANGE),
            (T0 + 11 * M, "off", CHANGE),
        ]
        cycles = run(flame, T0 + HOUR_MS, demand=ALWAYS_DEMAND)
        assert [(c.start, c.end) for c in cycles] == [
            (T0 + 5 * M, T0 + 8 * M),
            (T0 + 9 * M, T0 + 11 * M),
        ]

    def test_unparseable_flame_value_is_unknown(self) -> None:
        flame: list[Step] = [
            (T0, False, POLL),
            (T0 + 5 * M, True, CHANGE),
            (T0 + 8 * M, "garbage", CHANGE),
        ]
        (cycle,) = run(flame, T0 + HOUR_MS, demand=ALWAYS_DEMAND)
        assert cycle.end_reason is EndReason.DATA_GAP
        assert cycle.end == T0 + 8 * M

    def test_open_cycle_at_horizon(self) -> None:
        flame: list[Step] = [(T0, False, POLL), (T0 + 50 * M, True, CHANGE)]
        (cycle,) = run(flame, T0 + HOUR_MS, demand=ALWAYS_DEMAND)
        assert cycle.end is None
        assert cycle.end_reason is None
        assert cycle.duration_ms == 10 * M  # lower bound: window.end - start
        assert cycle.start_observed
        assert not cycle.complete
        assert cycle_settles_at(cycle, CONFIG) is None

    def test_input_order_is_irrelevant(self) -> None:
        span = TimeRange(T0, T0 + 2 * HOUR_MS)
        timelines = [
            timeline(FLAME, span, on_off((10, 13), (20, 30))),
            timeline(DEMAND, span, ALWAYS_DEMAND),
            timeline(FLOW, span, [(T0, 40.0, POLL), (T0 + 25 * M, 60.0, CHANGE)]),
        ]
        modes = segments([(T0, Mode.CH), (T0 + 30 * M, Mode.AFTERRUN)], span)
        w = window(span.end)
        expected = detect_cycles(timelines, modes, CONFIG, w)
        rng = random.Random(4)
        for _ in range(5):
            rng.shuffle(timelines)
            rng.shuffle(modes)
            assert detect_cycles(timelines, modes, CONFIG, w) == expected


# --------------------------------------------------------------------------------------
# End reasons (scenario 3, FR-16) and DHW (scenario 4)
# --------------------------------------------------------------------------------------


class TestEndReason:
    STOP = T0 + 20 * M

    def _reason(
        self, demand: Sequence[Step] | None, *, end: TimestampMs = T0 + HOUR_MS
    ) -> EndReason | None:
        (cycle,) = run(on_off((10, 20)), end, demand=demand, modes=[(T0, Mode.CH)])
        return cycle.end_reason

    def test_stop_during_demand(self) -> None:
        assert self._reason(ALWAYS_DEMAND) is EndReason.STOP_DURING_DEMAND

    def test_demand_ended_at_stop_is_not_stop_during_demand(self) -> None:
        demand: list[Step] = [(T0, True, POLL), (self.STOP, False, CHANGE)]
        assert self._reason(demand) is EndReason.DEMAND_ENDED

    def test_demand_ended_before_stop(self) -> None:
        demand: list[Step] = [(T0, True, POLL), (self.STOP - 30 * S, False, CHANGE)]
        assert self._reason(demand) is EndReason.DEMAND_ENDED

    def test_demand_ending_within_lookahead_after_stop(self) -> None:
        demand: list[Step] = [(T0, True, POLL), (self.STOP + 30 * S, False, CHANGE)]
        assert self._reason(demand) is EndReason.DEMAND_ENDED

    def test_demand_ending_after_lookahead_is_stop_during_demand(self) -> None:
        demand: list[Step] = [(T0, True, POLL), (self.STOP + 2 * M, False, CHANGE)]
        assert self._reason(demand) is EndReason.STOP_DURING_DEMAND

    def test_demand_unknown_around_stop_is_undetermined(self) -> None:
        demand: list[Step] = [(T0, True, POLL), (self.STOP + 10 * S, None, CHANGE)]
        assert self._reason(demand) is EndReason.UNDETERMINED

    def test_demand_not_mapped_is_undetermined(self) -> None:
        assert self._reason(None) is EndReason.UNDETERMINED

    def test_lookahead_beyond_horizon_is_undetermined(self) -> None:
        # Stop 30 s before the horizon: the lookahead is not complete yet.
        assert self._reason(ALWAYS_DEMAND, end=self.STOP + 30 * S) is EndReason.UNDETERMINED

    def test_partially_unknown_but_known_absent_is_demand_ended(self) -> None:
        demand: list[Step] = [
            (T0, True, POLL),
            (self.STOP, None, CHANGE),
            (self.STOP + 20 * S, False, POLL),
        ]
        assert self._reason(demand) is EndReason.DEMAND_ENDED

    def test_classify_end_reason_direct(self) -> None:
        span = TimeRange(T0, T0 + HOUR_MS)
        demand = timeline(DEMAND, span, ALWAYS_DEMAND)
        assert classify_end_reason(self.STOP, Mode.DHW, demand, CONFIG) is EndReason.DHW_ENDED
        assert (
            classify_end_reason(self.STOP, Mode.UNKNOWN, demand, CONFIG)
            is EndReason.STOP_DURING_DEMAND
        )
        assert classify_end_reason(self.STOP, Mode.CH, None, CONFIG) is EndReason.UNDETERMINED

    def test_lookahead_is_configurable(self) -> None:
        config = PipelineConfig(signals=CONFIG.signals, end_reason_lookahead_ms=10 * S)
        demand: list[Step] = [(T0, True, POLL), (self.STOP + 30 * S, False, CHANGE)]
        (cycle,) = run(on_off((10, 20)), T0 + HOUR_MS, demand=demand, config=config)
        assert cycle.end_reason is EndReason.STOP_DURING_DEMAND

    def test_dhw_cycle(self) -> None:
        """Scenario 4: tapwater cycle with afterrun (design: 07:12-07:22 + 4 min naloop)."""
        cycles = run(
            on_off((12, 22)),
            T0 + HOUR_MS,
            demand=ALWAYS_DEMAND,  # CH demand during DHW is irrelevant for the end reason
            modes=[
                (T0, Mode.STANDBY),
                (T0 + 12 * M, Mode.DHW),
                (T0 + 22 * M, Mode.AFTERRUN),
                (T0 + 26 * M, Mode.STANDBY),
            ],
        )
        (cycle,) = cycles
        assert cycle.mode is Mode.DHW
        assert cycle.end_reason is EndReason.DHW_ENDED
        assert cycle.complete
        assert cycle.duration_ms == 10 * M
        assert cycle.phases[-1] == PhaseSpan(CyclePhase.AFTERRUN, T0 + 22 * M, T0 + 26 * M)

    def test_dhw_wins_over_ch(self) -> None:
        (cycle,) = run(
            on_off((10, 20)), T0 + HOUR_MS, modes=[(T0, Mode.CH), (T0 + 15 * M, Mode.DHW)]
        )
        assert cycle.mode is Mode.DHW

    def test_mode_unknown_without_ch_or_dhw(self) -> None:
        (cycle,) = run(on_off((10, 20)), T0 + HOUR_MS, modes=[(T0, Mode.UNKNOWN)])
        assert cycle.mode is Mode.UNKNOWN


# --------------------------------------------------------------------------------------
# Data gaps and reconnects (scenario 5, FR-08, FR-11)
# --------------------------------------------------------------------------------------


class TestDataGaps:
    def test_gap_mid_cycle_gives_incomplete_cycle_and_no_start_after_reconnect(self) -> None:
        """Design B-015: cycle from 10:05, CAN data lost 10:10-10:40, reconnect while on."""
        flame: list[Step] = [
            (T0, False, POLL),
            (T0 + 5 * M, True, CHANGE),
            (T0 + 10 * M, None, CHANGE),
            (T0 + 40 * M, True, POLL),
            (T0 + 45 * M, False, CHANGE),
        ]
        first, second = run(flame, T0 + HOUR_MS, demand=ALWAYS_DEMAND, modes=[(T0, Mode.CH)])
        assert (first.start, first.end) == (T0 + 5 * M, T0 + 10 * M)
        assert first.end_reason is EndReason.DATA_GAP
        assert not first.complete
        assert first.start_observed
        assert first.duration_ms == 5 * M  # lower bound ("≥ 5:00")
        assert (second.start, second.end) == (T0 + 40 * M, T0 + 45 * M)
        assert not second.counts_as_start
        assert not second.complete
        assert second.end_reason is EndReason.STOP_DURING_DEMAND
        assert second.pause_before_ms is None  # unknown time is never a pause
        assert sum(c.counts_as_start for c in (first, second)) == 1

    def test_poll_after_gap_is_not_a_start(self) -> None:
        flame: list[Step] = [
            (T0, False, POLL),
            (T0 + 10 * M, None, CHANGE),
            (T0 + 30 * M, True, POLL),
            (T0 + 35 * M, False, CHANGE),
        ]
        (cycle,) = run(flame, T0 + HOUR_MS, demand=ALWAYS_DEMAND)
        assert cycle.start == T0 + 30 * M
        assert not cycle.start_observed

    def test_change_on_directly_after_gap_is_not_a_start(self) -> None:
        flame: list[Step] = [
            (T0, False, POLL),
            (T0 + 10 * M, None, CHANGE),
            (T0 + 30 * M, True, CHANGE),
            (T0 + 35 * M, False, CHANGE),
        ]
        (cycle,) = run(flame, T0 + HOUR_MS, demand=ALWAYS_DEMAND)
        assert not cycle.start_observed

    def test_poll_on_without_gap_is_not_a_start(self) -> None:
        flame: list[Step] = [
            (T0, False, POLL),
            (T0 + 10 * M, True, POLL),
            (T0 + 15 * M, False, CHANGE),
        ]
        (cycle,) = run(flame, T0 + HOUR_MS, demand=ALWAYS_DEMAND)
        assert not cycle.start_observed
        assert not cycle.complete

    def test_confirm_on_after_off_is_not_a_start(self) -> None:
        flame: list[Step] = [
            (T0, False, POLL),
            (T0 + 10 * M, True, CONFIRM),
            (T0 + 15 * M, False, CHANGE),
        ]
        (cycle,) = run(flame, T0 + HOUR_MS, demand=ALWAYS_DEMAND)
        assert not cycle.start_observed

    def test_off_after_gap_then_change_on_is_a_start_without_pause(self) -> None:
        flame: list[Step] = [
            (T0, False, POLL),
            (T0 + 5 * M, True, CHANGE),
            (T0 + 8 * M, False, CHANGE),
            (T0 + 10 * M, None, CHANGE),
            (T0 + 20 * M, False, POLL),
            (T0 + 25 * M, True, CHANGE),
            (T0 + 30 * M, False, CHANGE),
        ]
        first, second = run(flame, T0 + HOUR_MS, demand=ALWAYS_DEMAND)
        assert first.complete
        assert second.complete
        assert second.pause_before_ms is None

    def test_off_seen_only_by_poll_is_not_an_observed_stop(self) -> None:
        flame: list[Step] = [
            (T0, False, POLL),
            (T0 + 5 * M, True, CHANGE),
            (T0 + 9 * M, False, POLL),
            (T0 + 20 * M, True, CHANGE),
            (T0 + 25 * M, False, CHANGE),
        ]
        first, second = run(flame, T0 + HOUR_MS, demand=ALWAYS_DEMAND)
        assert first.end_reason is EndReason.DATA_GAP
        assert not first.complete
        assert first.aggregates.heat_demand_after_stop is None
        assert second.start_observed
        assert second.pause_before_ms is None

    def test_flame_unknown_until_horizon(self) -> None:
        flame: list[Step] = [
            (T0, False, POLL),
            (T0 + 5 * M, True, CHANGE),
            (T0 + 7 * M, None, POLL),
        ]
        (cycle,) = run(flame, T0 + HOUR_MS, demand=ALWAYS_DEMAND, modes=[(T0, Mode.AFTERRUN)])
        assert cycle.end == T0 + 7 * M
        assert cycle.end_reason is EndReason.DATA_GAP
        assert all(p.phase is not CyclePhase.AFTERRUN for p in cycle.phases)


# --------------------------------------------------------------------------------------
# Window boundaries (ADR-002 §4.4)
# --------------------------------------------------------------------------------------


class TestWindowBoundaries:
    def test_cycle_burning_at_context_start_is_clipped_and_not_a_start(self) -> None:
        flame: list[Step] = [(T0 - 10 * M, True, CHANGE), (T0 + 5 * M, False, CHANGE)]
        (cycle,) = run(flame, T0 + HOUR_MS, demand=ALWAYS_DEMAND)
        assert cycle.start == T0
        assert not cycle.start_observed
        assert cycle.duration_ms == 5 * M
        assert not cycle.complete
        assert cycle.end_reason is EndReason.STOP_DURING_DEMAND

    def test_carry_in_off_allows_an_observed_start_right_after_context_start(self) -> None:
        flame: list[Step] = [(T0 - 3 * HOUR_MS, False, CHANGE), (T0 + 1 * M, True, CHANGE)]
        (cycle,) = run(flame, T0 + HOUR_MS)
        assert cycle.start_observed

    def test_observations_at_or_after_horizon_are_ignored(self) -> None:
        end = T0 + 30 * M
        flame: list[Step] = [(T0, False, POLL), (T0 + 20 * M, True, CHANGE), (end, False, CHANGE)]
        (cycle,) = run(flame, end, demand=ALWAYS_DEMAND)
        assert cycle.end is None
        assert cycle.duration_ms == 10 * M

    def test_open_cycle_is_recomputed_identically_from_its_start(self) -> None:
        """A run that starts at the held watermark (the cycle start) sees the same cycle."""
        flame = on_off((7 * 60 + 10, 7 * 60 + 200))
        start = floor_to_grid(T0 + (7 * 60 + 10) * M, HOUR_MS) - CONFIG.lookback_ms
        assert start > T0
        late = run(flame, T0 + 12 * HOUR_MS, demand=ALWAYS_DEMAND, start=start)
        early = run(flame, T0 + 12 * HOUR_MS, demand=ALWAYS_DEMAND)
        assert late == early
        assert late[0].complete

    def test_settles_at_covers_lookahead_and_afterrun(self) -> None:
        (cycle,) = run(on_off((10, 20)), T0 + HOUR_MS, demand=ALWAYS_DEMAND)
        assert cycle.end is not None
        assert cycle_settles_at(cycle, CONFIG) == cycle.end + CONFIG.afterrun_max_ms


# --------------------------------------------------------------------------------------
# Phases (FR-15)
# --------------------------------------------------------------------------------------


class TestPhases:
    SPAN = TimeRange(T0, T0 + HOUR_MS)
    CYCLE = TimeRange(T0 + 10 * M, T0 + 30 * M)

    def _flow(self, steps: Sequence[Step]) -> SignalTimeline:
        return timeline(FLOW, self.SPAN, steps)

    def _setpoint(self, value: float = 55.0) -> SignalTimeline:
        return timeline(SETPOINT, self.SPAN, [(T0, value, POLL)])

    def test_startup_until_flow_reaches_setpoint_minus_margin(self) -> None:
        flow = self._flow(
            [(T0, 35.0, POLL), (T0 + 11 * M, 50.0, CHANGE), (T0 + 12 * M, 53.0, CHANGE)]
        )
        phases = cycle_phases(self.CYCLE, flow, self._setpoint(), [], CONFIG)
        assert phases == (
            PhaseSpan(CyclePhase.STARTUP, T0 + 10 * M, T0 + 12 * M),
            PhaseSpan(CyclePhase.STABLE, T0 + 12 * M, T0 + 30 * M),
        )

    def test_startup_capped_at_startup_max(self) -> None:
        flow = self._flow([(T0, 35.0, POLL)])
        phases = cycle_phases(self.CYCLE, flow, self._setpoint(), [], CONFIG)
        assert phases[0] == PhaseSpan(CyclePhase.STARTUP, T0 + 10 * M, T0 + 13 * M)
        assert phases[1].phase is CyclePhase.STABLE

    def test_unknown_setpoint_keeps_startup_until_max(self) -> None:
        flow = self._flow([(T0, 60.0, POLL)])
        phases = cycle_phases(self.CYCLE, flow, None, [], CONFIG)
        assert phases[0] == PhaseSpan(CyclePhase.STARTUP, T0 + 10 * M, T0 + 13 * M)

    def test_already_hot_flow_has_no_startup(self) -> None:
        flow = self._flow([(T0, 54.0, POLL)])
        phases = cycle_phases(self.CYCLE, flow, self._setpoint(), [], CONFIG)
        assert phases == (PhaseSpan(CyclePhase.STABLE, T0 + 10 * M, T0 + 30 * M),)

    def test_short_cycle_is_only_startup(self) -> None:
        short = TimeRange(T0 + 10 * M, T0 + 12 * M)
        phases = cycle_phases(short, self._flow([(T0, 35.0, POLL)]), self._setpoint(), [], CONFIG)
        assert phases == (PhaseSpan(CyclePhase.STARTUP, short.start, short.end),)

    def test_thresholds_are_configurable(self) -> None:
        config = PipelineConfig(
            signals=CONFIG.signals, startup_max_ms=5 * M, startup_flow_margin_k=6.0
        )
        flow = self._flow([(T0, 35.0, POLL), (T0 + 12 * M, 50.0, CHANGE)])
        assert cycle_phases(self.CYCLE, flow, self._setpoint(), [], config)[0].end == T0 + 12 * M
        flow = self._flow([(T0, 35.0, POLL)])
        assert cycle_phases(self.CYCLE, flow, self._setpoint(), [], config)[0].end == T0 + 15 * M

    def test_afterrun_merges_grid_split_segments_and_is_capped(self) -> None:
        cycle = TimeRange(T0 + 40 * M, T0 + 55 * M)
        span = TimeRange(T0, T0 + 2 * HOUR_MS)
        modes = segments([(T0, Mode.CH), (T0 + 55 * M, Mode.AFTERRUN)], span)
        phases = cycle_phases(cycle, None, None, modes, CONFIG)
        assert phases[-1] == PhaseSpan(CyclePhase.AFTERRUN, T0 + 55 * M, T0 + 70 * M)

    def test_afterrun_may_start_shortly_after_flame_off(self) -> None:
        modes = segments(
            [(T0, Mode.CH), (T0 + 30 * M + 20 * S, Mode.AFTERRUN), (T0 + 33 * M, Mode.STANDBY)],
            self.SPAN,
        )
        phases = cycle_phases(self.CYCLE, None, None, modes, CONFIG)
        assert phases[-1] == PhaseSpan(CyclePhase.AFTERRUN, T0 + 30 * M, T0 + 33 * M)

    def test_no_afterrun_when_mode_switches_later(self) -> None:
        modes = segments(
            [(T0, Mode.CH), (T0 + 32 * M, Mode.AFTERRUN), (T0 + 33 * M, Mode.STANDBY)],
            self.SPAN,
        )
        phases = cycle_phases(self.CYCLE, None, None, modes, CONFIG)
        assert all(p.phase is not CyclePhase.AFTERRUN for p in phases)


# --------------------------------------------------------------------------------------
# Aggregates (FR-12)
# --------------------------------------------------------------------------------------


class TestAggregates:
    def test_cycle_aggregates(self) -> None:
        cycles = run(
            on_off((10, 20)),
            T0 + HOUR_MS,
            demand=[(T0, True, POLL), (T0 + 20 * M, False, CHANGE)],
            modes=[(T0, Mode.CH)],
            extra=[
                (FLOW, [(T0, 40.0, POLL), (T0 + 15 * M, 60.0, CHANGE)]),
                (
                    RETURN,
                    [(T0, 35.0, POLL), (T0 + 12 * M, None, CHANGE), (T0 + 14 * M, 45.0, POLL)],
                ),
                (SETPOINT, [(T0, 55.0, POLL)]),
                (
                    MODULATION,
                    [(T0, 0.0, POLL), (T0 + 10 * M, 45.0, CHANGE), (T0 + 11 * M, 19.0, CHANGE)],
                ),
            ],
        )
        (cycle,) = cycles
        agg = cycle.aggregates
        assert agg.flow_max_c == 60.0
        assert agg.flow_mean_c == pytest.approx(50.0)
        assert agg.return_mean_c == pytest.approx((2 * 35.0 + 6 * 45.0) / 8)
        assert agg.flow_setpoint_c == 55.0
        assert agg.modulation_mean_pct == pytest.approx((45.0 + 9 * 19.0) / 10)
        assert agg.modulation_min_pct == 19.0
        assert agg.heat_demand_during is True
        assert agg.heat_demand_after_stop is False
        assert cycle.end_reason is EndReason.DEMAND_ENDED
        assert agg.signal_coverage == pytest.approx(0.8)

    def test_unmapped_signals_give_none_and_zero_coverage(self) -> None:
        span = TimeRange(T0, T0 + HOUR_MS)
        agg = cycle_aggregates(TimeRange(T0 + 10 * M, T0 + 20 * M), [], CONFIG)
        assert agg.flow_max_c is None
        assert agg.modulation_mean_pct is None
        assert agg.heat_demand_during is None
        assert agg.heat_demand_after_stop is None
        assert agg.signal_coverage == 0.0
        flame = timeline(FLAME, span, on_off((10, 20)))
        assert cycle_aggregates(span, [flame], CONFIG).flow_mean_c is None

    def test_heat_demand_after_stop_true_during_demand(self) -> None:
        (cycle,) = run(on_off((10, 20)), T0 + HOUR_MS, demand=ALWAYS_DEMAND)
        assert cycle.aggregates.heat_demand_after_stop is True
        assert cycle.aggregates.heat_demand_during is True

    def test_heat_demand_absent_while_burning(self) -> None:
        (cycle,) = run(on_off((10, 20)), T0 + HOUR_MS, demand=[(T0, False, POLL)])
        assert cycle.aggregates.heat_demand_during is False


# --------------------------------------------------------------------------------------
# Property: chunked == whole for this stage (ADR-002 §4, §6)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class History:
    flame: list[Step]
    demand: list[Step]
    modes: list[tuple[TimestampMs, Mode]]
    horizons: list[TimestampMs]


@st.composite
def histories(draw: st.DrawFn) -> History:
    """Random flame/demand histories with data gaps, reconnect polls, random modes (incl.
    DHW and afterrun) and random chunk horizons."""
    flame: list[Step] = [(T0, False, POLL)]
    demand: list[Step] = [(T0, False, POLL)]
    modes: list[tuple[TimestampMs, Mode]] = [(T0, Mode.STANDBY)]
    t, on, wants, connected = T0, False, False, True
    for _ in range(draw(st.integers(min_value=1, max_value=60))):
        t += draw(st.integers(min_value=1, max_value=40)) * M // 2
        action = draw(st.sampled_from(["flame", "flame", "demand", "outage", "mode"]))
        if action == "flame" and connected:
            on = not on
            flame.append((t, on, CHANGE))
        elif action == "demand" and connected:
            wants = not wants
            demand.append((t, wants, CHANGE))
        elif action == "outage":
            connected = not connected
            if connected:  # reconnect: get_states yields polls, never transitions
                on = draw(st.booleans())
                flame.append((t, on, POLL))
                demand.append((t, wants, POLL))
            else:
                flame.append((t, None, CHANGE))
                demand.append((t, None, CHANGE))
        elif action == "mode":
            modes.append((t, draw(st.sampled_from(list(Mode)))))
    end = t + draw(st.integers(min_value=1, max_value=120)) * M
    cuts = draw(st.lists(st.integers(min_value=T0 + 1, max_value=end - 1), max_size=12))
    return History(flame, demand, modes, [*sorted(set(cuts)), end])


def _stage_run(history: History, w: AnalysisWindow) -> tuple[BurnerCycle, ...]:
    span = w.context
    assert span is not None
    timelines = [timeline(FLAME, span, history.flame), timeline(DEMAND, span, history.demand)]
    return detect_cycles(timelines, segments(history.modes, span), CONFIG, w)


def run_chunked(
    history: History, horizons: Sequence[TimestampMs], config: PipelineConfig = CONFIG
) -> dict[TimestampMs, BurnerCycle]:
    """Simulate the runner (ADR-002 §4.2-4.3) for stage 4 alone: replace-from upsert of
    cycles keyed ``>= emit_from``; the watermark is held by unsettled cycles."""
    store: dict[TimestampMs, BurnerCycle] = {}
    watermark = T0
    for horizon in horizons:
        w = AnalysisWindow.for_run(
            watermark=watermark,
            now=horizon + config.settle_ms,
            lookback_ms=config.lookback_ms,
            settle_ms=config.settle_ms,
            grid_ms=config.grid_ms,
        )
        cycles = _stage_run(history, w)
        store = {k: v for k, v in store.items() if k < w.emit_from}
        store.update({c.key: c for c in cycles if w.emits(c.key)})
        held = [
            c.start
            for c in cycles
            if (settles := cycle_settles_at(c, config)) is None or settles > w.end
        ]
        candidate = min([w.end - config.end_reason_lookahead_ms, *held])
        watermark = min(max(candidate, w.emit_from), w.end)
    return store


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(histories())
def test_chunked_equals_whole(history: History) -> None:
    whole = run_chunked(history, history.horizons[-1:])
    chunked = run_chunked(history, history.horizons)
    assert chunked == whole


def test_chunked_equals_whole_long_cycle_beyond_lookback() -> None:
    """A cycle burning longer than the lookback holds the watermark (ADR-002 §4.4)."""
    history = History(
        flame=on_off((30, 30 + 8 * 60)),
        demand=[(T0, True, POLL)],
        modes=[(T0, Mode.CH), (T0 + (30 + 8 * 60) * M, Mode.AFTERRUN)],
        horizons=[T0 + h * HOUR_MS + 7 * M for h in range(1, 12)],
    )
    whole = run_chunked(history, history.horizons[-1:])
    chunked = run_chunked(history, history.horizons)
    assert chunked == whole
    (cycle,) = whole.values()
    assert cycle.complete
    assert cycle.duration_ms == 8 * HOUR_MS
