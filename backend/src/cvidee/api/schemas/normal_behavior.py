"""Contracts for versioned normal-behavior model lifecycle operations."""

from enum import StrEnum

from pydantic import Field

from cvidee.api.schemas.common import ApiModel, UtcDateTime


class NormalBehaviorStatus(StrEnum):
    INSUFFICIENT_DATA = "insufficient_data"
    LEARNING = "learning"
    ACTIVE = "active"
    PAUSED = "paused"


class NormalBehaviorEventKind(StrEnum):
    CREATED = "created"
    PAUSED = "paused"
    RESUMED = "resumed"
    REFERENCE_STARTED = "reference_started"


class NormalBehaviorEventOut(ApiModel):
    kind: NormalBehaviorEventKind
    occurred_at: UtcDateTime
    reason: str | None
    effective_from: UtcDateTime | None


class NormalBehaviorModelOut(ApiModel):
    metric_name: str
    version: int = Field(ge=1)
    status: NormalBehaviorStatus
    is_current: bool
    created_at: UtcDateTime
    updated_at: UtcDateTime
    effective_from: UtcDateTime | None
    reason: str | None
    pause_reason: str | None
    paused_at: UtcDateTime | None
    observation_count: int = Field(ge=0)
    events: list[NormalBehaviorEventOut]


class NormalBehaviorModelList(ApiModel):
    items: list[NormalBehaviorModelOut]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class NormalBehaviorReason(ApiModel):
    reason: str = Field(min_length=1, max_length=500)


class NormalBehaviorNewVersion(NormalBehaviorReason):
    effective_from: UtcDateTime
