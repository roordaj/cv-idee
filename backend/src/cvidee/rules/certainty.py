"""Certainty derivation from the criteria template (ADR-004 §5, FR-22, FR-28).

Pure and deterministic: the same :class:`~cvidee.rules.base.EvidenceSummary` and
:class:`~cvidee.rules.base.CertaintyCriteria` always give the same category and the same
explanation. The explanation is structured (reason codes); the UI renders it in Dutch.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from cvidee.rules.base import Certainty, CertaintyCriteria, EvidenceSummary, Thresholds


class CertaintyReason(StrEnum):
    BELOW_MIN_COVERAGE = "below_min_coverage"
    BELOW_MIN_CYCLES = "below_min_cycles"
    BELOW_MIN_HOURS = "below_min_hours"
    BELOW_MIN_REPETITION = "below_min_repetition"
    NOT_STRUCTURAL = "not_structural"
    """Pattern seen on fewer days than the structural repetition → preliminary."""
    REASONABLE_MET = "reasonable_met"
    HIGH_MET = "high_met"
    MEASURED = "measured"
    LOWERED_FOR_MISSING_SIGNALS = "lowered_for_missing_signals"
    CAPPED = "capped"


@dataclass(frozen=True, slots=True)
class CertaintyAssessment:
    certainty: Certainty
    reasons: tuple[CertaintyReason, ...]


def unmet(evidence: EvidenceSummary, thresholds: Thresholds) -> tuple[CertaintyReason, ...]:
    """Thresholds of ``thresholds`` that ``evidence`` does not meet. A threshold whose
    evidence value is unknown (``None``) counts as not met: unknown is never 'enough'."""
    reasons: list[CertaintyReason] = []
    if thresholds.coverage is not None and evidence.coverage < thresholds.coverage:
        reasons.append(CertaintyReason.BELOW_MIN_COVERAGE)
    if thresholds.relevant_cycles is not None and (
        evidence.relevant_cycles is None or evidence.relevant_cycles < thresholds.relevant_cycles
    ):
        reasons.append(CertaintyReason.BELOW_MIN_CYCLES)
    if thresholds.observed_hours is not None and (
        evidence.observed_hours is None or evidence.observed_hours < thresholds.observed_hours
    ):
        reasons.append(CertaintyReason.BELOW_MIN_HOURS)
    if thresholds.repetition_days is not None and (
        evidence.repetition_days is None or evidence.repetition_days < thresholds.repetition_days
    ):
        reasons.append(CertaintyReason.BELOW_MIN_REPETITION)
    return tuple(reasons)


def derive_certainty(
    evidence: EvidenceSummary, criteria: CertaintyCriteria, *, measured: bool = False
) -> CertaintyAssessment:
    """Certainty category for one candidate (ADR-004 §5.2).

    1. Any ``minimum`` threshold unmet → ``INSUFFICIENT_EVIDENCE``.
    2. Pattern on fewer than ``structural_repetition_days`` days → ``PRELIMINARY``.
    3. ``MODERATE``; ``reasonable`` met → ``REASONABLE``; ``high`` met as well → ``HIGH``;
       ``measured`` and ``allow_measured`` and ``HIGH`` → ``HIGH_MEASURED``.
    4. Missing optional signals → one step lower (once, never below ``MODERATE``).
    5. Cap at ``max_certainty``.

    ``measured`` is set by the rule for a candidate that only reports directly measured
    facts without interpretation (e.g. a connection outage the app observed itself).
    """
    failed = unmet(evidence, criteria.minimum)
    if failed:
        return CertaintyAssessment(Certainty.INSUFFICIENT_EVIDENCE, failed)

    reasons: list[CertaintyReason] = []
    if criteria.structural_repetition_days is not None and (
        evidence.repetition_days is None
        or evidence.repetition_days < criteria.structural_repetition_days
    ):
        level = Certainty.PRELIMINARY.at_most(criteria.max_certainty)
        return CertaintyAssessment(level, (CertaintyReason.NOT_STRUCTURAL,))

    level = Certainty.MODERATE
    if criteria.reasonable is not None and not unmet(evidence, criteria.reasonable):
        level = Certainty.REASONABLE
        reasons.append(CertaintyReason.REASONABLE_MET)
        if criteria.high is not None and not unmet(evidence, criteria.high):
            level = Certainty.HIGH
            reasons.append(CertaintyReason.HIGH_MET)
            if measured and criteria.allow_measured:
                level = Certainty.HIGH_MEASURED
                reasons.append(CertaintyReason.MEASURED)

    if criteria.lower_for_missing_signals and evidence.missing_signals:
        lowered = level.lowered(1, floor=Certainty.MODERATE)
        if lowered is not level:
            level = lowered
            reasons.append(CertaintyReason.LOWERED_FOR_MISSING_SIGNALS)

    capped = level.at_most(criteria.max_certainty)
    if capped is not level:
        level = capped
        reasons.append(CertaintyReason.CAPPED)
    return CertaintyAssessment(level, tuple(reasons))
