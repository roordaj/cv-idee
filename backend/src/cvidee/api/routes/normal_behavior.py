"""Read model lifecycle and record explicit user lifecycle actions (FR-35)."""

from fastapi import APIRouter, status

from cvidee.analysis.types import MetricName
from cvidee.api.routes.deps import Limit, NormalBehavior, Offset
from cvidee.api.schemas.common import problem_responses
from cvidee.api.schemas.normal_behavior import (
    NormalBehaviorModelList,
    NormalBehaviorModelOut,
    NormalBehaviorNewVersion,
    NormalBehaviorReason,
)

router = APIRouter(tags=["normal-behavior"], responses=problem_responses(501))


@router.get("/normal-behavior/models", response_model=NormalBehaviorModelList)
async def list_models(
    store: NormalBehavior, limit: Limit = 50, offset: Offset = 0
) -> NormalBehaviorModelList:
    return store.list(limit, offset)


@router.post(
    "/normal-behavior/models/{metric_name}/pause",
    response_model=NormalBehaviorModelOut,
    responses=problem_responses(404, 409, 422),
)
async def pause_model(
    metric_name: MetricName, body: NormalBehaviorReason, store: NormalBehavior
) -> NormalBehaviorModelOut:
    """Pause model updates without deleting its last reference."""
    return store.pause(metric_name, body)


@router.post(
    "/normal-behavior/models/{metric_name}/resume",
    response_model=NormalBehaviorModelOut,
    responses=problem_responses(404, 409),
)
async def resume_model(metric_name: MetricName, store: NormalBehavior) -> NormalBehaviorModelOut:
    return store.resume(metric_name)


@router.post(
    "/normal-behavior/models/{metric_name}/versions",
    response_model=NormalBehaviorModelOut,
    status_code=status.HTTP_201_CREATED,
    responses=problem_responses(404, 422),
)
async def start_version(
    metric_name: MetricName, body: NormalBehaviorNewVersion, store: NormalBehavior
) -> NormalBehaviorModelOut:
    """Start a new empty reference version from a user-selected date."""
    return store.start_version(metric_name, body)
