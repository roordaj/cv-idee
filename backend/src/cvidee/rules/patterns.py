"""Shared cycle-pattern evidence and configurable observation windows."""

from collections.abc import Sequence
from typing import Self

from pydantic import model_validator

from cvidee.analysis.types import (
    HOUR_MS,
    BurnerCycle,
    MetricName,
    MetricWindowKind,
    Role,
    TimeRange,
)
from cvidee.rules.base import (
    Certainty,
    CertaintyCriteria,
    EvidenceSummary,
    ParamGroup,
    RecommendationDraft,
    RecommendationKind,
    RuleContext,
    RuleParams,
    Thresholds,
    param,
    signal_ref,
)

DAY_MS = 24 * HOUR_MS


class WindowParams(RuleParams):
    window_days: int = param(
        7,
        title="Beoordelingsperiode",
        description="Aantal dagen in de beoordeling.",
        unit="dagen",
        group=ParamGroup.DATA,
        ge=3,
        le=28,
        step=1,
    )


class PatternParams(WindowParams):
    min_observation_h: float = param(
        6,
        title="Minimale observatieduur",
        description="Uren met bruikbare cv-gegevens voordat een patroon wordt beoordeeld.",
        unit="uur",
        group=ParamGroup.SHORT_CYCLES,
        ge=1,
        le=72,
        step=1,
    )
    structural_days: int = param(
        2,
        title="Herhaling over dagen",
        description="Dagen waarop het patroon moet terugkeren.",
        unit="dagen",
        group=ParamGroup.SHORT_CYCLES,
        ge=1,
        le=14,
        step=1,
    )

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.structural_days > self.window_days:
            raise ValueError("Repetition days must not exceed the observation window")
        return self


def pattern_criteria(params: PatternParams) -> CertaintyCriteria:
    return CertaintyCriteria(
        minimum=Thresholds(coverage=0.8, observed_hours=params.min_observation_h),
        structural_repetition_days=params.structural_days,
        repetition_window_days=params.window_days,
        reasonable=Thresholds(coverage=0.9, relevant_cycles=12, repetition_days=3),
        max_certainty=Certainty.REASONABLE,
    )


def evidence(
    ctx: RuleContext,
    all_cycles: Sequence[BurnerCycle],
    selected: Sequence[BurnerCycle],
    roles: frozenset[Role],
    optional: frozenset[Role],
    params: PatternParams,
) -> EvidenceSummary:
    coverage = min(
        (
            status.coverage if (status := ctx.signal_status(signal_ref(role))) is not None else 0.0
            for role in roles
        ),
        default=0.0,
    )
    days = ctx.local_days(ctx.period)[-params.window_days :]
    missing = tuple(
        sorted(signal_ref(role) for role in optional if not ctx.is_mapped(signal_ref(role)))
    )
    return EvidenceSummary(
        coverage=coverage,
        relevant_cycles=len(all_cycles),
        pattern_cycles=len(selected),
        observed_hours=sum(c.duration_ms + (c.pause_before_ms or 0) for c in all_cycles) / HOUR_MS,
        repetition_days=sum(any(day.contains(c.start) for c in selected) for day in days),
        repetition_window_days=len(days),
        missing_signals=missing,
        unknown_ms=round(ctx.period.duration_ms * (1 - coverage)),
        excluded_ms=sum(r.duration_ms for r in ctx.excluded_ranges()),
    )


def cycle_metric(ctx: RuleContext, cycle: BurnerCycle, name: MetricName) -> float | None:
    return next(
        (
            m.value
            for m in ctx.metrics
            if m.name is name
            and m.window.kind is MetricWindowKind.CYCLE
            and m.window.cycle_start == cycle.start
            and m.time_basis_seconds > 0
        ),
        None,
    )


def pattern_period(cycles: Sequence[BurnerCycle]) -> TimeRange:
    return TimeRange(min(c.start for c in cycles), max(c.end or c.start + 1 for c in cycles))


def measurement(action: str, reason: str) -> RecommendationDraft:
    return RecommendationDraft(
        kind=RecommendationKind.MEASUREMENT,
        action=action,
        reason=reason,
        expected_effect="Maakt een gerichte beoordeling mogelijk; geen direct energie-effect.",
        comfort_impact="Geen invloed.",
        conditions="Bruikbare gegevens buiten gemarkeerde perioden.",
        evaluation="Beoordeel opnieuw na verzamelen van de aanvullende gegevens.",
        success_criterion="De ontbrekende gegevens zijn beschikbaar en bruikbaar.",
    )
