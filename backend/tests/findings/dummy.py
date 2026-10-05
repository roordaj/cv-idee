"""A dummy rule and context builders for the findings tests."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import ClassVar

from cvidee.analysis.types import (
    HOUR_MS,
    ObservationKind,
    Provenance,
    Role,
    SignalRef,
    SignalTimeline,
    TimeRange,
    UnknownInterval,
    UnknownReason,
    ValueInterval,
    ValueKind,
)
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

DAY_MS = 24 * HOUR_MS
T0 = 1_791_064_800_000
FLAME = signal_ref(Role.FLAME)
OUTDOOR = signal_ref(Role.OUTDOOR_TEMPERATURE)


class DummyParams(RuleParams):
    threshold: int = param(
        3,
        title="Drempel",
        description="Testparameter.",
        unit="cycli",
        group=ParamGroup.SHORT_CYCLES,
    )


@dataclass(frozen=True, slots=True)
class Emit:
    scope_key: str = "boiler:ch"
    severity: Severity = Severity.MEDIUM
    certainty: Certainty = Certainty.MODERATE
    relevance: tuple[Relevance, ...] = (Relevance.ENERGY,)


class DummyRule(BaseRule[DummyParams]):
    """Emits the candidates listed in :attr:`emit` (set by the test); none when empty."""

    id = "dummy-regel"
    version = "1.0.0"
    category = Category.CYCLES
    required_signals = frozenset({Role.FLAME})
    params_schema = DummyParams
    emit: ClassVar[tuple[Emit, ...]] = ()

    def history_ms(self, params: RuleParams) -> int:
        return 7 * DAY_MS

    def certainty_criteria(self, params: RuleParams) -> CertaintyCriteria:
        return CertaintyCriteria(minimum=Thresholds())

    def _evaluate(self, ctx: RuleContext, params: DummyParams) -> Sequence[FindingCandidate]:
        out: list[FindingCandidate] = []
        period = TimeRange(ctx.now - HOUR_MS, ctx.now)
        for e in self.emit:
            insufficient = e.certainty is Certainty.INSUFFICIENT_EVIDENCE
            out.append(
                FindingCandidate(
                    scope_key=e.scope_key,
                    category=self.category,
                    title=f"Dummy {e.scope_key}",
                    severity=e.severity,
                    certainty=e.certainty,
                    relevance=e.relevance,
                    observation=f"Waargenomen op {e.scope_key} (drempel {params.threshold}).",
                    period=period,
                    signals=(FLAME,),
                    evidence=EvidenceSummary(
                        coverage=0.95,
                        relevant_cycles=10,
                        pattern_cycles=6,
                        repetition_days=2,
                        repetition_window_days=7,
                    ),
                    recommendation=(
                        RecommendationDraft(
                            kind=RecommendationKind.MEASUREMENT,
                            action="Koppel extra signalen.",
                            reason="Te weinig bewijs.",
                            expected_effect="Geen.",
                            comfort_impact="Geen.",
                            conditions="Geen.",
                            evaluation="Na 7 dagen.",
                            success_criterion="Voldoende cycli.",
                        )
                        if insufficient
                        else None
                    ),
                    no_advice_reason="" if insufficient else "Geen advies.",
                    refs=(PeriodRef(period), CycleRef(ctx.now - HOUR_MS)),
                )
            )
        return out


def timeline(
    signal: SignalRef,
    span: TimeRange,
    value: object = True,
    *,
    gap: TimeRange | None = None,
    step: tuple[int, object] | None = None,
) -> SignalTimeline:
    """A timeline over ``span`` with ``value`` (or ``step=(ts, value_after)``), unknown in
    ``gap``."""
    cuts = sorted({span.start, span.end} | ({gap.start, gap.end} if gap else set()))
    if step is not None:
        cuts = sorted({*cuts, step[0]})
    intervals: list[ValueInterval | UnknownInterval] = []
    for lo, hi in pairwise(cuts):
        if gap is not None and gap.start <= lo and hi <= gap.end:
            intervals.append(UnknownInterval(lo, hi, UnknownReason.DISCONNECTED))
            continue
        v = step[1] if step is not None and lo >= step[0] else value
        intervals.append(
            ValueInterval(
                lo,
                hi,
                v,  # type: ignore[arg-type]
                Provenance(ValueKind.REPORTED, "test.entity"),
                lo,
                ObservationKind.CHANGE,
            )
        )
    return SignalTimeline(signal, span, tuple(intervals))
