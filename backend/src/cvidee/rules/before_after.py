"""Explain change evaluations without claiming correlation proves a cause (FR-30/32)."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import model_validator

from cvidee.analysis.change_evaluation import EVALUATION_VERSION
from cvidee.analysis.types import OUTDOOR, Role, Scope, ScopeKind, SignalRef, TimeRange
from cvidee.rules.base import (
    BaseRule,
    Category,
    Certainty,
    CertaintyCriteria,
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
)


class BeforeAfterParams(RuleParams):
    short_cycle_min: float = param(
        3.0,
        title="Kortecyclusgrens",
        description="Grens voor het aandeel korte CV-cycli.",
        unit="min",
        group=ParamGroup.SHORT_CYCLES,
        ge=1,
        le=15,
        step=0.5,
    )
    min_observation_hours: float = param(
        6.0,
        title="Minimale observatieduur",
        description="Benodigde waargenomen uren met warmtevraag per periode.",
        unit="uur",
        group=ParamGroup.EFFECT_MEASUREMENT,
        ge=1,
        le=72,
        step=1,
    )

    comparison_days: int = param(
        7,
        title="Lengte vergelijkingsperiode",
        description="Even lange perioden vóór en na de wijziging.",
        unit="dagen",
        group=ParamGroup.EFFECT_MEASUREMENT,
        ge=3,
        le=28,
        step=1,
    )
    comparable_weather_c: float = param(
        2.0,
        title="Vergelijkbaar weer",
        description="Maximaal temperatuurverschil voor vergelijkbaar weer.",
        unit="°C",
        group=ParamGroup.EFFECT_MEASUREMENT,
        ge=0.5,
        le=6,
        step=0.5,
    )
    limited_weather_c: float = param(
        4.0,
        title="Beperkt vergelijkbaar weer",
        description="Boven dit verschil wordt geen effect toegeschreven.",
        unit="°C",
        group=ParamGroup.EFFECT_MEASUREMENT,
        ge=1,
        le=10,
        step=0.5,
    )
    min_period_coverage_pct: int = param(
        90,
        title="Minimale dekking per periode",
        description="Benodigde gegevensdekking in beide perioden.",
        unit="%",
        group=ParamGroup.EFFECT_MEASUREMENT,
        ge=50,
        le=100,
        step=1,
    )
    comfort_margin_c: float = param(
        0.5,
        title="Comfortgrens",
        description="Afwijking onder het kamersetpoint die als te koud telt.",
        unit="°C",
        group=ParamGroup.COMFORT,
        ge=0.1,
        le=3,
        step=0.1,
    )
    allowed_comfort_loss_h_per_week: float = param(
        4.0,
        title="Toegestaan comfortverlies",
        description="Standaard terugdraaicriterium per ruimte.",
        unit="u/week",
        group=ParamGroup.COMFORT,
        ge=0,
        le=40,
        step=0.5,
    )

    @model_validator(mode="after")
    def ordered_weather(self) -> BeforeAfterParams:
        if self.limited_weather_c < self.comparable_weather_c:
            raise ValueError("limited_weather_c must be >= comparable_weather_c")
        return self


def _number(value: float | None) -> str:
    return "onbekend" if value is None else f"{value:.1f}".replace(".", ",")


class BeforeAfterRule(BaseRule[BeforeAfterParams]):
    id = "voor-na"
    version = EVALUATION_VERSION
    category = Category.EFFECT_MEASUREMENT
    required_signals = frozenset()
    params_schema = BeforeAfterParams

    def history_ms(self, params: RuleParams) -> int:
        del params
        # Evaluations already carry their own before/after windows and evidence.
        return 0

    def certainty_criteria(self, params: RuleParams) -> CertaintyCriteria:
        return CertaintyCriteria(
            Thresholds(coverage=self.typed(params).min_period_coverage_pct / 100),
            reasonable=Thresholds(),
            max_certainty=Certainty.REASONABLE,
        )

    def _evaluate(self, ctx: RuleContext, params: BeforeAfterParams) -> Sequence[FindingCandidate]:
        del params
        results = []
        eligible = tuple(
            f
            for f in ctx.change_evaluations
            if f.verdict not in ("pending", "improved") or f.rollback
        )
        eligible_ids = {f.change_id for f in eligible}
        for fact in eligible:
            group = {fact.change_id, *(i for i in fact.overlap_ids if i in eligible_ids)}
            if fact.change_id != min(group):
                continue
            limited = (
                fact.weather != "yes"
                or fact.setpoints != "yes"
                or bool(fact.overlap_ids)
                or any(
                    value is None or value > fact.policy.short_cycle_s * 250
                    for value in (fact.before.flame_resolution_ms, fact.after.flame_resolution_ms)
                )
            )
            insufficient = fact.verdict == "insufficient_evidence"
            certainty = (
                Certainty.INSUFFICIENT_EVIDENCE
                if insufficient
                else Certainty.PRELIMINARY
                if limited
                else Certainty.REASONABLE
            )
            observation = (
                f"{fact.change_id}: CV-starts per waargenomen uur "
                f"{_number(fact.before.starts_per_hour)} vóór en "
                f"{_number(fact.after.starts_per_hour)} na. "
                + " ".join(
                    f"Comfortverlies {room}: {_number(value)} u/week na de wijziging."
                    for room, value in fact.after.cold_hours
                )
            )
            if fact.overlap_ids:
                observation += " Andere wijzigingen: " + ", ".join(fact.overlap_ids) + "."
            action = (
                "Beoordeel het terugzetten van de vastgelegde wijziging naar de oude waarde."
                if fact.rollback
                else "Verzamel vergelijkbare gegevens met één wijziging tegelijk "
                "en gekoppelde kamerdoelen."
            )
            recommendation = RecommendationDraft(
                kind=RecommendationKind.CHECK if fact.rollback else RecommendationKind.MEASUREMENT,
                action=action,
                reason=fact.summary,
                expected_effect=(
                    "Herstel van comfort beoordelen zonder een oorzaak als bewezen te presenteren."
                ),
                comfort_impact="De ingestelde comfortgrens per ruimte blijft leidend.",
                conditions=(
                    "Vergelijkbaar weer, ongewijzigde kamerdoelen en voldoende gegevensdekking."
                ),
                evaluation=(
                    "Vergelijk de CV-cycli en het comfort per ruimte opnieuw na de vervolgstap."
                ),
                success_criterion=(
                    "Comfort herstelt zonder onaanvaardbare verslechtering van de CV-cycli."
                ),
                rollback_criterion=(
                    "N.v.t. — beoordeel de eerdere wijziging "
                    "en het oorspronkelijke terugdraaicriterium."
                ),
            )
            mapped = {s.signal for s in ctx.signals}
            required = {
                SignalRef(role) for role in (Role.FLAME, Role.OPERATING_MODE, Role.HEAT_DEMAND)
            }
            required.add(SignalRef(Role.OUTDOOR_TEMPERATURE, OUTDOOR))
            for room, _ in fact.before.cold_hours:
                required.update(
                    SignalRef(role, Scope(ScopeKind.ROOM, room))
                    for role in (Role.ROOM_TEMPERATURE, Role.ROOM_SETPOINT)
                )
            if fact.before.flow_stable_c is not None or fact.after.flow_stable_c is not None:
                required.add(SignalRef(Role.FLOW_TEMPERATURE))
            signals = tuple(sorted(required))
            missing = tuple(sorted(required - mapped)) if insufficient else ()

            results.append(
                FindingCandidate(
                    scope_key=f"change:{fact.change_id}",
                    category=self.category,
                    title="Minder korte cycli, maar slechter comfort"
                    if fact.verdict == "trade_off"
                    else "Terugdraaicriterium geactiveerd"
                    if fact.rollback
                    else "Effect niet toe te schrijven"
                    if fact.verdict == "not_attributable"
                    else "Onvoldoende bewijs voor het effect"
                    if insufficient
                    else "Wijziging gaf een ongunstige uitkomst",
                    severity=Severity.MEDIUM
                    if fact.rollback or fact.verdict in ("trade_off", "worsened")
                    else Severity.INFO,
                    certainty=certainty,
                    relevance=(Relevance.COMFORT, Relevance.OPERATIONAL_STABILITY),
                    observation=observation,
                    interpretation=fact.summary,
                    period=TimeRange(fact.reference.start, fact.observation.end),
                    signals=signals,
                    evidence=EvidenceSummary(
                        coverage=min(fact.before.coverage, fact.after.coverage),
                        excluded_ms=fact.before.excluded_ms + fact.after.excluded_ms,
                        unknown_ms=round(
                            (fact.reference.duration_ms - fact.before.excluded_ms)
                            * (1 - fact.before.coverage)
                        )
                        + round(
                            (fact.observation.duration_ms - fact.after.excluded_ms)
                            * (1 - fact.after.coverage)
                        ),
                        missing_signals=missing,
                        relevant_cycles=fact.before.cycles + fact.after.cycles,
                        observed_hours=fact.before.observed_hours + fact.after.observed_hours,
                    ),
                    recommendation=recommendation,
                    refs=(PeriodRef(fact.reference, "Voor"), PeriodRef(fact.observation, "Na")),
                )
            )
        return results
