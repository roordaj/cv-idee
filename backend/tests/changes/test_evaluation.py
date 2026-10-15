"""Before/after verdicts use explicit comfort targets and reject false attribution."""

from dataclasses import replace

import pytest

from cvidee.analysis.change_evaluation import (
    ComparisonPolicy,
    EvaluationFact,
    evaluate_change,
    period_metrics,
)
from cvidee.analysis.types import TimeRange
from cvidee.rules.base import Certainty, InstallationFacts, RuleContext
from cvidee.rules.before_after import BeforeAfterParams, BeforeAfterRule
from tests.scenarios.harness import SCENARIO_ROOT, load_build, run_stages


@pytest.fixture(scope="module")
def scenarios() -> tuple[EvaluationFact, EvaluationFact]:
    results = []
    policy = ComparisonPolicy(days=3)
    for name in ("07-aanvoerwijziging-comfort", "08-gelijktijdige-wijzigingen"):
        data = load_build(SCENARIO_ROOT / name)
        run = run_stages(data)
        at = data.at(72)
        before, after = TimeRange(data.start_ms, at), TimeRange(at, data.end_ms)
        old = period_metrics(before, run.quality.timelines, run.cycles, run.modes, (), policy)
        new = period_metrics(after, run.quality.timelines, run.cycles, run.modes, (), policy)
        results.append(
            evaluate_change(
                "W-01",
                before,
                after,
                old,
                new,
                data.end_ms,
                policy,
                () if name.startswith("07") else ("W-02",),
            )
        )
    return results[0], results[1]


def test_better_cycles_with_worse_comfort_is_trade_off(
    scenarios: tuple[EvaluationFact, EvaluationFact],
) -> None:
    fact, _ = scenarios
    assert fact.verdict == "trade_off"
    assert fact.rollback
    assert fact.before.starts_per_hour is not None
    assert fact.after.starts_per_hour is not None
    assert fact.after.starts_per_hour < fact.before.starts_per_hour
    cold = dict(fact.after.cold_hours)["slaapkamer"]
    assert cold is not None
    assert cold > 4
    assert fact.weather == "yes"
    assert fact.setpoints == "yes"
    rule = BeforeAfterRule()
    ctx = RuleContext(
        now=fact.observation.end,
        period=TimeRange(fact.reference.start, fact.observation.end),
        profile=InstallationFacts(),
        change_evaluations=(fact,),
    )
    (candidate,) = rule.evaluate(ctx, BeforeAfterParams(comparison_days=3))
    assert candidate.certainty is Certainty.REASONABLE
    assert candidate.severity.value == "medium"


def test_overlap_and_weather_prevent_single_parameter_credit(
    scenarios: tuple[EvaluationFact, EvaluationFact],
) -> None:
    _, fact = scenarios
    assert fact.verdict == "not_attributable"
    assert fact.weather == "no"
    assert fact.overlap_ids == ("W-02",)

    ctx = RuleContext(
        now=fact.observation.end,
        period=TimeRange(fact.reference.start, fact.observation.end),
        profile=InstallationFacts(),
        change_evaluations=(fact, replace(fact, change_id="W-02", overlap_ids=("W-01",))),
    )
    (candidate,) = BeforeAfterRule().evaluate(ctx, BeforeAfterParams(comparison_days=3))
    assert candidate.certainty is Certainty.PRELIMINARY
    assert candidate.severity.value == "info"
    assert "W-02" in candidate.observation


def test_unknown_comfort_or_data_gap_never_becomes_improvement(
    scenarios: tuple[EvaluationFact, EvaluationFact],
) -> None:
    fact, _ = scenarios
    policy = ComparisonPolicy(days=3)
    for after in (
        replace(fact.after, coverage=0.2),
        replace(fact.after, cold_hours=(), room_coverage=(), setpoints=()),
    ):
        result = evaluate_change(
            fact.change_id,
            fact.reference,
            fact.observation,
            fact.before,
            after,
            fact.observation.end,
            policy,
        )
        assert result.verdict == "insufficient_evidence"
        assert not result.rollback
    pending = evaluate_change(
        fact.change_id,
        fact.reference,
        fact.observation,
        fact.before,
        fact.after,
        fact.observation.end - 1,
        policy,
    )
    assert pending.verdict == "pending"
    assert not pending.rollback


def test_per_advice_rollback_limit_is_respected(
    scenarios: tuple[EvaluationFact, EvaluationFact],
) -> None:
    fact, _ = scenarios
    result = evaluate_change(
        fact.change_id,
        fact.reference,
        fact.observation,
        fact.before,
        fact.after,
        fact.observation.end,
        ComparisonPolicy(days=3),
        rollback_room="slaapkamer",
        rollback_limit=168,
    )
    assert result.verdict == "trade_off"
    assert not result.rollback


def test_schedule_change_with_same_average_is_not_treated_as_comparable(
    scenarios: tuple[EvaluationFact, EvaluationFact],
) -> None:
    fact, _ = scenarios
    old_profile = dict(fact.before.setpoint_profile)
    new_profile = dict(fact.after.setpoint_profile)
    old_levels = dict(fact.before.setpoint_values)
    new_levels = dict(fact.after.setpoint_values)
    old_levels["woonkamer"] = new_levels["woonkamer"] = (20.0, 21.0)
    old_profile["woonkamer"] = ((0, 20.0), (1, 21.0))
    new_profile["woonkamer"] = ((0, 21.0), (1, 20.0))
    before = replace(
        fact.before,
        setpoint_values=tuple(old_levels.items()),
        setpoint_profile=tuple(old_profile.items()),
    )
    after = replace(
        fact.after,
        setpoint_values=tuple(new_levels.items()),
        setpoint_profile=tuple(new_profile.items()),
    )
    result = evaluate_change(
        fact.change_id,
        fact.reference,
        fact.observation,
        before,
        after,
        fact.observation.end,
        ComparisonPolicy(days=3),
    )
    assert result.setpoints == "no"
    assert result.verdict == "not_attributable"


def test_unknown_or_coarse_flame_resolution_blocks_an_effect_verdict(
    scenarios: tuple[EvaluationFact, EvaluationFact],
) -> None:
    fact, _ = scenarios
    for resolution in (None, 200_000):
        result = evaluate_change(
            fact.change_id,
            fact.reference,
            fact.observation,
            fact.before,
            replace(fact.after, flame_resolution_ms=resolution),
            fact.observation.end,
            ComparisonPolicy(days=3),
        )
        assert result.verdict == "insufficient_evidence"
        assert not result.rollback


def test_improvement_requires_preserved_comfort_and_exclusions_stay_explicit(
    scenarios: tuple[EvaluationFact, EvaluationFact],
) -> None:
    fact, _ = scenarios
    after = replace(fact.after, cold_hours=fact.before.cold_hours)
    result = evaluate_change(
        fact.change_id,
        fact.reference,
        fact.observation,
        fact.before,
        after,
        fact.observation.end,
        ComparisonPolicy(days=3),
    )
    assert result.verdict == "improved"
    assert not result.rollback
    excluded = period_metrics(
        fact.reference, (), (), (), (fact.reference,), ComparisonPolicy(days=3)
    )
    assert excluded.excluded_ms == fact.reference.duration_ms
    assert excluded.coverage == 0
    assert excluded.observed_hours == 0
    assert excluded.starts_per_hour is None
