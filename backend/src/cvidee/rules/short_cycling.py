"""Rule ``kort-branden`` (FR-14, FR-23): repeated short burns during heat demand.

Counts complete CH cycles that stop while heat demand continues
(``EndReason.STOP_DURING_DEMAND``) and last shorter than the short-cycle limit. DHW cycles
and cycles in excluded special periods never count (``RuleContext.relevant_cycles``). One
short cycle is never a finding: the pattern needs ``min_short_cycles`` of them. The
"demand continues after stop" criterion (``heat_demand_after_stop``) is part of the
pipeline's end-reason classification; this rule does not re-derive it.

Texts are Dutch UI text from design v3 (finding B-014). Numbers in the texts come from the
data; nothing is converted to kW and no setting change is advised without evidence.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from typing import Self

from pydantic import model_validator

from cvidee.analysis.types import (
    HOUR_MS,
    MINUTE_MS,
    BurnerCycle,
    DurationMs,
    EndReason,
    Mode,
    Role,
    ScopeKind,
    SignalRef,
    TimeRange,
)
from cvidee.rules.base import (
    AvailabilityStatus,
    BaseRule,
    Category,
    Certainty,
    CertaintyCriteria,
    CycleRef,
    EvidenceSummary,
    FindingCandidate,
    Hypothesis,
    ParamGroup,
    PeriodRef,
    RecommendationDraft,
    RecommendationKind,
    Relevance,
    ResolutionLimit,
    RuleContext,
    RuleParams,
    Severity,
    Thresholds,
    param,
    signal_ref,
)
from cvidee.rules.certainty import derive_certainty
from cvidee.rules.patterns import DEFAULT_SHORT_CYCLE_LIMIT_MIN

DAY_MS: DurationMs = 24 * HOUR_MS
MIN_SHORT_CYCLES_PER_DAY = 2
"""A day counts for the repetition when at least this many short cycles occurred on it."""


class ShortCyclingParams(RuleParams):
    short_cycle_min: float = param(
        DEFAULT_SHORT_CYCLE_LIMIT_MIN,
        title="Kortecyclusgrens",
        description="Een cv-cyclus die korter duurt dan deze grens én stopt terwijl de "
        "thermostaat nog warmte vraagt, telt als korte cyclus.",
        unit="min",
        step=0.5,
        ge=1,
        le=15,
        group=ParamGroup.SHORT_CYCLES,
    )
    min_short_cycles: int = param(
        4,
        title="Minimum aantal korte cycli",
        description="Zoveel korte cycli moeten er binnen één beoordeling zijn voordat de app "
        "een patroon meldt. Eén korte cyclus is nooit een waarschuwing.",
        unit="cycli",
        step=1,
        ge=2,
        le=30,
        group=ParamGroup.SHORT_CYCLES,
    )
    min_observation_h: float = param(
        6.0,
        title="Minimale observatieduur",
        description="Zoveel uur met gegevens tijdens cv-bedrijf of warmtevraag is nodig "
        "voordat de app iets over cycli concludeert. Uren zonder gegevens tellen niet mee.",
        unit="uur",
        step=1,
        ge=1,
        le=72,
        group=ParamGroup.SHORT_CYCLES,
    )
    structural_days: int = param(
        2,
        title="Herhaling over dagen",
        description="Een patroon heet structureel als het op minstens zoveel dagen binnen de "
        "periode voorkomt. Daarvoor is de zekerheid lager (voorlopig).",
        unit="dagen",
        step=1,
        ge=1,
        le=14,
        group=ParamGroup.SHORT_CYCLES,
    )
    window_days: int = param(
        7,
        title="Beoordelingsperiode",
        description="Aantal laatste dagen waarover herhaling wordt beoordeeld.",
        unit="dagen",
        step=1,
        ge=3,
        le=28,
        group=ParamGroup.SHORT_CYCLES,
    )

    @model_validator(mode="after")
    def _repetition_within_window(self) -> Self:
        if self.structural_days > self.window_days:
            raise ValueError("structural_days must be <= window_days")
        return self


_HYPOTHESIS_ROLES: frozenset[Role] = frozenset(
    {
        Role.VALVE_STATE,
        Role.PUMP_STATE,
        Role.FLOW_RATE,
        Role.MANIFOLD_FLOW_TEMPERATURE,
        Role.MANIFOLD_RETURN_TEMPERATURE,
    }
)
_TEMPERATURE_ROLES = (
    Role.FLOW_SETPOINT,
    Role.FLOW_TEMPERATURE,
    Role.RETURN_TEMPERATURE,
    Role.MODULATION,
)


class ShortCyclingRule(BaseRule[ShortCyclingParams]):
    id = "kort-branden"
    version = "1.1.0"
    category = Category.CYCLES
    required_signals = frozenset({Role.FLAME, Role.OPERATING_MODE, Role.HEAT_DEMAND})
    optional_signals = frozenset(
        {*_TEMPERATURE_ROLES, Role.OUTDOOR_TEMPERATURE, *_HYPOTHESIS_ROLES}
    )
    applies_in_modes = frozenset({Mode.CH})
    params_schema = ShortCyclingParams

    def history_ms(self, params: RuleParams) -> DurationMs:
        return self.typed(params).window_days * DAY_MS

    def resolution_limits(self, params: RuleParams) -> tuple[ResolutionLimit, ...]:
        limit_ms = round(self.typed(params).short_cycle_min * MINUTE_MS)
        return (
            ResolutionLimit(Role.FLAME, limit_ms // 2, AvailabilityStatus.UNAVAILABLE),
            ResolutionLimit(Role.FLAME, limit_ms // 4, AvailabilityStatus.LIMITED),
        )

    def certainty_criteria(self, params: RuleParams) -> CertaintyCriteria:
        p = self.typed(params)
        return CertaintyCriteria(
            minimum=Thresholds(coverage=0.8, observed_hours=p.min_observation_h),
            structural_repetition_days=p.structural_days,
            repetition_window_days=p.window_days,
            reasonable=Thresholds(coverage=0.9, relevant_cycles=12, repetition_days=3),
            high=Thresholds(coverage=0.95, relevant_cycles=30, repetition_days=5),
            max_certainty=Certainty.HIGH,
        )

    def unavailable_evidence(
        self, ctx: RuleContext, params: RuleParams
    ) -> Sequence[FindingCandidate]:
        """Report observable short burns without assigning a mode or end reason."""
        params = self.typed(params)
        missing_core = ctx.unmapped((signal_ref(Role.OPERATING_MODE), signal_ref(Role.HEAT_DEMAND)))
        if len(missing_core) != 2 or not ctx.is_mapped(signal_ref(Role.FLAME)):
            return ()
        limit_ms = round(params.short_cycle_min * MINUTE_MS)
        cycles = tuple(
            c
            for c in ctx.cycles_in(ctx.period)
            if c.complete
            and c.mode is Mode.UNKNOWN
            and c.end_reason is EndReason.UNDETERMINED
            and c.duration_ms < limit_ms
            and not ctx.is_excluded(TimeRange(c.start, c.end or c.start + 1))
        )
        if len(cycles) < params.min_short_cycles:
            return ()
        first, last = cycles[0], cycles[-1]
        pattern_period = TimeRange(first.start, last.end or last.start + 1)
        missing = tuple(
            sorted(
                {
                    *missing_core,
                    *ctx.unmapped(
                        (signal_ref(Role.RETURN_TEMPERATURE), signal_ref(Role.MODULATION))
                    ),
                    *(
                        signal_ref(Role.ROOM_TEMPERATURE, key)
                        for key in ctx.profile.scope_keys(Role.ROOM_TEMPERATURE.scope_kind)
                    ),
                }
            )
        )
        evidence = EvidenceSummary(
            coverage=0.0,
            unknown_ms=ctx.period.duration_ms,
            relevant_cycles=len(cycles),
            pattern_cycles=len(cycles),
            missing_signals=missing,
        )
        return (
            FindingCandidate(
                scope_key="boiler:ch",
                category=self.category,
                title="Korte branderperioden, maar onvoldoende gegevens voor beoordeling",
                severity=Severity.INFO,
                certainty=Certainty.INSUFFICIENT_EVIDENCE,
                relevance=(),
                observation=(
                    f"Er zijn {len(cycles)} volledige branderperioden korter dan "
                    f"{_minutes(params.short_cycle_min)} gemeten. De bedrijfsmodus en "
                    "eindreden zijn onbekend; dit zijn geen vastgestelde korte cv-cycli "
                    "tijdens warmtevraag."
                ),
                period=pattern_period,
                signals=(signal_ref(Role.FLAME),),
                evidence=evidence,
                recommendation=RecommendationDraft(
                    kind=RecommendationKind.MEASUREMENT,
                    action="Koppel de ontbrekende signalen en herhaal daarna de analyse.",
                    reason=(
                        "De cycli zijn geteld, maar kunnen niet aan cv-bedrijf of een "
                        "eindreden worden gekoppeld."
                    ),
                    expected_effect="Een beoordeling van korte cv-cycli wordt mogelijk.",
                    comfort_impact="Geen wijziging aan de installatie.",
                    conditions="Gebruik gegevens uit dezelfde installatieperiode.",
                    evaluation="Herhaal de analyse zodra de ontbrekende signalen beschikbaar zijn.",
                    success_criterion=(
                        "Bedrijfsmodus en warmtevraag zijn tijdens de cycli beschikbaar."
                    ),
                ),
                refs=(PeriodRef(pattern_period, "niet-geclassificeerde korte branderperioden"),),
            ),
        )

    def _evaluate(self, ctx: RuleContext, params: ShortCyclingParams) -> Sequence[FindingCandidate]:
        limit_ms = round(params.short_cycle_min * MINUTE_MS)
        period = ctx.period
        relevant = ctx.relevant_cycles(frozenset({Mode.CH}), period)
        complete = [c for c in relevant if c.complete]
        short = [
            c
            for c in complete
            if c.end_reason is EndReason.STOP_DURING_DEMAND and c.duration_ms < limit_ms
        ]
        if len(short) < params.min_short_cycles:
            return ()

        days = ctx.local_days(period)[-params.window_days :]
        days_with_pattern = sum(
            1
            for d in days
            if sum(1 for c in short if d.contains(c.start)) >= MIN_SHORT_CYCLES_PER_DAY
        )
        coverage = _core_coverage(ctx)
        observed_ms = sum(c.duration_ms + (c.pause_before_ms or 0) for c in complete)
        excluded = ctx.excluded_cycles(frozenset({Mode.CH}), period)
        evidence = EvidenceSummary(
            coverage=coverage,
            unknown_ms=round(period.duration_ms * (1.0 - coverage)),
            excluded_ms=sum(r.duration_ms for r in ctx.excluded_ranges(period)),
            excluded_cycles=len(excluded),
            relevant_cycles=len(complete),
            pattern_cycles=len(short),
            observed_hours=observed_ms / HOUR_MS,
            repetition_days=days_with_pattern,
            repetition_window_days=len(days),
            missing_signals=_missing_signals(ctx),
        )
        certainty = derive_certainty(evidence, self.certainty_criteria(params)).certainty
        insufficient = certainty is Certainty.INSUFFICIENT_EVIDENCE
        weak = insufficient or certainty is Certainty.PRELIMINARY

        severity = (
            Severity.HIGH if not weak and len(short) / len(complete) >= 0.5 else Severity.MEDIUM
        )
        pattern_period = TimeRange(short[0].start, max(c.end or c.start + 1 for c in short))
        observation = (
            f"In {len(short)} van {len(complete)} cv-cycli stopt de brander binnen "
            f"{_minutes(params.short_cycle_min)} terwijl de warmtevraag blijft bestaan "
            f"(op {days_with_pattern} van {len(days)} dagen)." + _temperature_observation(short)
        )
        interpretation = (
            ""
            if insufficient
            else "Dit past bij onvoldoende warmteafgifte ten opzichte van het geleverde "
            "vermogen, maar bewijst de oorzaak niet. Drie verklaringen zijn mogelijk:"
        )
        used = {
            *self.required_signals,
            *(
                r
                for r in (*_TEMPERATURE_ROLES[:2], Role.MODULATION)
                if ctx.is_mapped(signal_ref(r))
            ),
        }
        return (
            FindingCandidate(
                scope_key="boiler:ch",
                category=self.category,
                title="Herhaald kort branden tijdens aanhoudende warmtevraag",
                severity=severity,
                certainty=certainty,
                relevance=(Relevance.ENERGY, Relevance.OPERATIONAL_STABILITY),
                observation=observation,
                period=pattern_period,
                signals=tuple(signal_ref(r) for r in sorted(used)),
                evidence=evidence,
                interpretation=interpretation,
                hypotheses=() if insufficient else _hypotheses(ctx, short),
                recommendation=_advice(params, insufficient),
                refs=(
                    PeriodRef(pattern_period, "korte cycli"),
                    *(CycleRef(c.start) for c in short),
                ),
            ),
        )


def _core_coverage(ctx: RuleContext) -> float:
    values = [
        s.coverage
        for role in (Role.FLAME, Role.OPERATING_MODE, Role.HEAT_DEMAND)
        if (s := ctx.signal_status(signal_ref(role))) is not None
    ]
    return min(values) if values else 0.0


def _missing_signals(ctx: RuleContext) -> tuple[SignalRef, ...]:
    """Optional signals that would help distinguish the hypotheses and are not mapped."""
    refs: set[SignalRef] = set()
    for role in (*_HYPOTHESIS_ROLES, *_TEMPERATURE_ROLES, Role.OUTDOOR_TEMPERATURE):
        if any(s.signal.role is role for s in ctx.signals):
            continue
        if role.scope_kind in (ScopeKind.BOILER, ScopeKind.OUTDOOR):
            refs.add(signal_ref(role))
        else:
            refs.update(signal_ref(role, k) for k in ctx.profile.scope_keys(role.scope_kind))
    return tuple(sorted(refs))


def _nl(value: float, digits: int = 0) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _minutes(value: float) -> str:
    return f"{_nl(value, 0 if value == int(value) else 1)} minuten"


def _overshoots(short: Sequence[BurnerCycle]) -> list[float]:
    return [
        c.aggregates.flow_max_c - c.aggregates.flow_setpoint_c
        for c in short
        if c.aggregates.flow_max_c is not None and c.aggregates.flow_setpoint_c is not None
    ]


def _temperature_observation(short: Sequence[BurnerCycle]) -> str:
    overshoot = _overshoots(short)
    modulation = [
        c.aggregates.modulation_mean_pct
        for c in short
        if c.aggregates.modulation_mean_pct is not None
    ]
    parts = []
    if overshoot:
        above = sum(1 for o in overshoot if o > 0)
        parts.append(
            f"De werkelijke aanvoer komt in {above} van {len(overshoot)} korte cycli boven de "
            "gewenste aanvoer"
        )
    if modulation:
        text = f"modulatie gemiddeld {_nl(statistics.fmean(modulation))} %"
        parts.append(text if parts else text.capitalize())
    return " " + "; ".join(parts) + "." if parts else ""


def _hypotheses(ctx: RuleContext, short: Sequence[BurnerCycle]) -> tuple[Hypothesis, ...]:
    def mapped(*roles: Role) -> bool:
        return any(s.signal.role in roles for s in ctx.signals)

    overshoot = _overshoots(short)
    delta_t = [
        c.aggregates.flow_mean_c - c.aggregates.return_mean_c
        for c in short
        if c.aggregates.flow_mean_c is not None and c.aggregates.return_mean_c is not None
    ]
    modulation = [
        c.aggregates.modulation_min_pct
        for c in short
        if c.aggregates.modulation_min_pct is not None
    ]
    mod_mean = statistics.fmean(modulation) if modulation else None
    mod_text = f" ({_nl(mod_mean)} %)" if mod_mean is not None else ""

    if overshoot and statistics.fmean(overshoot) > 0:
        h1_for = (
            f"aanvoer ligt tijdens de korte cycli gemiddeld {_nl(statistics.fmean(overshoot), 1)}"
            f" K boven de gewenste aanvoer; modulatie staat op laag niveau{mod_text}."
            if mod_mean is not None
            else f"aanvoer ligt tijdens de korte cycli gemiddeld "
            f"{_nl(statistics.fmean(overshoot), 1)} K boven de gewenste aanvoer."
        )
    else:
        h1_for = "geen aanwijzing in de beschikbare gegevens."
    h2_for = (
        f"ketel-ΔT is tijdens branden gemiddeld {_nl(statistics.fmean(delta_t), 1)} K."
        if delta_t
        else "geen aanwijzing in de beschikbare gegevens (aanvoer of retour ontbreekt)."
    )
    h3_for = (
        f"modulatie staat tijdens de korte cycli op laag niveau{mod_text}."
        if mod_mean is not None
        else "geen aanwijzing in de beschikbare gegevens (modulatie ontbreekt)."
    )
    min_power = ctx.profile.boiler.min_power_kw
    h1_missing = (
        "open groepen en kranen tijdens de cycli zijn gekoppeld maar niet beoordeeld."
        if mapped(Role.VALVE_STATE, Role.ZONE_DEMAND)
        else "zone- en klepstatus niet gekoppeld."
    )
    h2_missing = (
        "pompstatus of debiet gekoppeld maar niet beoordeeld."
        if mapped(Role.PUMP_STATE, Role.FLOW_RATE)
        else "pompstatus en debiet onbekend."
    )
    if not mapped(Role.MANIFOLD_FLOW_TEMPERATURE, Role.MANIFOLD_RETURN_TEMPERATURE):
        h2_missing += " Verdeleraanvoer en -retour niet gekoppeld."
    h3_missing = (
        "minimumvermogen in kW niet vastgelegd."
        if min_power is None
        else f"minimumvermogen {_nl(min_power, 1)} kW is vastgelegd; de actuele warmtevraag "
        "is niet bekend."
    )
    if not mapped(Role.OUTDOOR_TEMPERATURE):
        h3_missing += " Buitentemperatuur niet gekoppeld."
    return (
        Hypothesis(
            name="Te weinig open afgifte",
            evidence_for=h1_for,
            missing=h1_missing,
            distinguishing_measurement=(
                "aantal open vloerverwarmingsgroepen en radiatorkranen tijdens de cycli."
            ),
            signals_needed=(Role.VALVE_STATE, Role.ZONE_DEMAND),
        ),
        Hypothesis(
            name="Beperkte doorstroming ketelcircuit",
            evidence_for=h2_for,
            missing=h2_missing,
            distinguishing_measurement="pompstatus of debiet; verdeleraanvoer en -retour.",
            signals_needed=(
                Role.PUMP_STATE,
                Role.FLOW_RATE,
                Role.MANIFOLD_FLOW_TEMPERATURE,
                Role.MANIFOLD_RETURN_TEMPERATURE,
            ),
        ),
        Hypothesis(
            name="Minimumvermogen boven actuele warmtevraag",
            evidence_for=h3_for,
            missing=h3_missing,
            distinguishing_measurement=(
                "vergelijk cycli bij lagere buitentemperatuur; leg minimumvermogen vast."
            ),
            signals_needed=(Role.OUTDOOR_TEMPERATURE,),
        ),
    )


def _advice(params: ShortCyclingParams, insufficient: bool) -> RecommendationDraft:
    if insufficient:
        return RecommendationDraft(
            kind=RecommendationKind.MEASUREMENT,
            action="Verzamel meer gegevens met cv-bedrijf voordat er iets wordt geconcludeerd.",
            reason=f"Er zijn minder dan {_nl(params.min_observation_h)} uur of te weinig "
            "gegevens met cv-bedrijf beschikbaar.",
            expected_effect="Geen direct effect. Maakt een beoordeling mogelijk.",
            comfort_impact="Geen invloed.",
            conditions="Geen gemarkeerde periode; vlamstatus, modus en warmtevraag gekoppeld.",
            evaluation=f"Opnieuw beoordelen na {params.window_days} dagen.",
            success_criterion="Voldoende observatieduur voor een beoordeling.",
            evaluation_days=params.window_days,
        )
    return RecommendationDraft(
        kind=RecommendationKind.CHECK,
        action="Controleer welke circuits werkelijk open staan en of doorstroming beschikbaar is.",
        reason="Onderscheidt hypothese 1 en 2 voordat een instelling wordt gewijzigd.",
        expected_effect="Geen direct energie-effect. Maakt een gerichte vervolgstap mogelijk.",
        comfort_impact="Geen invloed.",
        magnitude=None,
        conditions=(
            "Buitentemperatuur ±2 °C van referentie; geen gemarkeerde periode; "
            "zelfde thermostaatprogramma."
        ),
        evaluation="Vergelijk korte cycli en comfort 7 dagen na koppelen van zonestatus.",
        success_criterion="Eén hypothese wordt door de nieuwe meting ondersteund of uitgesloten.",
        rollback_criterion=None,
        evaluation_days=7,
        follow_up="Aanvoerverlaging alleen overwegen met een comfortgrens per ruimte.",
    )
