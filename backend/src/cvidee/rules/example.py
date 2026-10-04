"""Example rule ``voorbeeld-cycli`` (ADR-004): shows the contract end to end.

Not registered in :func:`cvidee.rules.registry.default_registry`; it exists as a template
for real rules (#30-#33) and is exercised by the tests. It reports how many relevant
(CH, not excluded) cycles were observed and derives its certainty from the criteria
template. With too little data it proposes an additional measurement (FR-28).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Self

from pydantic import model_validator

from cvidee.analysis.types import HOUR_MS, BurnerCycle, DurationMs, Mode, Role
from cvidee.rules.base import (
    BaseRule,
    Category,
    Certainty,
    CertaintyCriteria,
    CycleRef,
    EvidenceSummary,
    FindingCandidate,
    ParamGroup,
    PeriodRef,
    RecommendationDraft,
    RecommendationKind,
    Relevance,
    RuleContext,
    RuleParams,
    Severity,
    Thresholds,
    param,
    signal_ref,
)
from cvidee.rules.certainty import derive_certainty

DAY_MS: DurationMs = 24 * HOUR_MS


class ExampleCycleParams(RuleParams):
    min_cycles: int = param(
        4,
        title="Minimum aantal cycli",
        description="Zoveel cv-cycli zijn nodig voordat de voorbeeldregel iets concludeert.",
        unit="cycli",
        step=1,
        ge=1,
        le=50,
        group=ParamGroup.SHORT_CYCLES,
    )
    window_days: int = param(
        7,
        title="Beoordelingsperiode",
        description="Aantal dagen terug dat de voorbeeldregel bekijkt.",
        unit="dagen",
        step=1,
        ge=3,
        le=28,
        group=ParamGroup.SHORT_CYCLES,
    )
    structural_days: int = param(
        2,
        title="Herhaling over dagen",
        description="Op minstens zoveel dagen moeten cycli voorkomen; anders is de uitkomst "
        "voorlopig.",
        unit="dagen",
        step=1,
        ge=1,
        le=14,
        group=ParamGroup.SHORT_CYCLES,
    )

    @model_validator(mode="after")
    def _repetition_within_window(self) -> Self:
        if self.structural_days > self.window_days:
            raise ValueError("structural_days must be <= window_days")
        return self


class ExampleCycleRule(BaseRule[ExampleCycleParams]):
    id = "voorbeeld-cycli"
    version = "0.1.0"
    category = Category.CYCLES
    required_signals = frozenset({Role.FLAME})
    optional_signals = frozenset({Role.OPERATING_MODE, Role.HEAT_DEMAND})
    applies_in_modes = frozenset({Mode.CH})
    params_schema = ExampleCycleParams

    def history_ms(self, params: RuleParams) -> DurationMs:
        return self.typed(params).window_days * DAY_MS

    def certainty_criteria(self, params: RuleParams) -> CertaintyCriteria:
        p = self.typed(params)
        return CertaintyCriteria(
            minimum=Thresholds(coverage=0.8, relevant_cycles=p.min_cycles),
            structural_repetition_days=p.structural_days,
            repetition_window_days=p.window_days,
            reasonable=Thresholds(coverage=0.9, relevant_cycles=2 * p.min_cycles),
            high=Thresholds(coverage=0.95, relevant_cycles=5 * p.min_cycles, repetition_days=5),
            max_certainty=Certainty.HIGH,
        )

    def _evaluate(self, ctx: RuleContext, params: ExampleCycleParams) -> Sequence[FindingCandidate]:
        period = ctx.period
        relevant = ctx.relevant_cycles(frozenset({Mode.CH}), period)
        excluded = ctx.excluded_cycles(frozenset({Mode.CH}), period)
        days = ctx.local_days(period)[-params.window_days :]
        days_with_cycles = sum(1 for d in days if any(d.contains(c.start) for c in relevant))

        flame = signal_ref(Role.FLAME)
        flame_status = ctx.signal_status(flame)
        coverage = flame_status.coverage if flame_status is not None else 0.0
        optional = [signal_ref(role) for role in sorted(self.optional_signals)]
        evidence = EvidenceSummary(
            coverage=coverage,
            unknown_ms=round(period.duration_ms * (1.0 - coverage)),
            excluded_ms=sum(r.duration_ms for r in ctx.excluded_ranges(period)),
            excluded_cycles=len(excluded),
            relevant_cycles=len(relevant),
            pattern_cycles=len(relevant),
            repetition_days=days_with_cycles,
            repetition_window_days=len(days),
            missing_signals=ctx.unmapped(optional),
        )
        assessment = derive_certainty(evidence, self.certainty_criteria(params))
        insufficient = assessment.certainty is Certainty.INSUFFICIENT_EVIDENCE
        return (
            FindingCandidate(
                scope_key="boiler:ch",
                category=self.category,
                title="Voorbeeld: waargenomen cv-cycli",
                severity=Severity.INFO,
                certainty=assessment.certainty,
                relevance=(Relevance.OPERATIONAL_STABILITY,),
                observation=f"In de beoordelingsperiode zijn {len(relevant)} cv-cycli "
                f"waargenomen op {days_with_cycles} van {len(days)} dagen.",
                period=period,
                signals=(flame,),
                evidence=evidence,
                interpretation="" if insufficient else "Ter illustratie; geen diagnose.",
                recommendation=_more_data(params) if insufficient else None,
                no_advice_reason="" if insufficient else "Voorbeeldregel: geen advies.",
                refs=(PeriodRef(period), *(_cycle_refs(relevant))),
            ),
        )


def _cycle_refs(cycles: Sequence[BurnerCycle]) -> tuple[CycleRef, ...]:
    return tuple(CycleRef(c.start) for c in cycles)


def _more_data(params: ExampleCycleParams) -> RecommendationDraft:
    return RecommendationDraft(
        kind=RecommendationKind.MEASUREMENT,
        action="Verzamel meer gegevens met cv-bedrijf voordat er iets wordt geconcludeerd.",
        reason=f"Er zijn minder dan {params.min_cycles} cv-cycli met voldoende gegevens.",
        expected_effect="Geen direct effect. Maakt een beoordeling mogelijk.",
        comfort_impact="Geen invloed.",
        conditions="Geen gemarkeerde periode; vlamstatus gekoppeld.",
        evaluation=f"Opnieuw beoordelen na {params.window_days} dagen.",
        success_criterion="Voldoende cycli voor een beoordeling.",
        evaluation_days=params.window_days,
    )
