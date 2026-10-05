"""Deterministic prioritisation of findings (FR-21/22, plan §3.6).

``score = severity * certainty * relevance * recency``; every factor is a documented weight
in ``(0, 1]`` and the explanation (stored with the finding, shown on request) lists them.
No randomness and no wall clock: ``now`` is a parameter.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from cvidee.analysis.types import HOUR_MS, TimestampMs
from cvidee.rules.base import Certainty, Relevance, Severity

__all__ = ["Priority", "prioritise", "recency_weight"]

SEVERITY_WEIGHT: dict[Severity, float] = {
    Severity.HIGH: 1.0,
    Severity.MEDIUM: 0.7,
    Severity.LOW: 0.4,
    Severity.INFO: 0.15,
}
CERTAINTY_WEIGHT: dict[Certainty, float] = {
    Certainty.INSUFFICIENT_EVIDENCE: 0.2,
    Certainty.PRELIMINARY: 0.4,
    Certainty.MODERATE: 0.6,
    Certainty.REASONABLE: 0.8,
    Certainty.HIGH: 0.9,
    Certainty.HIGH_MEASURED: 1.0,
}
RELEVANCE_WEIGHT: dict[Relevance, float] = {
    Relevance.ENERGY: 1.0,
    Relevance.COMFORT: 1.0,
    Relevance.OPERATIONAL_STABILITY: 0.8,
    Relevance.DATA_RELIABILITY: 0.7,
}
NO_RELEVANCE_WEIGHT = 0.5
RECENCY_HALF_LIFE_MS = 7 * 24 * HOUR_MS
RECENCY_FLOOR = 0.25


@dataclass(frozen=True, slots=True)
class Priority:
    score: float
    explanation: dict[str, Any]


def recency_weight(age_ms: int) -> float:
    """1.0 for fresh patterns, halving every 7 days, never below :data:`RECENCY_FLOOR`."""
    age = max(age_ms, 0)
    return float(max(RECENCY_FLOOR, 0.5 ** (age / RECENCY_HALF_LIFE_MS)))


def prioritise(
    severity: Severity,
    certainty: Certainty,
    relevance: Sequence[Relevance],
    last_pattern_ts: TimestampMs,
    now: TimestampMs,
) -> Priority:
    """Score and explanation (``factors`` in multiplication order)."""
    rel = max((RELEVANCE_WEIGHT[r] for r in relevance), default=NO_RELEVANCE_WEIGHT)
    age_ms = max(now - last_pattern_ts, 0)
    factors: list[dict[str, Any]] = [
        {"factor": "severity", "value": str(severity), "weight": SEVERITY_WEIGHT[severity]},
        {"factor": "certainty", "value": str(certainty), "weight": CERTAINTY_WEIGHT[certainty]},
        {
            "factor": "relevance",
            "value": ",".join(sorted(str(r) for r in relevance)),
            "weight": rel,
        },
        {"factor": "recency", "value": f"{age_ms // HOUR_MS} h", "weight": recency_weight(age_ms)},
    ]
    score = 1.0
    for f in factors:
        score *= float(f["weight"])
    score = round(score, 6)
    return Priority(
        score,
        {
            "formula": "severity * certainty * relevance * recency",
            "factors": factors,
            "score": score,
        },
    )
