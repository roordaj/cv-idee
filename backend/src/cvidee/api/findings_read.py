# ruff: noqa: RUF001, RUF002
"""Read model of persisted findings: ORM rows → API schemas (Dutch UI texts, #34)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from cvidee.api.problems import ProblemError, not_found
from cvidee.api.schemas.common import TimeRange
from cvidee.api.schemas.findings import (
    BundledEvidence,
    Evidence,
    EvidenceDisplay,
    EvidenceLink,
    FindingDetail,
    FindingList,
    FindingNote,
    FindingNoteCreate,
    FindingStatusUpdate,
    FindingSummary,
    HypothesisOut,
    PriorityFactor,
    PriorityOut,
    RecommendationOut,
    RuleRef,
)
from cvidee.api.stubs.fixtures import status_text
from cvidee.findings.recommendations import follow_up_baseline, reopen_if_due
from cvidee.findings.repository import SqlFindingRepository
from cvidee.rules.base import Category, RecommendationKind, Relevance
from cvidee.settings.repository import current_revision, effective_values
from cvidee.store.enums import (
    Certainty,
    EvidenceKind,
    FindingLifecycle,
    RecommendationOutcome,
    RecommendationStatus,
    Severity,
)
from cvidee.store.models import Finding, FindingEvidence, Recommendation, RecommendationNote

__all__ = ["FindingsReadModel"]

AMS = ZoneInfo("Europe/Amsterdam")
MONTHS = ("jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec")
DAY_NAMES = ("ma", "di", "wo", "do", "vr", "za", "zo")
ROLE_LABELS = {
    "flame": "vlamstatus",
    "operating_mode": "CV-modus",
    "heat_demand": "warmtevraag",
    "flow_setpoint": "gewenste aanvoer",
    "flow_temperature": "aanvoer",
    "return_temperature": "retour",
    "modulation": "modulatie",
    "outdoor_temperature": "buitentemperatuur",
    "room_temperature": "kamertemperatuur",
    "room_setpoint": "kamersetpoint",
}
_OPEN = (RecommendationStatus.OPEN, RecommendationStatus.ROLLBACK_TRIGGERED)


def _dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def _role_label(signal: str) -> str:
    role = signal.partition("@")[0]
    label = ROLE_LABELS.get(role, role.replace("_", " "))
    scope = signal.partition("@")[2].partition(":")[2]
    return f"{label} {scope}" if scope else label


def _hm(ms: int) -> str:
    return _dt(ms).astimezone(AMS).strftime("%H:%M")


def _day(ms: int) -> str:
    local = _dt(ms).astimezone(AMS)
    return f"{local.day} {MONTHS[local.month - 1]}"


def when_text(start: int, end: int, now: int) -> str:
    """'vandaag 06:00–10:10', '3 okt 06:00–10:10' or 'sinds 21 sep' (multi-day patterns)."""
    s, e, n = (_dt(x).astimezone(AMS) for x in (start, end, now))
    if e.date() != s.date() and (e - s).total_seconds() > 24 * 3600:
        return f"sinds {_day(start)}"
    prefix = "vandaag" if s.date() == n.date() else _day(start)
    return f"{prefix} {_hm(start)}–{_hm(end)}"


def period_text(f: Finding) -> str:
    s = _dt(f.period_start_ts).astimezone(AMS)
    text = (
        f"{DAY_NAMES[s.weekday()].capitalize()} {_day(f.period_start_ts)} "
        f"{_hm(f.period_start_ts)}–{_hm(f.period_end_ts)}"
    )
    return f"{text} · {f.period_note}" if f.period_note else text


def _duration_text(ms: int) -> str:
    minutes = round(ms / 60_000)
    if minutes >= 120:
        return f"{minutes // 60} u"
    return f"{minutes} min"


def _evidence(f: Finding) -> Evidence:
    sup: dict[str, Any] = f.support
    return _support_evidence(sup)


def _support_evidence(sup: dict[str, Any]) -> Evidence:
    coverage = sup.get("coverage")
    unknown_ms = int(sup.get("unknown_ms") or 0)
    relevant, pattern = sup.get("relevant_cycles"), sup.get("pattern_cycles")
    days, window = sup.get("repetition_days"), sup.get("repetition_window_days")
    missing = [str(s) for s in sup.get("missing_signals", [])]
    cov_text = "—" if coverage is None else f"{round(coverage * 100)} %"
    if unknown_ms:
        cov_text += f" · {_duration_text(unknown_ms)} onbekend"
    if pattern is not None and relevant is not None:
        cycles = f"{pattern} van {relevant} cv-cycli"
    elif relevant is not None:
        cycles = f"{relevant} cv-cycli"
    else:
        cycles = "—"
    repetition = f"{days} van laatste {window} dagen" if days is not None and window else "—"
    return Evidence(
        coverage_pct=None if coverage is None else round(coverage * 100, 1),
        unknown_s=unknown_ms // 1000,
        excluded_cycles=int(sup.get("excluded_cycles") or 0),
        relevant_cycles=relevant,
        pattern_cycles=pattern,
        repetition_days=days,
        repetition_window_days=window,
        missing_signals=missing,
        display=EvidenceDisplay(
            coverage=cov_text,
            cycles=cycles,
            repetition=repetition,
            missing_signals=", ".join(_role_label(m) for m in missing) or "Geen",
        ),
    )


def _link(e: FindingEvidence) -> EvidenceLink:
    signal = None if e.role is None else f"{e.role}@{e.scope_key or 'boiler'}"
    start = None if e.start_ts is None else _dt(e.start_ts)
    end = None if e.end_ts is None else _dt(e.end_ts)
    match e.kind:
        case EvidenceKind.CYCLE:
            return EvidenceLink(
                kind="cycle", start=_dt(e.cycle_start_ts) if e.cycle_start_ts is not None else None
            )
        case EvidenceKind.TIME_RANGE:
            return EvidenceLink(kind="time_range", start=start, end=end, label=e.summary)
        case EvidenceKind.SIGNAL:
            return EvidenceLink(kind="signal", signal=signal, start=start, end=end)
        case EvidenceKind.METRIC:
            return EvidenceLink(kind="metric", start=start, label=e.metric)
        case _:
            return EvidenceLink(kind="quality_event", start=start, signal=signal, label=e.summary)


def _recommendation(rec: Recommendation, finding: Finding) -> RecommendationOut:
    kind = (rec.success_spec or {}).get("kind")
    return RecommendationOut(
        kind=RecommendationKind(kind)
        if kind
        else (
            RecommendationKind.MEASUREMENT
            if rec.is_additional_measurement
            else RecommendationKind.CHECK
        ),
        action=rec.action,
        reason=rec.reason,
        expected_effect=rec.expected_effect,
        comfort_impact=rec.comfort_impact,
        magnitude=rec.magnitude,
        conditions=rec.conditions,
        evaluation=rec.evaluation,
        success_criterion=rec.success_criterion,
        rollback_criterion=rec.rollback_criterion,
        follow_up=rec.follow_up,
    )


class FindingsReadModel:
    """``GET /api/findings`` and ``/api/findings/{id}`` over the database."""

    def __init__(self, session: Session, clock: Callable[[], int]) -> None:
        self._session = session
        self._repo = SqlFindingRepository(session)
        self._clock = clock

    def _status(self, finding: Finding) -> Recommendation | None:
        rec = self._repo.recommendation_of(finding)
        if rec is not None:
            reopen_if_due(rec, self._clock())
        return rec

    def _require_recommendation(self, finding_id: str) -> tuple[Finding, Recommendation]:
        finding = self._repo.by_human_id(finding_id)
        if finding is None:
            raise not_found("Bevinding", finding_id)
        rec = self._status(finding)
        if rec is None:
            raise ProblemError(422, "Geen aanbeveling", "Deze bevinding heeft geen aanbeveling.")
        return finding, rec

    def set_finding_status(self, finding_id: str, body: FindingStatusUpdate) -> FindingDetail:
        finding, rec = self._require_recommendation(finding_id)
        now = self._clock()
        values = effective_values(current_revision(self._session))
        until = None
        if body.status == "postponed":
            days = values.postpone_days
            until = (
                int(body.postponed_until.timestamp() * 1000)
                if body.postponed_until is not None
                else now + days * 86_400_000
            )
            if until <= now:
                raise ProblemError(422, "Ongeldige datum", "Kies een datum in de toekomst.")
        elif body.postponed_until is not None:
            raise ProblemError(422, "Ongeldige datum", "Een uitsteldatum hoort bij uitstellen.")
        rec.status = RecommendationStatus(body.status)
        rec.postponed_until_ts = until
        rec.status_changed_at_ts = now
        rec.success_spec = {
            **(rec.success_spec or {}),
            "follow_up_baseline": follow_up_baseline(
                finding, values.min_assessment_coverage_pct / 100
            ),
        }
        if rec.status is RecommendationStatus.DONE:
            rec.outcome = RecommendationOutcome.UNDECIDED
        self._session.flush()
        return self.finding(finding_id)

    def add_note(self, finding_id: str, body: FindingNoteCreate) -> FindingNote:
        _, rec = self._require_recommendation(finding_id)
        text = body.text.strip()
        if not text:
            raise ProblemError(422, "Ongeldige notitie", "Vul een notitie in.")
        note = RecommendationNote(text=text, created_at_ts=self._clock())
        rec.notes.append(note)
        self._session.flush()
        return FindingNote(id=str(note.id), text=note.text, created_at=_dt(note.created_at_ts))

    def _summary_fields(self, f: Finding, rec: Recommendation | None) -> dict[str, Any]:
        status = rec.status if rec is not None else RecommendationStatus.OPEN
        postponed = (
            _dt(rec.postponed_until_ts) if rec is not None and rec.postponed_until_ts else None
        )
        return {
            "id": f.human_id,
            "category": Category(f.category),
            "title": f.title,
            "severity": Severity(f.severity),
            "certainty": Certainty(f.certainty),
            "relevance": [Relevance(r) for r in f.relevance],
            "lifecycle": FindingLifecycle(f.lifecycle),
            "status": status,
            "status_text": status_text(status, postponed),
            "period": TimeRange(start=_dt(f.period_start_ts), end=_dt(f.period_end_ts)),
            "when_text": when_text(f.period_start_ts, f.period_end_ts, self._clock()),
        }

    def finding_list(self) -> FindingList:
        findings = self._repo.list_findings()
        items: list[FindingSummary] = []
        open_count = 0
        for f in findings:
            rec = self._status(f)
            fields = self._summary_fields(f, rec)
            items.append(FindingSummary(**fields))
            if rec is not None and rec.status in _OPEN:
                open_count += 1
        return FindingList(items=items, open_count=open_count)

    def finding(self, human_id: str) -> FindingDetail:
        f = self._repo.by_human_id(human_id)
        if f is None:
            raise not_found("Bevinding", human_id)
        rec = self._status(f)
        links = [
            _link(e)
            for e in sorted(f.evidence, key=_link_order)
            if e.kind is not EvidenceKind.BUNDLED_CANDIDATE
        ]
        links = list({link.model_dump_json(): link for link in links}.values())
        bundled = f.support.get("bundled_candidates", [])
        has_cycles = any(link.kind == "cycle" for link in links)
        explanation: dict[str, Any] = f.priority_explanation or {}
        priority = (
            PriorityOut(
                score=f.priority_score,
                formula=str(explanation.get("formula", "")),
                factors=[PriorityFactor(**x) for x in explanation.get("factors", [])],
            )
            if explanation
            else None
        )
        return FindingDetail(
            **self._summary_fields(f, rec),
            rule=RuleRef(id=f.rule_id, version=f.rule_version),
            observation=f.observation,
            period_text=period_text(f),
            signals_text=", ".join(_role_label(s) for s in f.signals).capitalize(),
            interpretation=f.interpretation,
            hypotheses=[
                HypothesisOut(
                    number=h.ordinal,
                    name=h.name,
                    evidence_for=h.evidence_for or "",
                    missing=h.evidence_against or "",
                    distinguishing_measurement=h.distinguishing_measurement or "",
                )
                for h in f.hypotheses
            ],
            evidence=_evidence(f),
            recommendation=_recommendation(rec, f) if rec is not None else None,
            no_advice_text=f.no_advice_text,
            bundle=[
                BundledEvidence(
                    text=source["observation"],
                    source=f"{_source_name(source['rule_id'])} · v{source['rule_version']}",
                    rule=RuleRef(id=source["rule_id"], version=source["rule_version"]),
                    scope_key=source["scope_key"],
                    period=TimeRange(start=_dt(source["start_ts"]), end=_dt(source["end_ts"])),
                    certainty=source["certainty"],
                    evidence=_support_evidence(source["evidence"]),
                    interpretation=source["interpretation"],
                    signals=source["signals"],
                    hypotheses=[
                        HypothesisOut(
                            number=index,
                            name=h["name"],
                            evidence_for=h["evidence_for"],
                            missing=h["missing"],
                            distinguishing_measurement=h["distinguishing_measurement"],
                        )
                        for index, h in enumerate(source["hypotheses"], start=1)
                    ],
                    parameters=source["parameters"],
                    recommendation=None
                    if source["recommendation"] is None
                    else RecommendationOut.model_validate(
                        {
                            key: value
                            for key, value in source["recommendation"].items()
                            if key in RecommendationOut.model_fields
                        }
                    ),
                    source_finding_id=source["source_finding_id"],
                )
                for source in bundled
            ],
            superseded_by=f.support.get("superseded_by"),
            glossary=[],
            timeline_range=(
                TimeRange(
                    start=_dt(min([f.period_start_ts, *(s["start_ts"] for s in bundled)])),
                    end=_dt(max([f.period_end_ts, *(s["end_ts"] for s in bundled)])),
                )
                if has_cycles
                else None
            ),
            postponed_until=_dt(rec.postponed_until_ts)
            if rec is not None and rec.postponed_until_ts
            else None,
            notes=[]
            if rec is None
            else [
                FindingNote(id=str(note.id), text=note.text, created_at=_dt(note.created_at_ts))
                for note in sorted(rec.notes, key=lambda n: (n.created_at_ts, n.id))
            ],
            evidence_links=links,
            priority=priority,
        )


def _link_order(e: FindingEvidence) -> tuple[str, int, int]:
    return (str(e.kind), e.cycle_start_ts or e.start_ts or 0, e.id or 0)


def _source_name(rule_id: str) -> str:
    return {
        "stop-tijdens-vraag": "Stop tijdens vraag",
        "temperatuurverloop": "Temperatuurverloop",
        "hydraulisch": "Hydraulisch",
    }.get(rule_id, rule_id)
