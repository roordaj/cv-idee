"""A mixing manifold without usable local data gets measurement advice only (FR-24/28)."""

from collections.abc import Sequence

from cvidee.analysis.types import Mode, QualityEventKind, Role, Scope, ScopeKind, SignalRef
from cvidee.rules.base import (
    BaseRule,
    Category,
    Certainty,
    CertaintyCriteria,
    EvidenceSummary,
    FindingCandidate,
    InstallationFacts,
    ParamGroup,
    Relevance,
    RuleContext,
    RuleParams,
    Severity,
    Thresholds,
    param,
    signal_ref,
)
from cvidee.rules.patterns import DAY_MS, WindowParams, measurement


class HydraulicParams(WindowParams):
    min_assessment_coverage_pct: int = param(
        80,
        title="Minimale dekking voor een beoordeling",
        description="Minimale dekking van lokale verdelermetingen.",
        unit="%",
        group=ParamGroup.DATA,
        ge=50,
        le=100,
        step=1,
    )


class HydraulicRule(BaseRule[HydraulicParams]):
    id = "hydraulisch"
    version = "1.0.0"
    category = Category.HYDRAULIC
    # Missing measurements are the finding, so they must not gate this diagnostic rule.
    required_signals = frozenset()
    params_schema = HydraulicParams

    def applies_to(self, profile: InstallationFacts) -> bool:
        return profile.has_mixing_manifold

    def history_ms(self, params: RuleParams) -> int:
        return self.typed(params).window_days * DAY_MS

    def certainty_criteria(self, params: RuleParams) -> CertaintyCriteria:
        return CertaintyCriteria(Thresholds(), max_certainty=Certainty.INSUFFICIENT_EVIDENCE)

    def _evaluate(self, ctx: RuleContext, params: HydraulicParams) -> Sequence[FindingCandidate]:
        if ctx.cycles and not ctx.relevant_cycles(frozenset({Mode.CH})):
            return ()
        if sum(r.duration_ms for r in ctx.excluded_ranges()) >= ctx.period.duration_ms:
            return ()
        out = []
        for circuit in ctx.profile.circuits:
            if circuit.manifold is None:
                continue
            refs = tuple(
                sorted(
                    signal_ref(role, circuit.manifold)
                    for role in (Role.MANIFOLD_FLOW_TEMPERATURE, Role.MANIFOLD_RETURN_TEMPERATURE)
                )
            )
            flow = SignalRef(Role.FLOW_RATE, Scope(ScopeKind.CIRCUIT, circuit.key))

            def usable(ref: SignalRef) -> bool:
                status = ctx.signal_status(ref)
                return (
                    status is not None
                    and status.coverage >= params.min_assessment_coverage_pct / 100
                    and not status.stale
                )

            misaligned = any(
                e.kind is QualityEventKind.MISALIGNED
                and e.signal in refs
                and e.other_signal in refs
                for e in ctx.quality_events
            )
            if (all(usable(ref) for ref in refs) and not misaligned) or usable(flow):
                continue
            missing = tuple(sorted(ref for ref in (*refs, flow) if not usable(ref)))
            out.append(
                FindingCandidate(
                    scope_key=f"circuit:{circuit.key}:ch",
                    category=self.category,
                    title="Mengverdeler: onvoldoende gegevens voor een hydraulische conclusie",
                    severity=Severity.LOW,
                    certainty=Certainty.INSUFFICIENT_EVIDENCE,
                    relevance=(Relevance.COMFORT, Relevance.ENERGY),
                    observation=(
                        f"Circuit {circuit.key} heeft een mengverdeler. Bruikbare, lokale "
                        f"verdelermetingen ontbreken of zijn niet uitgelijnd."
                    ),
                    period=ctx.period,
                    signals=tuple(ref for ref in (*refs, flow) if ctx.is_mapped(ref)),
                    evidence=EvidenceSummary(
                        coverage=min(
                            (
                                status.coverage
                                if (status := ctx.signal_status(ref)) is not None
                                else 0
                                for ref in refs
                            ),
                            default=0,
                        ),
                        missing_signals=missing,
                    ),
                    interpretation=(
                        "Ketel-ΔT is niet de ΔT per vloerverwarmingslus. Zonder lokale "
                        "gegevens wordt geen wijziging aan lusdebiet of mengtemperatuur aanbevolen."
                    ),
                    recommendation=measurement(
                        (
                            f"Aanvullende meting: plaats temperatuursensoren op "
                            f"verdeleraanvoer en -retour ({circuit.key})."
                        ),
                        "Maakt het afgiftecircuit los van het ketelcircuit te beoordelen.",
                    ),
                    supports=("kort-branden",),
                )
            )
        return tuple(out)
