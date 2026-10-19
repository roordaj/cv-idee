"""Daily and weekly report snapshots (FR-40)."""

from enum import StrEnum
from typing import Any

from pydantic import Field

from cvidee.api.schemas.common import ApiModel, TimeRange, UtcDateTime
from cvidee.api.schemas.data import Cycle, CycleSummary, QualityResponse
from cvidee.api.schemas.findings import FindingSummary
from cvidee.store.enums import EvaluationVerdict, RecommendationStatus


class ReportPeriodKind(StrEnum):
    DAY = "day"
    WEEK = "week"


class ReportAdvice(ApiModel):
    finding_id: str
    title: str
    status: RecommendationStatus
    action: str
    missing_signals: list[str]
    success_criterion: str | None
    rollback_criterion: str | None


class ReportStatusChange(ApiModel):
    at: UtcDateTime
    finding_id: str
    title: str
    status: RecommendationStatus


class ReportChange(ApiModel):
    change_id: str
    at: UtcDateTime
    parameter: str
    old_value: str
    new_value: str
    reason: str
    evaluation: "ReportChangeEvaluation | None"


class ReportChangeEvaluation(ApiModel):
    verdict: EvaluationVerdict
    summary: str | None
    reference: TimeRange
    observation: TimeRange
    comparability: list[dict[str, Any]]
    metrics: list[dict[str, Any]]


class ReportSnapshot(ApiModel):
    kind: ReportPeriodKind
    period: TimeRange
    generated_at: UtcDateTime
    quality: QualityResponse
    cycle_summary: CycleSummary
    cycles: list[Cycle]
    findings: list[FindingSummary]
    open_advice: list[ReportAdvice]
    status_changes: list[ReportStatusChange]
    changes: list[ReportChange]
    has_more_cycles: bool = Field(description="True when more than 500 cycles fall in the period.")
