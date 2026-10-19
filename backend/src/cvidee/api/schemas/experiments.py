"""Request and response schemas for guided experiment lifecycles (FR-33)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from cvidee.api.schemas.changes import Change, ChangeEvaluation
from cvidee.api.schemas.common import ApiModel, UtcDateTime


class ExperimentStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    ENDED = "ended"


class ExperimentCreate(ApiModel):
    """Start following one existing single-parameter change."""

    change_id: str = Field(min_length=1, max_length=16, examples=["W-07"])


class ExperimentOut(ApiModel):
    """Experiment lifecycle and the existing change evaluation it reuses."""

    change_id: str
    status: ExperimentStatus
    status_text: str
    change: Change
    evaluation: ChangeEvaluation | None
    created_at: UtcDateTime
    updated_at: UtcDateTime
    last_evaluated_at: UtcDateTime | None
    completed_at: UtcDateTime | None
    ended_at: UtcDateTime | None


class ExperimentList(ApiModel):
    items: list[ExperimentOut]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
