"""Findings engine: candidates → persistent findings with lifecycle (FR-21, FR-22, FR-39).

Rules emit :class:`~cvidee.rules.base.FindingCandidate` s; this module

* **dedupes** them on ``(rule_id, scope_key)``: an active finding is updated (``last_seen``,
  support, evidence, priority), never duplicated per cycle; a returning problem after
  resolution becomes a *new* finding with a new human id (``B-001``, ``B-002`` …);
* gives findings a **lifecycle** ``active → resolved``. A finding that is no longer emitted
  is closed only when

  - ``recovered``: the pattern was absent for :attr:`RecoverySettings.days_without_pattern`
    days, the core signals were known for at least :attr:`RecoverySettings.min_coverage` of
    that window and the weather was comparable to that during the pattern. A data gap (rule
    not evaluable, or signals unknown) **never** counts as recovery;
  - ``settings_changed`` / ``rule_changed``: the rule parameters or version differ from those
    the finding was created under and the rule, evaluated on sufficient data, no longer emits
    it (no recovery was observed, so the reason is not ``recovered``);

* **prioritises** deterministically (:mod:`cvidee.findings.priority`).

Bundling of supporting candidates (FR-26) and advice follow-up (FR-27) are #35/#36.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from cvidee.analysis.types import (
    HOUR_MS,
    Role,
    Scope,
    SignalRef,
    TimeRange,
)
from cvidee.findings.priority import prioritise
from cvidee.findings.repository import SqlFindingRepository
from cvidee.rules.base import (
    CycleRef,
    EvidenceRef,
    EvidenceSummary,
    FindingCandidate,
    MetricRef,
    PeriodRef,
    QualityEventRef,
    RecommendationDraft,
    RecommendationKind,
    RuleContext,
    RuleParams,
    SignalEvidence,
    signal_ref,
)
from cvidee.rules.registry import RuleOutcome, RuleRegistry
from cvidee.store.derived import parse_signal_ref
from cvidee.store.enums import (
    EvidenceKind,
    FindingLifecycle,
    RecommendationOutcome,
    RecommendationStatus,
    ResolutionReason,
)
from cvidee.store.models import Finding, FindingEvidence, FindingHypothesis, Recommendation

__all__ = [
    "NOT_SUBSTANTIATED",
    "EngineResult",
    "FindingsEngine",
    "RecoverySettings",
    "scope_text",
    "support_of",
]

logger = logging.getLogger(__name__)

NOT_SUBSTANTIATED = "Niet te onderbouwen met huidige gegevens — geen getal genoemd."
DAY_MS = 24 * HOUR_MS


@dataclass(frozen=True, slots=True)
class RecoverySettings:
    """Herstelcriterium (design additions §1.5, group ``recovery``; adjustable)."""

    days_without_pattern: int = 3
    """Days the pattern must be absent before a finding counts as recovered."""
    min_coverage: float = 0.8
    """Minimum known fraction of the core signals over the pattern-free window."""
    require_comparable_weather: bool = True
    max_outdoor_delta_k: float = 5.0
    """Comparable weather: mean outdoor temperatures at most this many K apart."""

    def __post_init__(self) -> None:
        if self.days_without_pattern < 1:
            raise ValueError("RecoverySettings: days_without_pattern must be >= 1")
        if not 0.0 < self.min_coverage <= 1.0:
            raise ValueError("RecoverySettings: min_coverage must be within (0, 1]")
        if self.max_outdoor_delta_k < 0:
            raise ValueError("RecoverySettings: max_outdoor_delta_k must be >= 0")


@dataclass(slots=True)
class EngineResult:
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    resolved: dict[str, ResolutionReason] = field(default_factory=dict)

    def merge(self, other: EngineResult) -> None:
        self.created += other.created
        self.updated += other.updated
        self.resolved |= other.resolved


ParamsFor = Callable[[str], RuleParams]


class FindingsEngine:
    """Evaluates a registry and persists the outcome through a :class:`SqlFindingRepository`."""

    def __init__(
        self,
        registry: RuleRegistry,
        repo: SqlFindingRepository,
        recovery: RecoverySettings | None = None,
        params_for: ParamsFor | None = None,
    ) -> None:
        self._registry = registry
        self._repo = repo
        self.recovery = recovery if recovery is not None else RecoverySettings()
        self._params_for = params_for or registry.default_params

    def evaluate(self, ctx: RuleContext, run_id: int | None = None) -> EngineResult:
        """Evaluate every registered rule for ``ctx`` and apply the outcomes."""
        result = EngineResult()
        for rule in self._registry:
            params = self._params_for(rule.id)
            outcome = self._registry.evaluate(rule.id, ctx, params)
            result.merge(self.apply(outcome, ctx, run_id))
        return result

    def apply(self, outcome: RuleOutcome, ctx: RuleContext, run_id: int | None) -> EngineResult:
        """Upsert the candidates of one rule and close findings that qualify."""
        result = EngineResult()
        rule_id = outcome.snapshot.rule_id
        seen: set[str] = set()
        for candidate in outcome.candidates:
            seen.add(candidate.scope_key)
            existing = self._repo.active_by_key(rule_id, candidate.scope_key)
            if existing is None:
                finding = self._create(outcome, candidate, ctx, run_id)
                result.created.append(finding.human_id)
            else:
                self._update(existing, outcome, candidate, ctx, run_id)
                result.updated.append(existing.human_id)
        if not outcome.evaluated:
            return result  # rule not applicable/evaluable: no statement about the problem
        for finding in self._repo.active_for_rule(rule_id):
            if finding.scope_key in seen:
                continue
            reason = self._closing_reason(finding, outcome, ctx)
            if reason is not None:
                finding.lifecycle = FindingLifecycle.RESOLVED
                finding.resolution_reason = reason
                finding.resolved_at_ts = ctx.now
                finding.last_run_id = run_id
                result.resolved[finding.human_id] = reason
        return result

    # ------------------------------------------------------------------ upsert

    def _create(
        self, outcome: RuleOutcome, c: FindingCandidate, ctx: RuleContext, run_id: int | None
    ) -> Finding:
        finding = Finding(
            rule_id=outcome.snapshot.rule_id,
            scope_key=c.scope_key,
            lifecycle=FindingLifecycle.ACTIVE,
            first_seen_ts=ctx.now,
            last_seen_ts=ctx.now,
        )
        self._fill(finding, outcome, c, ctx, run_id)
        self._repo.add(finding)
        self._sync_recommendation(finding, outcome, c.recommendation, ctx)
        return finding

    def _update(
        self,
        finding: Finding,
        outcome: RuleOutcome,
        c: FindingCandidate,
        ctx: RuleContext,
        run_id: int | None,
    ) -> None:
        finding.last_seen_ts = ctx.now
        self._fill(finding, outcome, c, ctx, run_id)
        self._sync_recommendation(finding, outcome, c.recommendation, ctx)

    def _fill(
        self,
        f: Finding,
        outcome: RuleOutcome,
        c: FindingCandidate,
        ctx: RuleContext,
        run: int | None,
    ) -> None:
        f.rule_version = outcome.snapshot.version
        f.rule_params = outcome.snapshot.params
        f.category = str(c.category)
        f.title = c.title
        f.severity = c.severity
        f.certainty = c.certainty
        f.relevance = [str(r) for r in c.relevance]
        f.observation = c.observation
        f.interpretation = c.interpretation
        f.no_advice_text = c.no_advice_reason or None
        f.period_start_ts = c.period.start
        f.period_end_ts = c.period.end
        f.period_note = _period_note(c.evidence)
        f.signals = [str(s) for s in c.signals]
        f.support = support_of(c.evidence)
        priority = prioritise(c.severity, c.certainty, c.relevance, c.period.end, ctx.now)
        f.priority_score = priority.score
        f.priority_explanation = priority.explanation
        f.last_run_id = run
        f.hypotheses.clear()
        f.evidence.clear()
        for number, h in enumerate(c.hypotheses, start=1):
            f.hypotheses.append(
                FindingHypothesis(
                    ordinal=number,
                    name=h.name,
                    evidence_for=h.evidence_for,
                    evidence_against=h.missing,
                    distinguishing_measurement=h.distinguishing_measurement,
                )
            )
        f.evidence.extend(_evidence_rows(c))

    def _sync_recommendation(
        self,
        finding: Finding,
        outcome: RuleOutcome,
        draft: RecommendationDraft | None,
        ctx: RuleContext,
    ) -> None:
        if draft is None:
            return
        rec = self._repo.recommendation_of(finding)
        if rec is None:
            rec = Recommendation(
                finding_id=finding.id,
                status=RecommendationStatus.OPEN,
                outcome=RecommendationOutcome.PENDING,
                created_at_ts=ctx.now,
                status_changed_at_ts=ctx.now,
            )
        elif rec.status is not RecommendationStatus.OPEN:
            return  # follow-up in progress (FR-27, #36): the advice is not rewritten
        rec.rule_id = outcome.snapshot.rule_id
        rec.rule_version = outcome.snapshot.version
        rec.is_additional_measurement = draft.kind is RecommendationKind.MEASUREMENT
        rec.action = draft.action
        rec.reason = draft.reason
        rec.expected_effect = draft.expected_effect
        rec.comfort_impact = draft.comfort_impact
        rec.magnitude = draft.magnitude or NOT_SUBSTANTIATED
        rec.magnitude_substantiated = draft.magnitude is not None
        rec.conditions = draft.conditions
        rec.evaluation = draft.evaluation
        rec.success_criterion = draft.success_criterion
        rec.rollback_criterion = draft.rollback_criterion
        rec.follow_up = draft.follow_up
        rec.success_spec = {"kind": str(draft.kind)}
        if rec.id is None:
            self._repo.add_recommendation(rec)

    # ---------------------------------------------------------------- lifecycle

    def _closing_reason(
        self, finding: Finding, outcome: RuleOutcome, ctx: RuleContext
    ) -> ResolutionReason | None:
        window = _clean_window(finding, ctx)
        signals = _signals_of(finding)
        changed_version = finding.rule_version != outcome.snapshot.version
        changed_params = finding.rule_params != outcome.snapshot.params
        if changed_version or changed_params:
            # Evaluated on sufficient data (not merely a gap) → a settings/rule change.
            if self._data_ok(signals, ctx, ctx.period):
                return (
                    ResolutionReason.RULE_CHANGED
                    if changed_version
                    else ResolutionReason.SETTINGS_CHANGED
                )
            return None
        if window is None or window.duration_ms < self.recovery.days_without_pattern * DAY_MS:
            return None
        if not self._data_ok(signals, ctx, window):
            return None  # data gap: never recovery
        if self.recovery.require_comparable_weather and not self._weather_comparable(
            finding, window, ctx
        ):
            return None
        return ResolutionReason.RECOVERED

    def _data_ok(self, signals: list[SignalRef], ctx: RuleContext, window: TimeRange) -> bool:
        if not signals:
            return False
        return all(
            (cov := known_fraction(ctx, s, window)) is not None
            and cov >= self.recovery.min_coverage
            for s in signals
        )

    def _weather_comparable(self, finding: Finding, clean: TimeRange, ctx: RuleContext) -> bool:
        outdoor = signal_ref(Role.OUTDOOR_TEMPERATURE)
        pattern = TimeRange(finding.period_start_ts, finding.period_end_ts)
        before = mean_value(ctx, outdoor, pattern)
        after = mean_value(ctx, outdoor, clean)
        if before is None or after is None:
            return False
        return abs(before - after) <= self.recovery.max_outdoor_delta_k


# ------------------------------------------------------------------------ helpers


def _clean_window(finding: Finding, ctx: RuleContext) -> TimeRange | None:
    """The pattern-free window: from the last time the pattern was seen to ``now``, within
    the evaluation period."""
    start = max(finding.period_end_ts, ctx.period.start)
    end = min(ctx.now, ctx.period.end)
    return TimeRange(start, end) if start < end else None


def _signals_of(finding: Finding) -> list[SignalRef]:
    out: list[SignalRef] = []
    for text in finding.signals:
        try:
            out.append(parse_signal_ref(str(text)))
        except ValueError:
            logger.warning("finding %s: unknown signal %r", finding.human_id, text)
    return out


def known_fraction(ctx: RuleContext, signal: SignalRef, window: TimeRange) -> float | None:
    """Fraction of ``window`` with a known value for ``signal``; ``None`` if not mapped."""
    timeline = ctx.timeline(signal, window)
    if timeline is None:
        return None
    known = 0
    for interval in timeline.values:
        lo, hi = max(interval.start, window.start), min(interval.end, window.end)
        known += max(hi - lo, 0)
    return known / window.duration_ms


def mean_value(ctx: RuleContext, signal: SignalRef, window: TimeRange) -> float | None:
    """Time-weighted mean of a numeric signal over its known time in ``window``."""
    timeline = ctx.timeline(signal, window)
    if timeline is None:
        return None
    total = 0.0
    weight = 0
    for interval in timeline.values:
        value = interval.value
        if isinstance(value, bool) or not isinstance(value, int | float):
            continue
        lo, hi = max(interval.start, window.start), min(interval.end, window.end)
        if hi > lo:
            total += float(value) * (hi - lo)
            weight += hi - lo
    return total / weight if weight else None


def support_of(e: EvidenceSummary) -> dict[str, Any]:
    """Onderbouwing as stored in ``findings.support`` (FR-22)."""
    return {
        "coverage": e.coverage,
        "unknown_ms": e.unknown_ms,
        "excluded_ms": e.excluded_ms,
        "excluded_cycles": e.excluded_cycles,
        "relevant_cycles": e.relevant_cycles,
        "pattern_cycles": e.pattern_cycles,
        "observed_hours": e.observed_hours,
        "repetition_days": e.repetition_days,
        "repetition_window_days": e.repetition_window_days,
        "missing_signals": [str(s) for s in e.missing_signals],
    }


def scope_text(scope: Scope) -> str:
    """``'boiler'`` or ``'room:slaapkamer'`` (inverse of the scope part of ``str(SignalRef)``)."""
    return str(scope.kind) if scope.key is None else f"{scope.kind}:{scope.key}"


def _period_note(e: EvidenceSummary) -> str | None:
    if e.excluded_cycles:
        return f"{e.excluded_cycles} cyclus uitgesloten"
    return None


def _evidence_rows(c: FindingCandidate) -> list[FindingEvidence]:
    rows = [_evidence_row(ref) for ref in c.refs]
    rows += [
        FindingEvidence(kind=EvidenceKind.SIGNAL, role=str(s.role), scope_key=scope_text(s.scope))
        for s in c.signals
        if not any(isinstance(r, SignalEvidence) and r.signal == s for r in c.refs)
    ]
    if not any(isinstance(r, PeriodRef) for r in c.refs):
        rows.append(
            FindingEvidence(
                kind=EvidenceKind.TIME_RANGE, start_ts=c.period.start, end_ts=c.period.end
            )
        )
    return rows


def _evidence_row(ref: EvidenceRef) -> FindingEvidence:
    match ref:
        case CycleRef(cycle_start=start):
            return FindingEvidence(kind=EvidenceKind.CYCLE, cycle_start_ts=start)
        case PeriodRef(range=rng, label=label):
            return FindingEvidence(
                kind=EvidenceKind.TIME_RANGE,
                start_ts=rng.start,
                end_ts=rng.end,
                summary=label or None,
            )
        case SignalEvidence(signal=sig, range=rng):
            return FindingEvidence(
                kind=EvidenceKind.SIGNAL,
                role=str(sig.role),
                scope_key=scope_text(sig.scope),
                start_ts=rng.start if rng else None,
                end_ts=rng.end if rng else None,
            )
        case MetricRef(name=name, window_start=start, mode=mode):
            return FindingEvidence(
                kind=EvidenceKind.METRIC,
                metric=str(name),
                start_ts=start,
                summary=str(mode) if mode is not None else None,
            )
        case QualityEventRef(kind=kind, start=start, signal=sig):
            return FindingEvidence(
                kind=EvidenceKind.QUALITY_EVENT,
                start_ts=start,
                role=str(sig.role) if sig else None,
                scope_key=scope_text(sig.scope) if sig else None,
                summary=str(kind),
            )
    raise TypeError(f"unknown evidence reference {ref!r}")
