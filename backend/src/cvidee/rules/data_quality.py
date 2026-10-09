"""Data-loss and stale-sensor findings; data gaps never prove recovery (FR-07/11)."""

from collections.abc import Sequence

from cvidee.analysis.types import (
    ConnectionSource,
    EndReason,
    QualityEvent,
    QualityEventKind,
    TimeRange,
)
from cvidee.rules.base import (
    BaseRule,
    Category,
    Certainty,
    CertaintyCriteria,
    EvidenceSummary,
    FindingCandidate,
    PeriodRef,
    QualityEventRef,
    Relevance,
    RuleContext,
    RuleParams,
    Severity,
    Thresholds,
)
from cvidee.rules.patterns import DAY_MS, WindowParams


def merged_ranges(events: Sequence[QualityEvent], period: TimeRange) -> tuple[TimeRange, ...]:
    spans = sorted(
        (
            r
            for e in events
            if (end := min(e.end if e.end is not None else period.end, period.end))
            > max(e.start, period.start)
            and (r := TimeRange(max(e.start, period.start), end)) is not None
        ),
        key=lambda r: r.start,
    )
    out: list[TimeRange] = []
    for span in spans:
        if out and span.start <= out[-1].end:
            out[-1] = TimeRange(out[-1].start, max(out[-1].end, span.end))
        else:
            out.append(span)
    return tuple(out)


class DataLossRule(BaseRule[WindowParams]):
    id = "dataverlies"
    version = "1.0.0"
    category = Category.DATA_QUALITY
    required_signals = frozenset()
    params_schema = WindowParams

    def history_ms(self, params: RuleParams) -> int:
        return self.typed(params).window_days * DAY_MS

    def certainty_criteria(self, params: RuleParams) -> CertaintyCriteria:
        return CertaintyCriteria(
            Thresholds(), reasonable=Thresholds(), high=Thresholds(), allow_measured=True
        )

    def _evaluate(self, ctx: RuleContext, params: WindowParams) -> Sequence[FindingCandidate]:
        out = []
        events = ctx.quality_events_of(QualityEventKind.CONNECTION_LOST)
        for source in (ConnectionSource.WS, ConnectionSource.CAN_GATEWAY):
            relevant = [e for e in events if e.source is source]
            spans = merged_ranges(relevant, ctx.period)
            if not spans:
                continue
            affected = (
                tuple(sorted(s.signal for s in ctx.signals))
                if source is ConnectionSource.WS
                else ctx.gateway_signals
            )
            incomplete = [
                c
                for c in ctx.cycles
                if not c.complete
                and c.end_reason is EndReason.DATA_GAP
                and any(c.start < r.end and r.start <= (c.end or ctx.now) for r in spans)
            ]
            duration_s = sum(r.duration_ms for r in spans) // 1000
            name = "Home Assistant-verbinding" if source is ConnectionSource.WS else "CAN-data"
            text = (
                f"De {name} was {duration_s} seconden onderbroken in {len(spans)} tijdvakken. "
                f"{len(incomplete)} branderperioden hebben hierdoor geen volledig "
                f"waargenomen einde."
            )
            text += (
                f" {len(affected)} gekoppelde signalen vallen onder deze bron."
                if affected
                else " Getroffen signalen zijn niet per entiteit vastgesteld."
            )
            out.append(
                FindingCandidate(
                    scope_key=f"source:{source.value}",
                    category=self.category,
                    title=f"{name} onderbroken",
                    severity=Severity.MEDIUM,
                    certainty=Certainty.MODERATE
                    if any(e.detail == "derived" for e in relevant)
                    else Certainty.HIGH_MEASURED,
                    relevance=(Relevance.DATA_RELIABILITY,),
                    observation=text,
                    period=TimeRange(spans[0].start, spans[-1].end),
                    signals=affected,
                    evidence=EvidenceSummary(
                        coverage=0,
                        unknown_ms=sum(r.duration_ms for r in spans),
                        relevant_cycles=len(incomplete),
                    ),
                    interpretation=(
                        "Deze tijd telt als onbekend, niet als uit-tijd. "
                        "Een datagat bewijst geen herstel van een lopend patroon. Na "
                        "reconnect telt een peiling niet als branderstart."
                    ),
                    no_advice_reason=(
                        "Geen optimalisatieadvies. Als de onderbreking terugkeert: "
                        "controleer de gateway en de verbinding met Home Assistant."
                    ),
                    refs=tuple(PeriodRef(r) for r in spans),
                )
            )
        # HA can stay connected while one device explicitly reports unknown/unavailable.
        # This proves missing values, not loss of the HA or CAN connection itself.
        unavailable = ctx.quality_events_of(QualityEventKind.UNAVAILABLE)
        for ref in sorted({e.signal for e in unavailable if e.signal is not None}):
            relevant = [e for e in unavailable if e.signal == ref]
            spans = merged_ranges(relevant, ctx.period)
            if not spans:
                continue
            if any(
                ref in finding.signals
                and finding.period.start <= spans[0].start
                and spans[-1].end <= finding.period.end
                for finding in out
            ):
                continue
            out.append(
                FindingCandidate(
                    scope_key=f"signal:{ref}",
                    category=self.category,
                    title="Signaalgegevens ontbreken",
                    severity=Severity.MEDIUM,
                    certainty=Certainty.HIGH_MEASURED,
                    relevance=(Relevance.DATA_RELIABILITY,),
                    observation="Home Assistant meldt expliciet onbekende of onbeschikbare "
                    f"waarden voor {ref}.",
                    period=TimeRange(spans[0].start, spans[-1].end),
                    signals=(ref,),
                    evidence=EvidenceSummary(
                        coverage=0, unknown_ms=sum(r.duration_ms for r in spans)
                    ),
                    interpretation="Deze tijd telt als onbekend. "
                    "Een verbindingsoorzaak is niet vastgesteld.",
                    no_advice_reason="Geen optimalisatieadvies. "
                    "Controleer de bron van het signaal.",
                    refs=tuple(PeriodRef(r) for r in spans),
                )
            )
        return tuple(out)


class StaleSensorRule(BaseRule[WindowParams]):
    id = "sensor-verouderd"
    version = "1.0.0"
    category = Category.DATA_QUALITY
    required_signals = frozenset()
    params_schema = WindowParams

    def history_ms(self, params: RuleParams) -> int:
        return self.typed(params).window_days * DAY_MS

    def certainty_criteria(self, params: RuleParams) -> CertaintyCriteria:
        return CertaintyCriteria(
            Thresholds(), reasonable=Thresholds(), high=Thresholds(), allow_measured=True
        )

    def _evaluate(self, ctx: RuleContext, params: WindowParams) -> Sequence[FindingCandidate]:
        out = []
        events = ctx.quality_events_of(QualityEventKind.STALE)
        for ref in sorted({e.signal for e in events if e.signal is not None}):
            relevant = [e for e in events if e.signal == ref]
            spans = merged_ranges(relevant, ctx.period)
            if not spans:
                continue
            status = ctx.signal_status(ref)
            out.append(
                FindingCandidate(
                    scope_key=str(ref),
                    category=self.category,
                    title="Sensor verouderd",
                    severity=Severity.LOW,
                    certainty=Certainty.HIGH_MEASURED,
                    relevance=(Relevance.DATA_RELIABILITY,),
                    observation=f"Signaal {ref} overschreed de ingestelde maximale leeftijd "
                    "gedurende "
                    f"{sum(r.duration_ms for r in spans) // 1000} seconden.",
                    period=TimeRange(spans[0].start, spans[-1].end),
                    signals=(ref,),
                    evidence=EvidenceSummary(
                        coverage=0 if status is None else status.coverage,
                        unknown_ms=sum(r.duration_ms for r in spans),
                    ),
                    interpretation=(
                        "Verouderde waarden tellen als onbekend en worden niet "
                        "gecombineerd met nieuwere waarden voor een temperatuurconclusie."
                    ),
                    no_advice_reason=(
                        "Geen optimalisatieadvies. Controleer de sensor en de verwachte "
                        "rapportagefrequentie."
                    ),
                    refs=tuple(QualityEventRef(e.kind, e.start, ref) for e in relevant),
                )
            )
        return tuple(out)
