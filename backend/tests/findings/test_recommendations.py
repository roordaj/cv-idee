"""Postponement only ends early with new, sufficiently supported deterioration."""

from copy import deepcopy

import pytest

from cvidee.findings.recommendations import follow_up_baseline, has_deteriorated
from cvidee.store.enums import Severity
from cvidee.store.models import Finding, Recommendation


@pytest.mark.parametrize(
    ("severity", "pattern", "coverage", "cycles", "new_period", "version", "expected"),
    [
        (Severity.MEDIUM, 7, 0.95, 10, True, "1", True),
        (Severity.HIGH, 6, 0.95, 10, True, "1", True),
        (Severity.MEDIUM, 6, 0.95, 10, True, "1", False),
        (Severity.MEDIUM, 7, 0.5, 10, True, "1", False),
        (Severity.MEDIUM, 5, 0.95, 5, True, "1", False),
        (Severity.HIGH, 8, 0.95, 10, False, "1", False),
        (Severity.HIGH, 8, 0.95, 10, True, "2", False),
    ],
)
def test_deterioration_requires_new_comparable_evidence(
    severity: Severity,
    pattern: int,
    coverage: float,
    cycles: int,
    new_period: bool,
    version: str,
    expected: bool,
) -> None:
    finding = Finding(
        severity=Severity.MEDIUM,
        period_end_ts=100,
        support={"coverage": 0.95, "relevant_cycles": 10, "pattern_cycles": 6},
        rule_version="1",
        rule_params={"threshold": 3},
    )
    baseline = deepcopy(follow_up_baseline(finding))
    rec = Recommendation(success_spec={"follow_up_baseline": baseline})
    finding.severity = severity
    finding.period_end_ts = 101 if new_period else 100
    finding.rule_version = version
    finding.support = {"coverage": coverage, "relevant_cycles": cycles, "pattern_cycles": pattern}
    assert has_deteriorated(rec, finding) is expected
    assert rec.success_spec == {"follow_up_baseline": baseline}


def test_configured_coverage_threshold_is_captured_at_postponement() -> None:
    finding = Finding(
        severity=Severity.MEDIUM,
        period_end_ts=100,
        support={"coverage": 0.6},
        rule_version="1",
        rule_params={},
    )
    rec = Recommendation(success_spec={"follow_up_baseline": follow_up_baseline(finding, 0.5)})
    finding.period_end_ts = 101
    finding.severity = Severity.HIGH
    assert has_deteriorated(rec, finding)
    finding.rule_params = {"changed": True}
    assert not has_deteriorated(rec, finding)
