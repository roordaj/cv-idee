"""Observed stops during heat demand, with correlations rather than a diagnosis (FR-16)."""

from collections.abc import Sequence

from cvidee.analysis.types import MINUTE_MS, EndReason, MetricName, Mode, ModeCertainty, Role
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


class StopParams(PatternParams):
    min_stop_cycles: int = param(
        4,
        title="Minimum aantal stops tijdens vraag",
        description="Minimum aantal herhaalde stops voor een patroonmelding.",
        unit="cycli",
        group=ParamGroup.SHORT_CYCLES,
        ge=2,
        le=30,
        step=1,
    )
    demand_after_stop_s: int = param(
        60,
        title="Warmtevraag na stop",
        description="Tijd waarvoor de pipeline aanhoudende warmtevraag beoordeelt.",
        unit="s",
        group=ParamGroup.SHORT_CYCLES,
        ge=0,
        le=600,
        step=10,
    )


class StopDuringDemandRule(BaseRule[StopParams]):
    id = "stop-tijdens-vraag"
    version = "1.0.0"
    category = Category.CYCLES
    required_signals = frozenset({Role.FLAME, Role.OPERATING_MODE, Role.HEAT_DEMAND})
    optional_signals = frozenset({Role.FLOW_TEMPERATURE, Role.FLOW_SETPOINT, Role.MODULATION})
    params_schema = StopParams

    def history_ms(self, params: RuleParams) -> int:
        return self.typed(params).window_days * DAY_MS

    def certainty_criteria(self, params: RuleParams) -> CertaintyCriteria:
        return pattern_criteria(self.typed(params))

    def _evaluate(self, ctx: RuleContext, params: StopParams) -> Sequence[FindingCandidate]:
        cycles = [c for c in ctx.relevant_cycles() if c.complete]
        stops = [c for c in cycles if c.end_reason is EndReason.STOP_DURING_DEMAND]
        if len(stops) < params.min_stop_cycles:
            return ()
        overshoots = [cycle_metric(ctx, c, MetricName.OVERSHOOT_AT_STOP) for c in stops]
        known = [value for value in overshoots if value is not None]
        modulation = [
            c.aggregates.modulation_min_pct
            for c in cycles
            if c.aggregates.modulation_min_pct is not None
        ]
        low = min(modulation) if modulation else None
        at_low = (
            sum(c.aggregates.modulation_min_pct == low for c in stops) if low is not None else None
        )
        faults = sum(
            any(
                s.mode is Mode.FAULT_BLOCKING
                and s.certainty is ModeCertainty.DIRECT
                and s.start < (c.end or c.start) + max(1, params.demand_after_stop_s * 1000)
                and (c.end or c.start) - MINUTE_MS < s.end
                for s in ctx.mode_segments
            )
            for c in stops
        )
        support = evidence(ctx, cycles, stops, self.required_signals, self.optional_signals, params)
        certainty = derive_certainty(support, self.certainty_criteria(params)).certainty
        text = (
            f"In {len(stops)} van {len(cycles)} cv-cycli stopt de brander "
            f"terwijl de warmtevraag aanhoudt."
        )
        text += (
            (
                f" Bij {sum(value > 0 for value in known)} van {len(known)} "
                f"beoordeelbare stops ligt de aanvoer vlak vóór stop boven gewenst."
            )
            if known
            else " Temperatuur vlak vóór stop is niet met uitgelijnde gegevens te beoordelen."
        )
        text += (
            (
                f" In {at_low} cycli met een stop tijdens vraag is de laagste waargenomen "
                "modulatie bereikt "
                f"({str(low).replace('.', ',')} %)."
            )
            if low is not None
            else " Modulatiegegevens ontbreken."
        )
        text += f" {faults} stoptijden overlappen een gemelde storing/blokkering."
        return (
            FindingCandidate(
                scope_key="boiler:ch",
                category=self.category,
                title="Herhaald stoppen tijdens aanhoudende warmtevraag",
                severity=Severity.MEDIUM,
                certainty=certainty,
                relevance=(Relevance.OPERATIONAL_STABILITY, Relevance.ENERGY),
                observation=text,
                period=pattern_period(stops),
                signals=tuple(sorted(signal_ref(role) for role in self.required_signals)),
                evidence=support,
                interpretation=""
                if certainty is Certainty.INSUFFICIENT_EVIDENCE
                else (
                    "Temperatuur, modulatie en gemelde blokkeringen kunnen "
                    "samenhangen met de stops. "
                    "Deze correlatie bewijst geen oorzaak; ontbrekende meldingen "
                    "sluiten een blokkering niet uit."
                ),
                recommendation=measurement(
                    "Controleer temperatuur, modulatie en blokkeringen rond de stoptijden.",
                    "Onderscheid mogelijke verklaringen voordat een instelling wordt gewijzigd.",
                ),
                refs=tuple(CycleRef(c.start) for c in stops),
                supports=("kort-branden",),
            ),
        )
