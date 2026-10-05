"""Change log and before/after evaluation (FR-29, FR-30, FR-32)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from cvidee.api.schemas.common import ApiModel, TimeRange, UtcDateTime
from cvidee.store.enums import ChangeActor, EvaluationVerdict


class Change(ApiModel):
    id: str = Field(examples=["W-07"])
    at: UtcDateTime
    actor: ChangeActor
    parameter: str
    old_value: str
    new_value: str
    reason: str
    finding_id: str | None = Field(description="Recommendation the change follows from.")
    verdict: EvaluationVerdict
    verdict_text: str = Field(description="Short verdict label, e.g. 'Afweging · terugdraaien'.")
    rollback_advised: bool


class ChangeList(ApiModel):
    items: list[Change]


class ChangeCreate(ApiModel):
    at: UtcDateTime
    actor: ChangeActor
    parameter: str = Field(min_length=1, max_length=120)
    old_value: str = Field(max_length=60)
    new_value: str = Field(min_length=1, max_length=60)
    reason: str = Field(default="", max_length=280)
    finding_id: str | None = None


class Comparability(StrEnum):
    YES = "yes"
    LIMITED = "limited"
    NO = "no"
    EXCLUDED = "excluded"


class ConditionRow(ApiModel):
    label: str
    before: str
    after: str
    comparable: Comparability


class MetricAssessment(StrEnum):
    BETTER = "better"
    WORSE = "worse"
    NEUTRAL = "neutral"


class MetricComparison(ApiModel):
    label: str
    note: str
    before: str
    after: str
    before_bar_pct: float = Field(ge=0, le=100)
    after_bar_pct: float = Field(ge=0, le=100)
    effect_text: str
    assessment: MetricAssessment


class ChangeEvaluation(ApiModel):
    change_id: str
    verdict: EvaluationVerdict
    verdict_text: str
    summary: str
    before: TimeRange | None
    after: TimeRange | None
    before_text: str
    after_text: str
    conditions: list[ConditionRow]
    metrics: list[MetricComparison]
    result_expected_at: UtcDateTime | None = Field(
        default=None, description="While pending: when the observation period is complete."
    )
