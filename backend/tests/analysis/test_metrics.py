"""Stage 5 — cycle and temperature metrics (FR-13, FR-15; ADR-002 §3.5)."""

from __future__ import annotations

from collections.abc import Sequence

from cvidee.analysis.metrics_cycles import (
    grid_buckets,
    hourly_cycle_metrics,
    summarize_cycles,
)
from cvidee.analysis.metrics_temperature import (
    cycle_temperature_metrics,
    hourly_temperature_metrics,
)
from cvidee.analysis.pipeline import run_pipeline
from cvidee.analysis.types import (
    HOUR_MS,
    BurnerCycle,
    CyclePhase,
    EndReason,
    MetricName,
    MetricValue,
    MetricWindowKind,
    Mode,
    ObservationKind,
    PhaseSpan,
    PipelineConfig,
    Provenance,
    SignalConfig,
    SignalTimeline,
    TimeRange,
    ValueKind,
)
from tests.analysis.test_cycles import (
    ALWAYS_DEMAND,
    CONFIG,
    DEMAND,
    FLAME,
    FLOW,
    RETURN,
    SETPOINT,
    T0,
    M,
    Step,
    segments,
    timeline,
    window,
)
from tests.scenarios.harness import load_build, run_stages, scenario_dirs

P = ObservationKind.POLL


def cyc(
    start_min: float,
    end_min: float,
    *,
    mode: Mode = Mode.CH,
    reason: EndReason = EndReason.STOP_DURING_DEMAND,
    pause_min: float | None = None,
    complete: bool = True,
) -> BurnerCycle:
    start, end = T0 + round(start_min * M), T0 + round(end_min * M)
    return BurnerCycle(
        start=start,
        end=end,
        duration_ms=end - start,
        complete=complete,
        start_observed=True,
        mode=mode,
        end_reason=reason,
        pause_before_ms=None if pause_min is None else round(pause_min * M),
    )


def by_name(
    values: Sequence[MetricValue], name: MetricName, mode: Mode | None = Mode.CH
) -> MetricValue:
    (found,) = [v for v in values if v.name is name and v.mode is mode]
    return found


def hourly_for(
    cycles: Sequence[BurnerCycle], hours: int, flame_steps: Sequence[Step] | None = None
) -> tuple[MetricValue, ...]:
    end = T0 + hours * HOUR_MS
    span = TimeRange(T0, end)
    flame = timeline(FLAME, span, flame_steps or [(T0, False, P)])
    demand = timeline(DEMAND, span, ALWAYS_DEMAND)
    modes = segments([(T0, Mode.CH)], span)
    return hourly_cycle_metrics(
        cycles, modes, flame, demand, grid_buckets(window(end), HOUR_MS), CONFIG
    )


class TestCycleMetrics:
    def test_starts_per_observed_hour_exposes_time_basis(self) -> None:
        # 6 h, flame unknown for 30 min: basis 5.5 h.
        flame: list[Step] = [
            (T0, False, P),
            (T0 + 2 * HOUR_MS, None, P),
            (T0 + 2 * HOUR_MS + 30 * M, False, P),
        ]
        cycles = [
            cyc(10, 20),
            cyc(40, 50),
            cyc(70, 80),
            cyc(200, 210),
            cyc(260, 270),
            cyc(300, 310),
        ]
        hourly = hourly_for(cycles, 6, flame)
        period = TimeRange(T0, T0 + 6 * HOUR_MS)
        out = summarize_cycles(cycles, hourly, period, CONFIG, short_cycle_ms=15 * M)
        sph = by_name(out, MetricName.STARTS_PER_HOUR)
        assert sph.time_basis_seconds == 5.5 * 3600
        assert abs((sph.value or 0) - 6 / 5.5) < 1e-9
        assert abs(sph.coverage - 5.5 / 6) < 1e-9

    def test_long_standby_does_not_mask_pattern_during_demand(self) -> None:
        cycles = [
            cyc(0, 5),
            cyc(10, 15, pause_min=5),
            cyc(20, 25, pause_min=5),
            # 3 h of standby afterwards: the pause stays None, never a 3 h "pause".
            cyc(205, 210),
        ]
        out = summarize_cycles(
            cycles,
            hourly_for(cycles, 4),
            TimeRange(T0, T0 + 4 * HOUR_MS),
            CONFIG,
            short_cycle_ms=15 * M,
        )
        assert by_name(out, MetricName.PAUSE_DURATION_MEDIAN).value == 5 * 60
        assert by_name(out, MetricName.SHORT_CYCLES).value == 4
        assert by_name(out, MetricName.STARTS).value == 4

    def test_pause_after_demand_ended_is_not_a_pause(self) -> None:
        cycles = [cyc(0, 5, reason=EndReason.DEMAND_ENDED), cyc(10, 15, pause_min=5)]
        out = summarize_cycles(
            cycles, hourly_for(cycles, 1), TimeRange(T0, T0 + HOUR_MS), CONFIG, short_cycle_ms=M
        )
        assert by_name(out, MetricName.PAUSE_DURATION_MEDIAN).value is None

    def test_dhw_and_incomplete_are_separate(self) -> None:
        cycles = [
            cyc(0, 10),
            cyc(20, 21, mode=Mode.DHW, reason=EndReason.DHW_ENDED),
            cyc(30, 40, reason=EndReason.DATA_GAP, complete=False),
        ]
        out = summarize_cycles(
            cycles,
            hourly_for(cycles, 1),
            TimeRange(T0, T0 + HOUR_MS),
            CONFIG,
            short_cycle_ms=15 * M,
            kind=MetricWindowKind.DAY,
        )
        assert by_name(out, MetricName.STARTS, Mode.DHW).value == 1
        assert by_name(out, MetricName.INCOMPLETE_CYCLES).value == 1
        assert by_name(out, MetricName.BURN_DURATION_MEAN).value == 600
        assert by_name(out, MetricName.SHORT_CYCLE_SHARE).value == 1.0
        assert all(m.window.kind is MetricWindowKind.DAY for m in out)

    def test_no_observed_time_gives_no_value(self) -> None:
        out = summarize_cycles([], [], TimeRange(T0, T0 + HOUR_MS), CONFIG, short_cycle_ms=M)
        assert by_name(out, MetricName.STARTS_PER_HOUR).value is None

    def test_hourly_starts_counted_in_start_bucket(self) -> None:
        hourly = hourly_for([cyc(50, 70)], 2)
        starts = [m for m in hourly if m.name is MetricName.STARTS and m.mode is Mode.CH]
        burn = [m for m in hourly if m.name is MetricName.BURN_TIME and m.mode is Mode.CH]
        assert [m.value for m in starts] == [1, 0]
        assert [m.value for m in burn] == [600, 600]


def temp_timelines(
    *, flow: Sequence[Step], ret: Sequence[Step], setpoint: Sequence[Step]
) -> list[SignalTimeline]:
    span = TimeRange(T0, T0 + HOUR_MS)
    return [
        timeline(FLOW, span, flow),
        timeline(RETURN, span, ret),
        timeline(SETPOINT, span, setpoint),
    ]


def ch_cycle_with_phases() -> BurnerCycle:
    base = cyc(0, 20)
    return BurnerCycle(
        start=base.start,
        end=base.end,
        duration_ms=base.duration_ms,
        complete=True,
        start_observed=True,
        mode=Mode.CH,
        end_reason=EndReason.STOP_DURING_DEMAND,
        phases=(
            PhaseSpan(CyclePhase.STARTUP, T0, T0 + 2 * M),
            PhaseSpan(CyclePhase.STABLE, T0 + 2 * M, T0 + 20 * M),
            PhaseSpan(CyclePhase.AFTERRUN, T0 + 20 * M, T0 + 22 * M),
        ),
    )


class TestTemperatureMetrics:
    def test_overshoot_rate_and_stable_delta_t(self) -> None:
        tl = temp_timelines(
            flow=[
                (T0, 30.0, P),
                (T0 + 2 * M, 45.0, P),
                (T0 + 10 * M, 52.0, P),
                (T0 + 20 * M, 40.0, P),
            ],
            ret=[
                (T0, 28.0, P),
                (T0 + 2 * M, 35.0, P),
                (T0 + 10 * M, 35.0, ObservationKind.CONFIRM),
                (T0 + 20 * M, 38.0, P),
            ],
            setpoint=[(T0, 50.0, P)],
        )
        out = cycle_temperature_metrics([ch_cycle_with_phases()], tl, CONFIG)
        assert by_name(out, MetricName.OVERSHOOT).value == 2.0
        assert by_name(out, MetricName.OVERSHOOT_AT_STOP).value == 2.0
        assert by_name(out, MetricName.HEATING_RATE).value == 7.5  # 30 -> 45 K over 2 min
        stable_dt = by_name(out, MetricName.BOILER_DELTA_T_STABLE)
        assert abs((stable_dt.value or 0) - (8 * 10 + 10 * 17) / 18) < 1e-9
        assert stable_dt.time_basis_seconds == 18 * 60
        # Startup and afterrun are separate from stable.
        assert by_name(out, MetricName.BOILER_DELTA_T_STARTUP).value == 2.0
        assert by_name(out, MetricName.BOILER_DELTA_T_AFTERRUN).value == 2.0
        assert all(m.window.kind is MetricWindowKind.CYCLE for m in out)

    def test_dhw_cycle_is_skipped(self) -> None:
        tl = temp_timelines(flow=[(T0, 71.0, P)], ret=[(T0, 50.0, P)], setpoint=[(T0, 50.0, P)])
        dhw = cyc(0, 20, mode=Mode.DHW, reason=EndReason.DHW_ENDED)
        assert cycle_temperature_metrics([dhw], tl, CONFIG) == ()
        assert hourly_temperature_metrics([dhw], tl, [TimeRange(T0, T0 + HOUR_MS)], CONFIG) == ()

    def test_hourly_means_use_stable_only(self) -> None:
        tl = temp_timelines(
            flow=[(T0, 90.0, P), (T0 + 2 * M, 50.0, P)],
            ret=[(T0, 30.0, P), (T0 + 2 * M, 40.0, P)],
            setpoint=[(T0, 50.0, P)],
        )
        out = hourly_temperature_metrics(
            [ch_cycle_with_phases()], tl, [TimeRange(T0, T0 + HOUR_MS)], CONFIG
        )
        assert by_name(out, MetricName.FLOW_MEAN_STABLE).value == 50.0
        assert by_name(out, MetricName.BOILER_DELTA_T_STABLE).value == 10.0

    def test_misaligned_pair_is_flagged_not_combined(self) -> None:
        cfg = PipelineConfig(
            signals=tuple(
                SignalConfig(
                    s,
                    Provenance(ValueKind.REPORTED, "x"),
                    heartbeat_expected=True,
                    max_age_ms=600_000,
                )
                for s in (FLOW, RETURN)
            ),
            config_hash="t",
        )
        tl = temp_timelines(
            flow=[(T0, 50.0, P)], ret=[(T0 + 5 * M, 40.0, P)], setpoint=[(T0, 50.0, P)]
        )
        out = cycle_temperature_metrics([ch_cycle_with_phases()], tl, cfg)
        assert [m for m in out if m.name is MetricName.PAIR_MISALIGNED_TIME]
        assert by_name(out, MetricName.BOILER_DELTA_T_STABLE).time_basis_seconds < 18 * 60


class TestPipelineAndScenario:
    def test_scenario_4_dhw_not_reported_as_high_ch_flow(self) -> None:
        directory = next(d for d in scenario_dirs() if d.name == "04-tapwater")
        data = load_build(directory)
        stages = run_stages(data)
        dhw_starts = {c.start for c in stages.cycles if c.mode is Mode.DHW}
        assert dhw_starts
        metrics = cycle_temperature_metrics(stages.cycles, stages.quality.timelines, data.config)
        assert metrics
        assert not {m.window.cycle_start for m in metrics} & dhw_starts
        means = [m.value for m in metrics if m.name is MetricName.FLOW_MEAN_STABLE]
        assert means
        assert max(v for v in means if v is not None) < 65

    def test_run_pipeline_emits_unique_metric_keys(self) -> None:
        directory = next(d for d in scenario_dirs() if d.name == "01-normaal-cv")
        data = load_build(directory)
        result = run_pipeline(
            data.observations,
            data.connection_events,
            data.config,
            data.window,
            data.window.end + data.config.settle_ms,
        )
        names = {m.name for m in result.metrics}
        assert {MetricName.STARTS, MetricName.OBSERVED_TIME, MetricName.FLOW_MEAN_STABLE} <= names
        keys = [
            (m.name, m.mode, m.window.kind, m.window.range.start, m.window.cycle_start)
            for m in result.metrics
        ]
        assert len(keys) == len(set(keys))
