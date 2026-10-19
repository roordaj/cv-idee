"""Stage 3 — operating modes (FR-09; ADR-002 §3.3, §4.5, §6; scenarios 4 and 10).

Timelines are built by hand: stages 1-2 are not under test here.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from cvidee.analysis.cycles import detect_cycles
from cvidee.analysis.modes import (
    classify_modes,
    map_mode_code,
    merge_segments,
    mode_code,
    split_on_grid,
)
from cvidee.analysis.types import (
    HOUR_MS,
    MINUTE_MS,
    PROVISIONAL_MODE_MAPPING,
    AnalysisWindow,
    CyclePhase,
    EndReason,
    Mode,
    ModeCertainty,
    ModeSegment,
    ObservationKind,
    ObservedValue,
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
)

T0: TimestampMs = 1_790_000_000_000 - (1_790_000_000_000 % HOUR_MS)
"""A whole UTC hour in late Sept 2026."""
M = MINUTE_MS

STATUS = SignalRef(Role.OPERATING_MODE)
FLAME = SignalRef(Role.FLAME)
DEMAND = SignalRef(Role.HEAT_DEMAND)
SETPOINT = SignalRef(Role.FLOW_SETPOINT)
PUMP = SignalRef(Role.PUMP_STATE)

CONFIG = PipelineConfig(
    signals=tuple(
        SignalConfig(s, Provenance(ValueKind.REPORTED, f"sensor.{s.role}"))
        for s in (STATUS, FLAME, DEMAND, SETPOINT, PUMP)
    ),
    mode_mapping=(*PROVISIONAL_MODE_MAPPING, ("9", Mode.FAULT_BLOCKING)),
    config_hash="test",
)

CHANGE, POLL = ObservationKind.CHANGE, ObservationKind.POLL
DIRECT, INFERRED, NONE = ModeCertainty.DIRECT, ModeCertainty.INFERRED, ModeCertainty.NONE

type Step = tuple[TimestampMs, ObservedValue | None, ObservationKind]
"""``(ts, value, kind)``; ``value is None`` = unknown (disconnected) from ``ts``."""


def timeline(signal: SignalRef, span: TimeRange, steps: Sequence[Step]) -> SignalTimeline:
    """Timeline of ``steps`` over ``span`` as stage 1 would build it (carry-in clipped to the
    span start, ``NO_DATA`` before the first step, ``None`` → ``DISCONNECTED``)."""
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


def at(minute: float, value: ObservedValue | None, kind: ObservationKind = CHANGE) -> Step:
    return (T0 + int(minute * M), value, kind)


def window(end: TimestampMs, start: TimestampMs = T0) -> AnalysisWindow:
    return AnalysisWindow(context_start=start, emit_from=start, end=end)


def timelines_for(
    span: TimeRange, signals: Mapping[SignalRef, Sequence[Step]]
) -> list[SignalTimeline]:
    return [timeline(s, span, steps) for s, steps in signals.items()]


def classify(
    signals: dict[SignalRef, Sequence[Step]],
    end: TimestampMs = T0 + HOUR_MS,
    config: PipelineConfig = CONFIG,
) -> tuple[ModeSegment, ...]:
    w = window(end)
    assert w.context is not None
    return classify_modes(timelines_for(w.context, signals), config, w)


def summary(
    segments: Sequence[ModeSegment],
) -> list[tuple[float, float, Mode, ModeCertainty]]:
    """Merged segments as ``(start_min, end_min, mode, certainty)`` relative to ``T0``."""
    return [
        ((s.start - T0) / M, (s.end - T0) / M, s.mode, s.certainty)
        for s in merge_segments(segments)
    ]


def assert_partition(segments: Sequence[ModeSegment], rng: TimeRange) -> None:
    assert segments[0].start == rng.start
    assert segments[-1].end == rng.end
    for a, b in pairwise(segments):
        assert a.end == b.start
    for s in segments:
        assert s.start // HOUR_MS == (s.end - 1) // HOUR_MS, "segment crosses an hour"


OFF = [at(-10, False, POLL)]
NO_DEMAND = [at(-10, False, POLL)]
ALWAYS_DEMAND = [at(-10, True, POLL)]


# --------------------------------------------------------------------------------------
# Status codes
# --------------------------------------------------------------------------------------


class TestModeCodes:
    def test_map_mode_code(self) -> None:
        mapping = (("1", Mode.CH), ("2", Mode.DHW), ("2", Mode.STANDBY))
        assert map_mode_code("1", mapping) is Mode.CH
        assert map_mode_code(" 2 ", mapping) is Mode.DHW  # first match wins
        assert map_mode_code("7", mapping) is None

    @pytest.mark.parametrize(
        ("value", "code"),
        [("1", "1"), (" 2 ", "2"), (1.0, "1"), (2, "2"), (1.5, None), (True, None), ("", None)],
    )
    def test_mode_code_normalisation(self, value: ObservedValue, code: str | None) -> None:
        assert mode_code(value) == code

    def test_mode_code_nan_is_not_a_code(self) -> None:
        assert mode_code(float("nan")) is None

    def test_no_unvalidated_default_mapping(self) -> None:
        """Design v3: "Statuscode ketel; 1 = CV, 2 = tapwater" (to be confirmed by #5)."""
        default = PipelineConfig(signals=())
        assert default.mode_mapping == ()
        assert map_mode_code("1", default.mode_mapping) is None
        assert map_mode_code("2", default.mode_mapping) is None


class TestDirect:
    def test_status_signal_gives_direct_certainty(self) -> None:
        segments = classify(
            {
                STATUS: [at(-10, "1", POLL), at(20, "2"), at(30, 1.0)],
                FLAME: [at(-10, True, POLL)],
                DEMAND: ALWAYS_DEMAND,
            }
        )
        assert summary(segments) == [
            (0, 20, Mode.CH, DIRECT),
            (20, 30, Mode.DHW, DIRECT),
            (30, 60, Mode.CH, DIRECT),
        ]
        assert all(s.sources == (STATUS,) for s in segments)

    def test_dhw_status_wins_over_heat_demand(self) -> None:
        """Scenario 4: tap water heating during CH demand is never classified CH."""
        segments = classify(
            {
                STATUS: [at(-10, "2", POLL)],
                FLAME: [at(-10, True, POLL)],
                DEMAND: ALWAYS_DEMAND,
            }
        )
        assert summary(segments) == [(0, 60, Mode.DHW, DIRECT)]

    def test_fault_code_is_device_reported(self) -> None:
        """Requirements §8: faults are device messages with their source."""
        segments = classify(
            {STATUS: [at(-10, "1", POLL), at(10, "9"), at(25, "1")], FLAME: OFF, DEMAND: OFF}
        )
        fault = [s for s in segments if s.mode is Mode.FAULT_BLOCKING]
        assert [(f.start, f.end, f.certainty, f.sources) for f in fault] == [
            (T0 + 10 * M, T0 + 25 * M, DIRECT, (STATUS,))
        ]

    def test_fault_is_never_inferred(self) -> None:
        segments = classify({FLAME: [at(-10, None)], DEMAND: [at(-10, None)]})
        assert all(s.mode is not Mode.FAULT_BLOCKING for s in segments)

    def test_unmapped_code_stays_unknown(self) -> None:
        segments = classify(
            {STATUS: [at(-10, "0", POLL)], FLAME: [at(-10, True, POLL)], DEMAND: ALWAYS_DEMAND}
        )
        assert summary(segments) == [(0, 60, Mode.UNKNOWN, NONE)]

    def test_unknown_status_stays_unknown(self) -> None:
        segments = classify(
            {STATUS: [at(-10, None)], FLAME: [at(-10, False, POLL)], DEMAND: NO_DEMAND}
        )
        assert summary(segments) == [(0, 60, Mode.UNKNOWN, NONE)]

    def test_mapping_is_configurable(self) -> None:
        config = PipelineConfig(signals=CONFIG.signals, mode_mapping=(("dhw", Mode.DHW),))
        segments = classify({STATUS: [at(-10, "dhw", POLL)]}, config=config)
        assert summary(segments) == [(0, 60, Mode.DHW, DIRECT)]


# --------------------------------------------------------------------------------------
# Inference without a mode signal (limited certainty)
# --------------------------------------------------------------------------------------


class TestInferred:
    def test_missing_mode_signal_gives_limited_certainty(self) -> None:
        """FR-09: missing mode data ⇒ limited certainty (never DIRECT)."""
        segments = classify(
            {
                FLAME: [at(-10, False, POLL), at(10, True), at(20, False)],
                DEMAND: [at(-10, False, POLL), at(5, True), at(25, False)],
            }
        )
        assert summary(segments) == [
            (0, 5, Mode.STANDBY, INFERRED),
            (5, 25, Mode.CH, INFERRED),
            (25, 60, Mode.STANDBY, INFERRED),
        ]
        assert {s.sources for s in segments} == {(FLAME, DEMAND)}

    def test_burning_without_demand_is_dhw(self) -> None:
        """Scenario 4 without a mode signal: a burn without heat demand is tap water."""
        segments = classify(
            {FLAME: [at(-10, False, POLL), at(10, True), at(14, False)], DEMAND: NO_DEMAND}
        )
        assert summary(segments) == [
            (0, 10, Mode.STANDBY, INFERRED),
            (10, 14, Mode.DHW, INFERRED),
            (14, 60, Mode.STANDBY, INFERRED),
        ]

    def test_burner_winding_down_after_demand_ended_stays_ch(self) -> None:
        segments = classify(
            {
                FLAME: [at(-10, False, POLL), at(10, True), at(21, False)],
                DEMAND: [at(-10, True, POLL), at(20, False)],
            }
        )
        assert summary(segments) == [
            (0, 21, Mode.CH, INFERRED),
            (21, 60, Mode.STANDBY, INFERRED),
        ]

    def test_demand_grace_is_bounded(self) -> None:
        segments = classify(
            {
                FLAME: [at(-10, False, POLL), at(10, True), at(50, False)],
                DEMAND: [at(-10, True, POLL), at(20, False)],
            }
        )
        assert summary(segments) == [
            (0, 35, Mode.CH, INFERRED),
            (35, 50, Mode.DHW, INFERRED),
            (50, 60, Mode.STANDBY, INFERRED),
        ]

    def test_flow_setpoint_as_demand_proxy(self) -> None:
        segments = classify(
            {
                FLAME: [at(-10, True, POLL), at(30, False)],
                SETPOINT: [at(-10, 55.0, POLL), at(20, 0.0)],
            }
        )
        assert summary(segments) == [
            (0, 30, Mode.CH, INFERRED),
            (30, 60, Mode.STANDBY, INFERRED),
        ]
        assert segments[0].sources == (FLAME, SETPOINT)

    def test_heat_demand_preferred_over_setpoint(self) -> None:
        segments = classify(
            {FLAME: [at(-10, True, POLL)], DEMAND: NO_DEMAND, SETPOINT: [at(-10, 60.0, POLL)]}
        )
        assert summary(segments) == [(0, 60, Mode.DHW, INFERRED)]


# --------------------------------------------------------------------------------------
# Afterrun
# --------------------------------------------------------------------------------------


class TestAfterrun:
    def _signals(self, pump: Sequence[Step]) -> dict[SignalRef, Sequence[Step]]:
        return {
            FLAME: [at(-10, False, POLL), at(5, True), at(10, False)],
            DEMAND: [at(-10, True, POLL), at(10, False)],
            PUMP: pump,
        }

    def test_pump_after_flame_off_without_demand(self) -> None:
        segments = classify(self._signals([at(-10, True, POLL), at(14, False)]))
        assert summary(segments) == [
            (0, 10, Mode.CH, INFERRED),
            (10, 14, Mode.AFTERRUN, INFERRED),
            (14, 60, Mode.STANDBY, INFERRED),
        ]
        afterrun = [s for s in segments if s.mode is Mode.AFTERRUN]
        assert afterrun[0].sources == (FLAME, DEMAND, PUMP)

    def test_afterrun_is_bounded(self) -> None:
        segments = classify(self._signals([at(-10, True, POLL)]))
        assert summary(segments) == [
            (0, 10, Mode.CH, INFERRED),
            (10, 25, Mode.AFTERRUN, INFERRED),
            (25, 60, Mode.STANDBY, INFERRED),
        ]

    def test_afterrun_ends_at_first_pump_off(self) -> None:
        segments = classify(
            self._signals([at(-10, True, POLL), at(12, False), at(14, True), at(16, False)])
        )
        assert summary(segments) == [
            (0, 10, Mode.CH, INFERRED),
            (10, 12, Mode.AFTERRUN, INFERRED),
            (12, 60, Mode.STANDBY, INFERRED),
        ]

    def test_without_pump_signal_no_afterrun_is_inferred(self) -> None:
        signals = self._signals([])
        del signals[PUMP]
        segments = classify(signals)
        assert summary(segments) == [
            (0, 10, Mode.CH, INFERRED),
            (10, 60, Mode.STANDBY, INFERRED),
        ]

    def test_unknown_pump_in_afterrun_window_is_unknown(self) -> None:
        segments = classify(self._signals([at(-10, None)]))
        assert summary(segments) == [
            (0, 10, Mode.CH, INFERRED),
            (10, 25, Mode.UNKNOWN, NONE),
            (25, 60, Mode.STANDBY, INFERRED),
        ]

    def test_pump_without_preceding_flame_is_standby(self) -> None:
        segments = classify({FLAME: OFF, DEMAND: NO_DEMAND, PUMP: [at(-10, True, POLL)]})
        assert summary(segments) == [(0, 60, Mode.STANDBY, INFERRED)]

    def test_afterrun_status_code(self) -> None:
        config = PipelineConfig(
            signals=CONFIG.signals, mode_mapping=(*PROVISIONAL_MODE_MAPPING, ("6", Mode.AFTERRUN))
        )
        segments = classify(
            {STATUS: [at(-10, "1", POLL), at(10, "6"), at(13, "0")], FLAME: OFF, DEMAND: OFF},
            config=config,
        )
        assert summary(segments) == [
            (0, 10, Mode.CH, DIRECT),
            (10, 13, Mode.AFTERRUN, DIRECT),
            (13, 60, Mode.UNKNOWN, NONE),
        ]


# --------------------------------------------------------------------------------------
# Unknown is never standby (FR-11, scenario 10)
# --------------------------------------------------------------------------------------


class TestUnknown:
    def test_no_signals_gives_unknown(self) -> None:
        end = T0 + 3 * HOUR_MS
        segments = classify({}, end=end)
        assert summary(segments) == [(0, 180, Mode.UNKNOWN, NONE)]
        assert len(segments) == 3  # split on whole hours
        assert all(s.sources == () for s in segments)

    def test_unknown_flame_is_unknown_not_standby(self) -> None:
        segments = classify(
            {FLAME: [at(-10, False, POLL), at(10, None), at(40, False, POLL)], DEMAND: NO_DEMAND}
        )
        assert summary(segments) == [
            (0, 10, Mode.STANDBY, INFERRED),
            (10, 40, Mode.UNKNOWN, NONE),
            (40, 60, Mode.STANDBY, INFERRED),
        ]

    def test_unknown_demand_is_unknown(self) -> None:
        segments = classify({FLAME: [at(-10, False, POLL), at(30, True)], DEMAND: [at(-10, None)]})
        assert summary(segments) == [(0, 60, Mode.UNKNOWN, NONE)]

    def test_flame_only_is_unknown(self) -> None:
        segments = classify({FLAME: [at(-10, True, POLL), at(30, False)]})
        assert summary(segments) == [(0, 60, Mode.UNKNOWN, NONE)]

    def test_no_data_before_first_observation(self) -> None:
        segments = classify({FLAME: [at(15, False, POLL)], DEMAND: [at(15, False, POLL)]})
        assert summary(segments) == [
            (0, 15, Mode.UNKNOWN, NONE),
            (15, 60, Mode.STANDBY, INFERRED),
        ]

    def test_flame_on_after_reconnect_has_no_afterrun_history(self) -> None:
        """Flame-off right after a gap has no known flame-off transition: no afterrun."""
        segments = classify(
            {
                FLAME: [at(-10, None), at(10, False, POLL)],
                DEMAND: NO_DEMAND,
                PUMP: [at(-10, True, POLL)],
            }
        )
        assert summary(segments) == [
            (0, 10, Mode.UNKNOWN, NONE),
            (10, 60, Mode.STANDBY, INFERRED),
        ]

    def test_outage_during_afterrun_is_unknown_and_afterrun_does_not_resume(self) -> None:
        """ADR-003 §5.4: no value carries over an outage, so neither does the afterrun."""
        segments = classify(
            {
                FLAME: [at(-10, True, POLL), at(10, False), at(12, None), at(15, False, POLL)],
                DEMAND: [at(-10, True, POLL), at(10, False), at(12, None), at(15, False, POLL)],
                PUMP: [at(-10, True, POLL), at(12, None), at(15, True, POLL)],
            }
        )
        assert summary(segments) == [
            (0, 10, Mode.CH, INFERRED),
            (10, 12, Mode.AFTERRUN, INFERRED),
            (12, 15, Mode.UNKNOWN, NONE),
            (15, 60, Mode.STANDBY, INFERRED),
        ]

    def test_empty_window(self) -> None:
        assert classify_modes([], CONFIG, AnalysisWindow(T0, T0, T0)) == ()


# --------------------------------------------------------------------------------------
# Canonical grid, merging, determinism
# --------------------------------------------------------------------------------------


class TestGrid:
    SIGNALS: dict[SignalRef, Sequence[Step]] = {  # noqa: RUF012
        FLAME: [at(-10, False, POLL), at(50, True), at(130, False), at(170, True)],
        DEMAND: [at(-10, True, POLL), at(125, False)],
        PUMP: [at(-10, True, POLL)],
        STATUS: [at(100, None), at(110, "2"), at(115, "0")],
    }
    END = T0 + 3 * HOUR_MS + 17 * M

    def test_segments_partition_the_context_on_whole_hours(self) -> None:
        segments = classify(self.SIGNALS, end=self.END)
        assert_partition(segments, TimeRange(T0, self.END))
        assert segments == tuple(sorted(segments, key=lambda s: s.start))

    def test_split_merge_round_trip(self) -> None:
        segments = classify(self.SIGNALS, end=self.END)
        merged = merge_segments(segments)
        assert split_on_grid(merged, HOUR_MS) == segments
        assert merge_segments(split_on_grid(merged, HOUR_MS)) == merged
        # merged segments are maximal: neighbours always differ
        for a, b in pairwise(merged):
            assert (a.mode, a.certainty, a.sources) != (b.mode, b.certainty, b.sources)

    def test_split_on_grid(self) -> None:
        segment = ModeSegment(T0 + 30 * M, T0 + 150 * M, Mode.CH, INFERRED, (FLAME,), True)
        parts = split_on_grid([segment], HOUR_MS)
        assert [(p.start, p.end) for p in parts] == [
            (T0 + 30 * M, T0 + HOUR_MS),
            (T0 + HOUR_MS, T0 + 2 * HOUR_MS),
            (T0 + 2 * HOUR_MS, T0 + 150 * M),
        ]
        assert all(p.final and p.sources == (FLAME,) for p in parts)
        assert merge_segments(parts) == (segment,)

    def test_merge_final_only_if_all_parts_final(self) -> None:
        a = ModeSegment(T0, T0 + M, Mode.CH, INFERRED, (), True)
        b = ModeSegment(T0 + M, T0 + 2 * M, Mode.CH, INFERRED, (), False)
        assert merge_segments([b, a]) == (ModeSegment(T0, T0 + 2 * M, Mode.CH, INFERRED),)

    def test_input_order_is_irrelevant(self) -> None:
        w = window(self.END)
        assert w.context is not None
        timelines = timelines_for(w.context, self.SIGNALS)
        expected = classify_modes(timelines, CONFIG, w)
        rnd = random.Random(7)
        for _ in range(5):
            shuffled = list(timelines)
            rnd.shuffle(shuffled)
            assert classify_modes(shuffled, CONFIG, w) == expected

    def test_unrelated_timelines_are_ignored(self) -> None:
        w = window(self.END)
        assert w.context is not None
        timelines = timelines_for(w.context, self.SIGNALS)
        flow = timeline(SignalRef(Role.FLOW_TEMPERATURE), w.context, [at(-10, 40.0, POLL)])
        assert classify_modes([*timelines, flow], CONFIG, w) == classify_modes(timelines, CONFIG, w)


# --------------------------------------------------------------------------------------
# Integration: modes → cycles (stage 3 output fits stage 4)
# --------------------------------------------------------------------------------------


class TestModesToCycles:
    def test_dhw_cycle_by_status_is_excluded_from_ch(self) -> None:
        """Scenario 4: a tap-water cycle during CH demand is a DHW cycle."""
        signals: dict[SignalRef, Sequence[Step]] = {
            STATUS: [at(-10, "1", POLL), at(10, "2"), at(14, "1")],
            FLAME: [at(-10, False, POLL), at(10, True), at(14, False)],
            DEMAND: ALWAYS_DEMAND,
        }
        w = window(T0 + HOUR_MS)
        assert w.context is not None
        timelines = timelines_for(w.context, signals)
        (cycle,) = detect_cycles(timelines, classify_modes(timelines, CONFIG, w), CONFIG, w)
        assert cycle.mode is Mode.DHW
        assert cycle.end_reason is EndReason.DHW_ENDED

    def test_inferred_ch_cycle_with_afterrun_across_hour_boundary(self) -> None:
        signals: dict[SignalRef, Sequence[Step]] = {
            FLAME: [at(-10, False, POLL), at(40, True), at(55, False)],
            DEMAND: [at(-10, True, POLL), at(54.5, False)],
            PUMP: [at(-10, True, POLL), at(65, False)],
        }
        w = window(T0 + 2 * HOUR_MS)
        assert w.context is not None
        timelines = timelines_for(w.context, signals)
        modes = classify_modes(timelines, CONFIG, w)
        afterrun = [(s.start, s.end) for s in modes if s.mode is Mode.AFTERRUN]
        assert afterrun == [(T0 + 55 * M, T0 + HOUR_MS), (T0 + HOUR_MS, T0 + 65 * M)]
        (cycle,) = detect_cycles(timelines, modes, CONFIG, w)
        assert cycle.mode is Mode.CH
        assert cycle.end_reason is EndReason.DEMAND_ENDED
        phase = cycle.phases[-1]
        assert (phase.phase, phase.start, phase.end) == (
            CyclePhase.AFTERRUN,
            T0 + 55 * M,
            T0 + 65 * M,
        )

    def test_inferred_dhw_cycle_without_demand(self) -> None:
        signals: dict[SignalRef, Sequence[Step]] = {
            FLAME: [at(-10, False, POLL), at(10, True), at(13, False)],
            DEMAND: NO_DEMAND,
        }
        w = window(T0 + HOUR_MS)
        assert w.context is not None
        timelines = timelines_for(w.context, signals)
        (cycle,) = detect_cycles(timelines, classify_modes(timelines, CONFIG, w), CONFIG, w)
        assert cycle.mode is Mode.DHW

    def test_unknown_mode_cycle(self) -> None:
        signals: dict[SignalRef, Sequence[Step]] = {
            FLAME: [at(-10, False, POLL), at(10, True), at(13, False)],
        }
        w = window(T0 + HOUR_MS)
        assert w.context is not None
        timelines = timelines_for(w.context, signals)
        (cycle,) = detect_cycles(timelines, classify_modes(timelines, CONFIG, w), CONFIG, w)
        assert cycle.mode is Mode.UNKNOWN


# --------------------------------------------------------------------------------------
# Property: chunked == whole for this stage (ADR-002 §4, §6)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class History:
    signals: dict[SignalRef, list[Step]]
    horizons: list[TimestampMs]
    holds: list[int]
    """Per run: how many grid steps an (imaginary) open cycle holds the watermark back."""


@st.composite
def histories(draw: st.DrawFn) -> History:
    """Random status/flame/demand/setpoint/pump histories with outages and random chunks."""
    signals: dict[SignalRef, list[Step]] = {
        STATUS: [(T0, draw(st.sampled_from(["0", "1", "2"])), POLL)],
        FLAME: [(T0, False, POLL)],
        DEMAND: [(T0, False, POLL)],
        SETPOINT: [(T0, 0.0, POLL)],
        PUMP: [(T0, False, POLL)],
    }
    values: dict[SignalRef, st.SearchStrategy[ObservedValue]] = {
        STATUS: st.sampled_from(["0", "1", "2", "9", "x"]),
        FLAME: st.booleans(),
        DEMAND: st.booleans(),
        SETPOINT: st.sampled_from([0.0, 10.0, 45.0, 60.0]),
        PUMP: st.booleans(),
    }
    t = T0
    for _ in range(draw(st.integers(min_value=1, max_value=60))):
        t += draw(st.integers(min_value=1, max_value=40)) * M // 2
        signal = draw(st.sampled_from(sorted(values)))
        value: ObservedValue | None = draw(st.one_of(st.none(), values[signal]))
        kind = POLL if value is None else draw(st.sampled_from([CHANGE, CHANGE, POLL]))
        signals[signal].append((t, value, kind))
    end = t + draw(st.integers(min_value=1, max_value=120)) * M
    cuts = draw(st.lists(st.integers(min_value=T0 + 1, max_value=end - 1), max_size=12))
    horizons = [*sorted(set(cuts)), end]
    holds = draw(st.lists(st.integers(0, 3), min_size=len(horizons), max_size=len(horizons)))
    return History(signals, horizons, holds)


def run_chunked(
    history: History, horizons: Sequence[TimestampMs], holds: Sequence[int]
) -> dict[TimestampMs, ModeSegment]:
    """Simulate the runner (ADR-002 §4.2-4.3) for stage 3: replace-from upsert of segments
    keyed ``>= emit_from``. The watermark is ``end - lookahead``, optionally held back
    further (as an open cycle would)."""
    store: dict[TimestampMs, ModeSegment] = {}
    watermark = T0
    for horizon, hold in zip(horizons, holds, strict=True):
        w = AnalysisWindow.for_run(
            watermark=watermark,
            now=horizon + CONFIG.settle_ms,
            lookback_ms=CONFIG.lookback_ms,
            settle_ms=CONFIG.settle_ms,
            grid_ms=CONFIG.grid_ms,
        )
        span = w.context
        assert span is not None
        timelines = timelines_for(span, history.signals)
        segments = classify_modes(timelines, CONFIG, w)
        assert_partition(segments, span)
        store = {k: v for k, v in store.items() if k < w.emit_from}
        store.update({s.start: s for s in segments if w.emits(s.start)})
        candidate = w.end - CONFIG.end_reason_lookahead_ms - hold * CONFIG.grid_ms
        watermark = min(max(candidate, w.emit_from), w.end)
    return store


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(histories())
def test_chunked_equals_whole(history: History) -> None:
    whole = run_chunked(history, history.horizons[-1:], [0])
    chunked = run_chunked(history, history.horizons, history.holds)
    assert chunked == whole
    # The stored segments partition the whole range on the grid.
    ordered = [chunked[k] for k in sorted(chunked)]
    assert_partition(ordered, TimeRange(T0, history.horizons[-1]))
