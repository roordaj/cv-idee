"""Hydraulic analysis limits must not be confused with executable data warnings."""

from dataclasses import replace

import pytest

from cvidee.analysis.types import Role, Scope, ScopeKind, SignalRef, TimeRange
from cvidee.rules.availability import assess, assess_analyses, rule_requirement
from cvidee.rules.base import (
    AnalysisId,
    AvailabilityStatus,
    Certainty,
    CircuitFacts,
    CircuitKind,
    IssueKind,
    RuleContext,
    Severity,
    SignalStatus,
)
from cvidee.rules.hydraulic import HydraulicParams, HydraulicRule
from tests.rules.helpers import PROFILE, T0, boiler_signals, status


def hydraulic(signals: tuple[SignalStatus, ...]) -> AvailabilityStatus:
    return next(
        item.availability.status
        for item in assess_analyses(signals, PROFILE)
        if item.analysis is AnalysisId.HYDRAULIC
    )


def local_flow(circuit: str, *, coverage: float = 0.97, stale: bool = False) -> SignalStatus:
    return SignalStatus(
        SignalRef(Role.FLOW_RATE, Scope(ScopeKind.CIRCUIT, circuit)), coverage, stale
    )


def test_measurement_warning_runs_while_hydraulic_analysis_is_limited() -> None:
    signals = boiler_signals()
    rule = HydraulicRule()
    params = HydraulicParams()
    assert (
        assess(rule_requirement(rule, params), signals, PROFILE).status
        is AvailabilityStatus.AVAILABLE
    )
    assert hydraulic(signals) is AvailabilityStatus.LIMITED
    (finding,) = rule.evaluate(
        RuleContext(
            now=T0 + 1000, period=TimeRange(T0, T0 + 1000), profile=PROFILE, signals=signals
        ),
        params,
    )
    assert finding.severity is Severity.INFO
    assert finding.certainty is Certainty.INSUFFICIENT_EVIDENCE
    assert finding.recommendation is not None
    assert finding.recommendation.kind.value == "measurement"


@pytest.mark.parametrize("missing", [Role.FLOW_TEMPERATURE, Role.RETURN_TEMPERATURE])
def test_missing_boiler_data_still_makes_analysis_unavailable(missing: Role) -> None:
    signals = (*boiler_signals(without=(missing,)), local_flow("boven"))
    (result,) = [
        item.availability
        for item in assess_analyses(signals, PROFILE)
        if item.analysis is AnalysisId.HYDRAULIC
    ]
    assert result.status is AvailabilityStatus.UNAVAILABLE
    assert any(issue.role is missing and issue.required for issue in result.issues)


def test_boiler_flow_or_other_circuit_cannot_replace_local_measurements() -> None:
    signals = (*boiler_signals(), status(Role.PUMP_STATE))
    assert hydraulic((*signals, status(Role.FLOW_RATE))) is AvailabilityStatus.LIMITED
    assert hydraulic((*signals, local_flow("beneden"))) is AvailabilityStatus.LIMITED
    assert hydraulic((*signals, local_flow("boven"))) is AvailabilityStatus.AVAILABLE


@pytest.mark.parametrize(
    "flow",
    [
        local_flow("boven", coverage=0),
        local_flow("boven", coverage=0.5),
        local_flow("boven", stale=True),
    ],
)
def test_unusable_local_flow_cannot_remove_measurement_warning(flow: SignalStatus) -> None:
    signals = (*boiler_signals(), status(Role.PUMP_STATE), flow)
    assert hydraulic(signals) is AvailabilityStatus.LIMITED
    (finding,) = HydraulicRule().evaluate(
        RuleContext(
            now=T0 + 1000, period=TimeRange(T0, T0 + 1000), profile=PROFILE, signals=signals
        ),
        HydraulicParams(),
    )
    assert finding.severity is Severity.INFO


def test_each_mixing_manifold_needs_local_evidence() -> None:
    second = CircuitFacts("annex", CircuitKind.MIXING_MANIFOLD, manifold="annex")
    profile = replace(PROFILE, circuits=(*PROFILE.circuits, second))
    signals = (*boiler_signals(), status(Role.PUMP_STATE), local_flow("boven"))
    (limited,) = [
        item.availability
        for item in assess_analyses(signals, profile)
        if item.analysis is AnalysisId.HYDRAULIC
    ]
    assert limited.status is AvailabilityStatus.LIMITED
    assert any(
        issue.role is Role.MANIFOLD_FLOW_TEMPERATURE
        and issue.scope_key == "annex"
        and issue.kind is IssueKind.NOT_MAPPED
        and not issue.required
        for issue in limited.issues
    )
    (available,) = [
        item.availability
        for item in assess_analyses((*signals, local_flow("annex")), profile)
        if item.analysis is AnalysisId.HYDRAULIC
    ]
    assert available.status is AvailabilityStatus.AVAILABLE


def test_each_manifold_can_use_a_different_valid_local_alternative() -> None:
    profile = replace(
        PROFILE,
        circuits=(
            *PROFILE.circuits,
            CircuitFacts("annex", CircuitKind.MIXING_MANIFOLD, manifold="annex"),
        ),
    )
    signals = (
        *boiler_signals(),
        status(Role.PUMP_STATE),
        status(Role.MANIFOLD_FLOW_TEMPERATURE, "boven"),
        status(Role.MANIFOLD_RETURN_TEMPERATURE, "boven"),
        local_flow("boven", stale=True),
        local_flow("annex"),
    )
    (result,) = [
        item.availability
        for item in assess_analyses(signals, profile)
        if item.analysis is AnalysisId.HYDRAULIC
    ]
    assert result.status is AvailabilityStatus.AVAILABLE
    assert result.issues == ()
