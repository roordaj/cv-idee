"""Tests for rule ``kort-branden`` (#30): unit cases and MVP scenarios 1 and 2."""

from __future__ import annotations

from dataclasses import replace

import pytest

from cvidee.analysis.types import HOUR_MS, MINUTE_MS, BurnerCycle, EndReason, Mode, Role, TimeRange
from cvidee.rules.base import (
    AvailabilityStatus,
    Certainty,
    RecommendationKind,
    RuleContext,
    SpecialPeriod,
    SpecialPeriodKind,
)
from cvidee.rules.registry import default_registry
from cvidee.rules.short_cycling import ShortCyclingParams, ShortCyclingRule
from tests.scenarios.harness import load_build, run_stages, scenario_dirs

from .helpers import DAY_MS, PROFILE, T0, boiler_signals, cycle

RULE = ShortCyclingRule()
PARAMS = ShortCyclingParams()
NOW = T0 + 7 * DAY_MS
PERIOD = TimeRange(NOW - 7 * DAY_MS, NOW)


def ctx(
    cycles: tuple[BurnerCycle, ...], special_periods: tuple[SpecialPeriod, ...] = ()
) -> RuleContext:
    return RuleContext(
        now=NOW,
        period=PERIOD,
        profile=PROFILE,
        signals=boiler_signals(),
        cycles=cycles,
        special_periods=special_periods,
    )


def burst(day: int, count: int, *, hour: int = 6, mode: Mode = Mode.CH) -> tuple[BurnerCycle, ...]:
    start = T0 + day * DAY_MS + hour * HOUR_MS
    return tuple(
        replace(cycle(start + i * 6 * MINUTE_MS, 2.0, mode), pause_before_ms=4 * MINUTE_MS)
        for i in range(count)
    )


def test_registered_with_identity() -> None:
    registry = default_registry()
    assert "kort-branden" in registry
    assert registry.get("kort-branden").version == "1.1.0"
    schema = registry.params_json_schema("kort-branden")
    assert schema["properties"]["short_cycle_min"]["x-unit"] == "min"


def test_unclassified_short_burns_emit_measurement_only_outcome() -> None:
    cycles = tuple(
        replace(c, mode=Mode.UNKNOWN, end_reason=EndReason.UNDETERMINED) for c in burst(1, 5)
    )
    flame_only = tuple(s for s in boiler_signals() if s.signal.role is Role.FLAME)
    context = replace(ctx(cycles), signals=flame_only)
    outcome = default_registry().evaluate("kort-branden", context, PARAMS)
    assert outcome.availability.status is AvailabilityStatus.UNAVAILABLE
    assert not outcome.evaluated
    (finding,) = outcome.candidates
    assert finding.certainty is Certainty.INSUFFICIENT_EVIDENCE
    assert finding.recommendation is not None
    assert finding.recommendation.kind is RecommendationKind.MEASUREMENT
    assert finding.hypotheses == ()
    assert finding.evidence.pattern_cycles == 5
    assert {signal.role for signal in finding.evidence.missing_signals} >= {
        Role.OPERATING_MODE,
        Role.HEAT_DEMAND,
        Role.RETURN_TEMPERATURE,
        Role.MODULATION,
        Role.ROOM_TEMPERATURE,
    }


def test_unclassified_long_burns_stay_silent() -> None:
    cycles = tuple(
        replace(
            cycle(T0 + DAY_MS + i * HOUR_MS, 5.0),
            mode=Mode.UNKNOWN,
            end_reason=EndReason.UNDETERMINED,
        )
        for i in range(5)
    )
    context = replace(
        ctx(cycles), signals=tuple(s for s in boiler_signals() if s.signal.role is Role.FLAME)
    )
    outcome = default_registry().evaluate("kort-branden", context, PARAMS)
    assert outcome.availability.status is AvailabilityStatus.UNAVAILABLE
    assert not outcome.candidates


def test_single_short_cycle_is_no_finding() -> None:
    assert RULE.evaluate(ctx(burst(1, 1)), PARAMS) == ()


def test_below_minimum_count_is_no_finding() -> None:
    assert RULE.evaluate(ctx(burst(1, 3)), PARAMS) == ()


def test_dhw_cycles_do_not_count() -> None:
    assert RULE.evaluate(ctx(burst(1, 10, mode=Mode.DHW)), PARAMS) == ()


def test_excluded_special_period_does_not_count() -> None:
    cycles = burst(1, 10)
    sp = SpecialPeriod(TimeRange(T0 + DAY_MS, T0 + 2 * DAY_MS), SpecialPeriodKind.MAINTENANCE)
    assert RULE.evaluate(ctx(cycles, (sp,)), PARAMS) == ()


def test_long_cycles_do_not_count() -> None:
    cycles = tuple(cycle(T0 + DAY_MS + i * HOUR_MS, 20.0) for i in range(10))
    assert RULE.evaluate(ctx(cycles), PARAMS) == ()


def test_pattern_on_one_day_is_preliminary_with_check_advice() -> None:
    (finding,) = RULE.evaluate(ctx(burst(1, 70)), PARAMS)
    assert finding.certainty is Certainty.PRELIMINARY
    assert finding.recommendation is not None
    assert finding.recommendation.kind is RecommendationKind.CHECK
    assert len(finding.hypotheses) == 3


def test_too_little_observation_is_insufficient_with_measurement() -> None:
    (finding,) = RULE.evaluate(ctx(burst(1, 4)), PARAMS)
    assert finding.certainty is Certainty.INSUFFICIENT_EVIDENCE
    assert finding.recommendation is not None
    assert finding.recommendation.kind is RecommendationKind.MEASUREMENT
    assert finding.hypotheses == ()


def test_repeated_pattern_lists_hypotheses_without_setting_change() -> None:
    cycles = burst(1, 20) + burst(2, 20) + burst(3, 20)
    (finding,) = RULE.evaluate(ctx(cycles), PARAMS)
    assert finding.certainty.rank >= Certainty.MODERATE.rank
    assert finding.recommendation is not None
    assert finding.recommendation.kind is RecommendationKind.CHECK
    assert finding.recommendation.rollback_criterion is None
    names = [h.name for h in finding.hypotheses]
    assert names == [
        "Te weinig open afgifte",
        "Beperkte doorstroming ketelcircuit",
        "Minimumvermogen boven actuele warmtevraag",
    ]
    assert all(h.missing and h.distinguishing_measurement for h in finding.hypotheses)


def test_missing_optional_signals_lower_certainty_and_are_listed() -> None:
    cycles = burst(1, 20) + burst(2, 20) + burst(3, 20)
    (finding,) = RULE.evaluate(ctx(cycles), PARAMS)
    assert finding.evidence.missing_signals  # pump, valves, manifold: not mapped in the fixture


@pytest.mark.parametrize("name", ["01-normaal-cv", "02-kort-branden"])
def test_scenarios(name: str) -> None:
    directory = next(d for d in scenario_dirs() if d.name == name)
    data = load_build(directory)
    stages = run_stages(data)
    period = TimeRange(data.start_ms, data.end_ms)
    context = RuleContext(
        now=data.end_ms,
        period=period,
        profile=PROFILE,
        signals=boiler_signals(),
        cycles=stages.cycles,
        mode_segments=stages.modes,
    )
    findings = RULE.evaluate(context, ShortCyclingParams(window_days=7))
    if name == "01-normaal-cv":
        assert findings == ()
        return
    (finding,) = findings
    assert finding.scope_key == "boiler:ch"
    assert finding.certainty.rank >= Certainty.MODERATE.rank
    assert len(finding.hypotheses) == 3
    assert finding.recommendation is not None
    assert finding.recommendation.kind is RecommendationKind.CHECK
    assert finding.evidence.excluded_cycles >= 1  # DHW draws are left out, not counted
    assert finding.evidence.pattern_cycles is not None
    assert finding.evidence.pattern_cycles > 100
