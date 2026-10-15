"""Recommendation follow-up and evidence-based reopening (FR-27).

The caller owns the transaction. A larger pattern fraction only counts as
deterioration with at least the original coverage and relevant cycle count.
"""

from typing import Any

from cvidee.store.enums import RecommendationStatus, Severity
from cvidee.store.models import Finding, Recommendation

_SEVERITY = {Severity.INFO: 0, Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3}


def follow_up_baseline(finding: Finding, min_coverage: float = 0.8) -> dict[str, Any]:
    return {
        "min_coverage": min_coverage,
        "severity": str(finding.severity),
        "support": dict(finding.support),
        "period_end": finding.period_end_ts,
        "rule_version": finding.rule_version,
        "rule_params": dict(finding.rule_params),
    }


def reopen_if_due(recommendation: Recommendation, now: int) -> bool:
    if (
        recommendation.status is RecommendationStatus.POSTPONED
        and recommendation.postponed_until_ts is not None
        and recommendation.postponed_until_ts <= now
    ):
        reopen(recommendation, now)
        return True
    return False


def reopen(recommendation: Recommendation, now: int) -> None:
    recommendation.status = RecommendationStatus.OPEN
    recommendation.postponed_until_ts = None
    recommendation.status_changed_at_ts = now


def has_deteriorated(recommendation: Recommendation, finding: Finding) -> bool:
    baseline = (recommendation.success_spec or {}).get("follow_up_baseline")
    if not baseline or finding.period_end_ts <= baseline["period_end"]:
        return False
    if (
        finding.rule_version != baseline["rule_version"]
        or finding.rule_params != baseline["rule_params"]
    ):
        return False
    before, after = baseline["support"], finding.support
    coverage = after.get("coverage")
    if coverage is None or coverage < max(before.get("coverage") or 0, baseline["min_coverage"]):
        return False
    if _SEVERITY[finding.severity] > _SEVERITY[Severity(baseline["severity"])]:
        return True
    old_n, new_n = before.get("relevant_cycles"), after.get("relevant_cycles")
    old_bad, new_bad = before.get("pattern_cycles"), after.get("pattern_cycles")
    return bool(
        old_n
        and new_n
        and new_n >= old_n
        and old_bad is not None
        and new_bad is not None
        and new_bad / new_n > old_bad / old_n
    )
