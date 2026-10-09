"""Detection rules #31-#33: evidence, exclusions and MVP scenarios."""

from dataclasses import replace
from typing import Any

import pytest

from cvidee.analysis.pipeline import run_pipeline
from cvidee.analysis.types import (
    HOUR_MS,
    BurnerCycle,
    ConnectionSource,
    EndReason,
    MetricName,
    MetricValue,
    MetricWindow,
    MetricWindowKind,
    Mode,
    QualityEvent,
    QualityEventKind,
    Role,
    TimeRange,
)
from cvidee.rules.base import (
    Certainty,
    RuleContext,
    SignalStatus,
    SpecialPeriod,
    SpecialPeriodKind,
    StaticTimelines,
    signal_ref,
)
from cvidee.rules.data_quality import DataLossRule, StaleSensorRule
from cvidee.rules.dhw import DhwExcludedRule
from cvidee.rules.hydraulic import HydraulicParams, HydraulicRule
from cvidee.rules.patterns import WindowParams
from cvidee.rules.registry import default_registry
from cvidee.rules.stop_during_demand import StopDuringDemandRule, StopParams
from cvidee.rules.temperature import TemperatureParams, TemperatureRule
from tests.rules.helpers import PROFILE, T0, boiler_signals, cycle, status
from tests.scenarios.harness import load_build, scenario_dirs

SPAN = TimeRange(T0, T0 + 8 * HOUR_MS)


def context(**changes: Any) -> RuleContext:
    base = RuleContext(now=SPAN.end, period=SPAN, profile=PROFILE, signals=boiler_signals())
    return replace(base, **changes)


def metric(c: BurnerCycle, name: MetricName, value: float) -> MetricValue:
    assert c.end is not None
    return MetricValue(
        name,
        MetricWindow(MetricWindowKind.CYCLE, TimeRange(c.start, c.end), c.start),
        value,
        "K",
        60,
        1,
        mode=Mode.CH,
    )


def test_stop_pattern_observation_is_separate_from_interpretation() -> None:
    cycles = tuple(cycle(T0 + i * HOUR_MS, 20) for i in range(4))
    metrics = tuple(metric(c, MetricName.OVERSHOOT_AT_STOP, 5) for c in cycles)
    (finding,) = StopDuringDemandRule().evaluate(
        context(cycles=cycles, metrics=metrics), StopParams(min_observation_h=1)
    )
    assert "In 4 van 4" in finding.observation
    assert "4 van 4 beoordeelbare stops" in finding.observation
    assert "bewijst geen oorzaak" in finding.interpretation
    assert finding.supports == ("kort-branden",)
    assert finding.recommendation is not None
    assert finding.recommendation.kind.value == "measurement"


@pytest.mark.parametrize(
    ("mode", "reason"), [(Mode.CH, EndReason.DEMAND_ENDED), (Mode.DHW, EndReason.DHW_ENDED)]
)
def test_normal_demand_end_and_dhw_do_not_trigger_stop_rule(mode: Mode, reason: EndReason) -> None:
    cycles = tuple(replace(cycle(T0 + i * HOUR_MS, 2, mode), end_reason=reason) for i in range(8))
    assert StopDuringDemandRule().evaluate(context(cycles=cycles), StopParams()) == ()


def test_incomplete_and_special_period_cycles_do_not_trigger_patterns() -> None:
    cycles = tuple(
        replace(cycle(T0 + i * HOUR_MS), complete=False, end_reason=EndReason.DATA_GAP)
        for i in range(8)
    )
    assert StopDuringDemandRule().evaluate(context(cycles=cycles), StopParams()) == ()
    excluded = SpecialPeriod(SPAN, SpecialPeriodKind.COMMISSIONING)
    cycles = tuple(cycle(T0 + i * HOUR_MS) for i in range(8))
    ctx = context(cycles=cycles, special_periods=(excluded,))
    assert StopDuringDemandRule().evaluate(ctx, StopParams()) == ()
    assert HydraulicRule().evaluate(ctx, HydraulicParams()) == ()


def test_temperature_requires_aligned_metrics_not_cycle_maxima() -> None:
    cycles = tuple(cycle(T0 + i * HOUR_MS, 30) for i in range(4))
    assert TemperatureRule().evaluate(context(cycles=cycles), TemperatureParams()) == ()
    metrics = tuple(metric(c, MetricName.OVERSHOOT, 4) for c in cycles)
    rule = TemperatureRule()
    (finding,) = rule.evaluate(
        context(cycles=cycles, metrics=metrics), TemperatureParams(min_observation_h=1)
    )
    assert "In 4 cv-cycli" in finding.observation
    assert (
        rule.evaluate(
            context(cycles=cycles, metrics=metrics), TemperatureParams(overshoot_margin_c=5)
        )
        == ()
    )
    assert finding.supports == ("kort-branden", "stop-tijdens-vraag")


def test_inverted_stable_delta_t_is_observation_not_loop_advice() -> None:
    cycles = tuple(cycle(T0 + i * HOUR_MS, 30) for i in range(4))
    metrics = tuple(metric(c, MetricName.BOILER_DELTA_T_STABLE, -1) for c in cycles)
    (finding,) = TemperatureRule().evaluate(
        context(cycles=cycles, metrics=metrics), TemperatureParams()
    )
    assert "retour" in finding.observation
    assert finding.recommendation is not None
    assert "instelling" not in finding.recommendation.action


def test_data_gap_fragments_merge_and_include_cycle_ending_at_gap_start() -> None:
    gap_start = T0 + HOUR_MS
    events = (
        QualityEvent(
            QualityEventKind.CONNECTION_LOST,
            None,
            gap_start,
            gap_start + HOUR_MS,
            source=ConnectionSource.WS,
        ),
        QualityEvent(
            QualityEventKind.CONNECTION_LOST,
            None,
            gap_start + HOUR_MS,
            gap_start + 2 * HOUR_MS,
            source=ConnectionSource.WS,
        ),
    )
    incomplete = replace(cycle(T0, 60), complete=False, end_reason=EndReason.DATA_GAP)
    (finding,) = DataLossRule().evaluate(
        context(cycles=(incomplete,), quality_events=events), WindowParams()
    )
    assert finding.evidence.unknown_ms == 2 * HOUR_MS
    assert finding.evidence.relevant_cycles == 1
    assert finding.certainty is Certainty.HIGH_MEASURED
    assert finding.recommendation is None
    assert "onbekend, niet als uit-tijd" in finding.interpretation


def test_inferred_gateway_loss_is_not_claimed_as_direct_measurement() -> None:
    event = QualityEvent(
        QualityEventKind.CONNECTION_LOST,
        None,
        T0,
        T0 + HOUR_MS,
        source=ConnectionSource.CAN_GATEWAY,
        detail="derived",
    )
    (finding,) = DataLossRule().evaluate(context(quality_events=(event,)), WindowParams())
    assert finding.certainty is Certainty.MODERATE
    assert finding.signals == ()
    assert "niet per entiteit vastgesteld" in finding.observation


def test_stale_sensor_is_scoped_and_does_not_optimize() -> None:
    ref = signal_ref(Role.ROOM_TEMPERATURE, "slaapkamer")
    event = QualityEvent(QualityEventKind.STALE, ref, T0, None)
    (finding,) = StaleSensorRule().evaluate(context(quality_events=(event,)), WindowParams())
    assert finding.scope_key == str(ref)
    assert finding.certainty is Certainty.HIGH_MEASURED
    assert finding.recommendation is None
    assert finding.evidence.unknown_ms == SPAN.duration_ms


def test_explicit_unavailable_does_not_invent_connection_loss() -> None:
    ref = signal_ref(Role.FLAME)
    event = QualityEvent(QualityEventKind.UNAVAILABLE, ref, T0, T0 + HOUR_MS)
    (finding,) = DataLossRule().evaluate(context(quality_events=(event,)), WindowParams())
    assert finding.scope_key == f"signal:{ref}"
    assert finding.recommendation is None
    assert "niet vastgesteld" in finding.interpretation


def test_low_aligned_coverage_keeps_temperature_conclusion_insufficient() -> None:
    cycles = tuple(cycle(T0 + i * HOUR_MS, 30) for i in range(4))
    metrics = tuple(replace(metric(c, MetricName.OVERSHOOT, 4), coverage=0.1) for c in cycles)
    (finding,) = TemperatureRule().evaluate(
        context(cycles=cycles, metrics=metrics), TemperatureParams(min_observation_h=1)
    )
    assert finding.certainty is Certainty.INSUFFICIENT_EVIDENCE
    assert finding.interpretation == ""


def test_dhw_is_visible_but_never_a_temperature_pattern() -> None:
    cycles = tuple(cycle(T0 + i * HOUR_MS, 10, Mode.DHW) for i in range(4))
    (finding,) = DhwExcludedRule().evaluate(context(cycles=cycles), WindowParams())
    assert finding.evidence.excluded_cycles == 4
    assert finding.severity.value == "info"
    assert finding.recommendation is None
    metrics = tuple(metric(c, MetricName.OVERSHOOT, 20) for c in cycles)
    assert (
        TemperatureRule().evaluate(context(cycles=cycles, metrics=metrics), TemperatureParams())
        == ()
    )


def test_mixing_manifold_without_local_measurements_gets_measurement_only() -> None:
    (finding,) = HydraulicRule().evaluate(context(), HydraulicParams())
    assert finding.certainty is Certainty.INSUFFICIENT_EVIDENCE
    assert finding.scope_key == "circuit:boven:ch"
    assert finding.recommendation is not None
    assert finding.recommendation.kind.value == "measurement"
    assert "verdeleraanvoer" in finding.recommendation.action
    assert "lussen" not in finding.recommendation.action
    assert (
        HydraulicRule().evaluate(
            context(profile=replace(PROFILE, circuits=(PROFILE.circuits[0],))), HydraulicParams()
        )
        == ()
    )


def test_local_temperatures_remove_missing_data_finding_but_boiler_data_does_not() -> None:
    signals = (
        *boiler_signals(),
        status(Role.MANIFOLD_FLOW_TEMPERATURE, "boven"),
        status(Role.MANIFOLD_RETURN_TEMPERATURE, "boven"),
    )
    assert HydraulicRule().evaluate(context(signals=signals), HydraulicParams()) == ()
    stale = (
        *boiler_signals(),
        status(Role.MANIFOLD_FLOW_TEMPERATURE, "boven", stale=True),
        status(Role.MANIFOLD_RETURN_TEMPERATURE, "boven"),
    )
    assert len(HydraulicRule().evaluate(context(signals=stale), HydraulicParams())) == 1


@pytest.mark.parametrize(
    "name",
    [
        "03-stop-na-einde-vraag",
        "04-tapwater",
        "05-can-uitval",
        "06-mengverdeler-zonder-verdelerdata",
        "09-opstookprotocol",
    ],
)
def test_mvp_scenarios(name: str) -> None:
    directory = next(d for d in scenario_dirs() if d.name == name)
    data = load_build(directory)
    result = run_pipeline(
        data.observations,
        data.connection_events,
        data.config,
        data.window,
        data.end_ms + data.config.settle_ms,
    )
    period = TimeRange(data.start_ms, data.end_ms)
    statuses = tuple(
        SignalStatus(t.signal, t.coverage(period), resolution_ms=4000) for t in result.timelines
    )
    marked = tuple(
        SpecialPeriod(
            TimeRange(start, end),
            SpecialPeriodKind("commissioning" if kind == "opstookprotocol" else kind),
        )
        for start, end, kind in data.special_periods
    )
    ctx = RuleContext(
        now=data.end_ms,
        period=period,
        profile=PROFILE,
        signals=statuses,
        cycles=result.cycles,
        mode_segments=result.mode_segments,
        metrics=result.metrics,
        quality_events=result.quality_events,
        special_periods=marked,
        timelines=StaticTimelines(result.timelines),
    )
    registry = default_registry()
    findings = {
        rule.id: registry.evaluate(rule.id, ctx, registry.default_params(rule.id)).candidates
        for rule in registry
    }
    if name.startswith("03"):
        assert findings["kort-branden"] == ()
        assert findings["stop-tijdens-vraag"] == ()
    if name.startswith("04"):
        assert findings["tapwater-uitgesloten"]
        assert findings["kort-branden"] == ()
    if name.startswith("05"):
        assert findings["dataverlies"]
    if name.startswith("06"):
        advice = findings["hydraulisch"][0].recommendation
        assert advice is not None
        assert advice.kind.value == "measurement"
    if name.startswith("09"):
        assert findings["kort-branden"] == ()
        protocol = replace(ctx, period=marked[0].range, now=marked[0].range.end)
        assert HydraulicRule().evaluate(protocol, HydraulicParams()) == ()
