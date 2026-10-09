"""Explain the exclusion of observed domestic-hot-water cycles from CH conclusions."""

from collections.abc import Sequence

from cvidee.analysis.types import Mode, Role
from cvidee.rules.base import (
    BaseRule,
    Category,
    Certainty,
    CertaintyCriteria,
    CycleRef,
    EvidenceSummary,
    FindingCandidate,
    RuleContext,
    RuleParams,
    Severity,
    Thresholds,
    signal_ref,
)
from cvidee.rules.patterns import DAY_MS, WindowParams, pattern_period


class DhwExcludedRule(BaseRule[WindowParams]):
    id = "tapwater-uitgesloten"
    version = "1.0.0"
    category = Category.OPERATING_CONTEXT
    required_signals = frozenset({Role.FLAME, Role.OPERATING_MODE})
    applies_in_modes = frozenset({Mode.DHW})
    params_schema = WindowParams

    def history_ms(self, params: RuleParams) -> int:
        return self.typed(params).window_days * DAY_MS

    def certainty_criteria(self, params: RuleParams) -> CertaintyCriteria:
        return CertaintyCriteria(Thresholds(), max_certainty=Certainty.HIGH)

    def _evaluate(self, ctx: RuleContext, params: WindowParams) -> Sequence[FindingCandidate]:
        cycles = [c for c in ctx.cycles_in() if c.mode is Mode.DHW]
        if not cycles:
            return ()
        coverage = min(
            (s.coverage for s in ctx.signals if s.signal.role in self.required_signals), default=0
        )
        return (
            FindingCandidate(
                scope_key="boiler:dhw",
                category=self.category,
                title="Tapwatercyclus uitgesloten van cv-conclusies",
                severity=Severity.INFO,
                certainty=Certainty.HIGH if coverage >= 0.9 else Certainty.MODERATE,
                relevance=(),
                observation=(
                    f"{len(cycles)} branderperioden zijn als tapwaterbedrijf geclassificeerd."
                ),
                period=pattern_period(cycles),
                signals=tuple(sorted(signal_ref(r) for r in self.required_signals)),
                evidence=EvidenceSummary(
                    coverage=coverage, relevant_cycles=len(cycles), excluded_cycles=len(cycles)
                ),
                interpretation=(
                    "Deze cycli tellen niet mee in korte-cycli-meldingen en worden "
                    "niet gerapporteerd als te hoge cv-aanvoer."
                ),
                no_advice_reason="Geen advies nodig. Ter informatie zichtbaar gehouden.",
                refs=tuple(CycleRef(c.start) for c in cycles),
            ),
        )
