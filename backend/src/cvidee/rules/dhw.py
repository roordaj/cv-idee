"""Explain the exclusion of observed domestic-hot-water cycles from CH conclusions."""

from collections.abc import Sequence

from cvidee.analysis.types import MINUTE_MS, EndReason, Mode, Role
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
from cvidee.rules.patterns import (
    DAY_MS,
    DEFAULT_SHORT_CYCLE_LIMIT_MIN,
    WindowParams,
    pattern_period,
)

MIN_REPEATED_DHW_CYCLES = 10
"""Minimum count for a separate DHW finding; individual cycles stay in the timeline."""
MIN_SHORT_CH_CYCLES_FOR_DHW_CONTEXT = 4
"""Show DHW context at lower counts when short CH cycles could be misread."""


class DhwExcludedRule(BaseRule[WindowParams]):
    id = "tapwater-uitgesloten"
    version = "1.1.0"
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
        short_ch = [
            c
            for c in ctx.cycles_in()
            if c.mode is Mode.CH
            and c.complete
            and c.end_reason is EndReason.STOP_DURING_DEMAND
            and c.duration_ms < round(DEFAULT_SHORT_CYCLE_LIMIT_MIN * MINUTE_MS)
        ]
        if (
            len(cycles) < MIN_REPEATED_DHW_CYCLES
            and len(short_ch) < MIN_SHORT_CH_CYCLES_FOR_DHW_CONTEXT
        ):
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
