"""CH temperature patterns based only on aligned pipeline metrics (FR-15)."""

from collections.abc import Sequence
from dataclasses import replace

from cvidee.analysis.types import MetricName, Role
from cvidee.rules.base import (
    BaseRule,
    Category,
    Certainty,
    CertaintyCriteria,
    CycleRef,
    FindingCandidate,
    ParamGroup,
    Relevance,
    RuleContext,
    RuleParams,
    Severity,
    param,
    signal_ref,
)
from cvidee.rules.certainty import derive_certainty
from cvidee.rules.patterns import (
    DAY_MS,
    PatternParams,
    cycle_metric,
    evidence,
    measurement,
    pattern_criteria,
    pattern_period,
)


class TemperatureParams(PatternParams):
    min_temperature_cycles: int = param(
        4,
        title="Minimum aantal temperatuurafwijkingen",
        description="Minimum aantal cycli met een waargenomen afwijking.",
        unit="cycli",
        group=ParamGroup.SHORT_CYCLES,
        ge=2,
        le=30,
        step=1,
    )
    overshoot_margin_c: float = param(
        0,
        title="Marge voor doorschieten",
        description="Aanvoer boven gewenst plus deze marge; geen universele schadelijkheidsgrens.",
        unit="°C",
        group=ParamGroup.SHORT_CYCLES,
        ge=0,
        le=20,
        step=0.5,
    )


class TemperatureRule(BaseRule[TemperatureParams]):
    id = "temperatuurverloop"
    version = "1.1.0"
    category = Category.TEMPERATURE
    required_signals = frozenset(
        {Role.FLAME, Role.OPERATING_MODE, Role.FLOW_TEMPERATURE, Role.FLOW_SETPOINT}
    )
    optional_signals = frozenset({Role.RETURN_TEMPERATURE})
    params_schema = TemperatureParams

    def history_ms(self, params: RuleParams) -> int:
        return self.typed(params).window_days * DAY_MS

    def certainty_criteria(self, params: RuleParams) -> CertaintyCriteria:
        return pattern_criteria(self.typed(params))

    def _evaluate(self, ctx: RuleContext, params: TemperatureParams) -> Sequence[FindingCandidate]:
        cycles = [c for c in ctx.relevant_cycles() if c.complete]
        overshoot = [
            c
            for c in cycles
            if (v := cycle_metric(ctx, c, MetricName.OVERSHOOT)) is not None
            and v > params.overshoot_margin_c
        ]
        inverted = [
            c
            for c in cycles
            if (v := cycle_metric(ctx, c, MetricName.BOILER_DELTA_T_STABLE)) is not None and v < 0
        ]
        selected = sorted(
            {c.start: c for c in (*overshoot, *inverted)}.values(), key=lambda c: c.start
        )
        if len(selected) < params.min_temperature_cycles:
            return ()
        support = evidence(
            ctx, cycles, selected, self.required_signals, self.optional_signals, params
        )
        pair_coverage = min(
            (
                m.coverage
                for m in ctx.metrics
                if m.window.cycle_start in {c.start for c in selected}
                and m.name in (MetricName.OVERSHOOT, MetricName.BOILER_DELTA_T_STABLE)
                and m.value is not None
            ),
            default=0,
        )
        support = replace(support, coverage=min(support.coverage, pair_coverage))
        certainty = derive_certainty(support, self.certainty_criteria(params)).certainty
        return (
            FindingCandidate(
                scope_key="boiler:ch",
                category=self.category,
                title="Afwijkend temperatuurverloop tijdens cv-bedrijf",
                severity=Severity.LOW,
                certainty=certainty,
                relevance=(Relevance.ENERGY, Relevance.OPERATIONAL_STABILITY),
                observation=(
                    f"In {len(overshoot)} cv-cycli ligt de aanvoer boven gewenst plus "
                    f"de ingestelde marge. "
                    f"In {len(inverted)} cycli ligt de uitgelijnde retour tijdens "
                    f"stabiel bedrijf boven de aanvoer."
                ),
                period=pattern_period(selected),
                signals=tuple(sorted(signal_ref(r) for r in self.required_signals)),
                evidence=support,
                interpretation=""
                if certainty is Certainty.INSUFFICIENT_EVIDENCE
                else (
                    "Dit is een waargenomen temperatuurpatroon. Controleer "
                    "sensorplaatsing en de samenhang "
                    "met brandergedrag; een hydraulische oorzaak is hiermee niet vastgesteld."
                ),
                recommendation=measurement(
                    "Controleer sensorplaatsing en verzamel uitgelijnde temperatuurmetingen.",
                    "Ketelmetingen zijn geen metingen van afzonderlijke vloerverwarmingslussen.",
                ),
                refs=tuple(CycleRef(c.start) for c in selected),
                supports=("kort-branden", "stop-tijdens-vraag"),
            ),
        )
