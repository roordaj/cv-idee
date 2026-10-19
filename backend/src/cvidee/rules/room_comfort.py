"""Per-room comfort loss from explicit user targets (FR-17)."""

from collections.abc import Sequence

from cvidee.analysis.types import Role, Scope, ScopeKind, SignalRef
from cvidee.rules.base import (
    BaseRule,
    Category,
    Certainty,
    CertaintyCriteria,
    EvidenceSummary,
    FindingCandidate,
    NoParams,
    PeriodRef,
    RecommendationDraft,
    RecommendationKind,
    Relevance,
    RuleContext,
    RuleParams,
    Severity,
    SignalEvidence,
    Thresholds,
)

DAY_MS = 86_400_000


class RoomComfortRule(BaseRule[NoParams]):
    id = "comfort-per-ruimte"
    version = "1.0.0"
    category = Category.COMFORT
    required_signals = frozenset()
    params_schema = NoParams

    def history_ms(self, params: RuleParams) -> int:
        del params
        return 7 * DAY_MS

    def certainty_criteria(self, params: RuleParams) -> CertaintyCriteria:
        del params
        return CertaintyCriteria(minimum=Thresholds(), allow_measured=True)

    def _evaluate(self, ctx: RuleContext, params: NoParams) -> Sequence[FindingCandidate]:
        del params
        candidates = []
        for room_key, metrics in ctx.room_comfort:
            if (
                metrics.availability == "not_available"
                or metrics.coverage is None
                or metrics.coverage < ctx.minimum_room_comfort_coverage
                or metrics.observed_ms / 3_600_000 < ctx.minimum_room_comfort_observed_hours
                or metrics.target_comfort_loss_ms is None
                or metrics.observed_ms == 0
            ):
                continue
            loss_h_week = metrics.target_comfort_loss_ms / metrics.observed_ms * 168
            if loss_h_week <= ctx.allowed_room_comfort_loss_h_week:
                continue
            temperature = SignalRef(Role.ROOM_TEMPERATURE, Scope(ScopeKind.ROOM, room_key))
            certainty = Certainty.HIGH_MEASURED if metrics.coverage == 1.0 else Certainty.MODERATE
            candidates.append(
                FindingCandidate(
                    scope_key=f"room:{room_key}",
                    category=self.category,
                    title=f"Comfortverlies gemeten in {room_key}",
                    severity=Severity.MEDIUM,
                    certainty=certainty,
                    relevance=(Relevance.COMFORT,),
                    observation=(
                        f"De gemeten temperatuur lag omgerekend {loss_h_week:.1f}".replace(".", ",")
                        + " uur per week meer dan de ingestelde comfortgrens onder het "
                        f"comfortdoel van deze ruimte. Dekking tijdens comforturen: "
                        f"{metrics.coverage * 100:.0f}%."
                    ),
                    period=metrics.period,
                    signals=(temperature,),
                    evidence=EvidenceSummary(
                        coverage=metrics.coverage,
                        observed_hours=metrics.observed_ms / 3_600_000,
                        unknown_ms=metrics.expected_ms - metrics.observed_ms,
                    ),
                    interpretation=(
                        "Dit beschrijft de gemeten temperatuur ten opzichte van het door de "
                        "gebruiker ingestelde doel; het stelt geen oorzaak vast."
                    ),
                    recommendation=RecommendationDraft(
                        kind=RecommendationKind.CHECK,
                        action="Controleer het comfortdoel en de metingen van deze ruimte.",
                        reason="De gemeten comfortafwijking overschrijdt de ingestelde grens.",
                        expected_effect="Toont of doel en meetgegevens bij het gebruik passen.",
                        comfort_impact="Geen instelling wordt door de app gewijzigd.",
                        conditions="Beoordeel alleen gemeten comforturen met geldige dekking.",
                        evaluation="Bekijk de comfortmetingen na controle van doel en sensor.",
                        success_criterion="Doel en gegevens voor deze ruimte zijn gecontroleerd.",
                    ),
                    refs=(
                        PeriodRef(metrics.period, "Gemeten comforturen"),
                        SignalEvidence(temperature),
                    ),
                )
            )
        return tuple(candidates)
