"""Guided experiment lifecycle over manually recorded installation changes (FR-33)."""

from fastapi import APIRouter, status

from cvidee.api.routes.deps import Experiments, Limit, Offset
from cvidee.api.schemas.common import problem_responses
from cvidee.api.schemas.experiments import ExperimentCreate, ExperimentList, ExperimentOut

router = APIRouter(tags=["experiments"], responses=problem_responses(501))


@router.get("/experiments")
async def list_experiments(
    store: Experiments, limit: Limit = 50, offset: Offset = 0
) -> ExperimentList:
    return store.list(limit, offset)


@router.post(
    "/experiments",
    status_code=status.HTTP_201_CREATED,
    responses=problem_responses(404, 409, 422),
)
async def create_experiment(body: ExperimentCreate, store: Experiments) -> ExperimentOut:
    """Follow one previously recorded, single-parameter change."""
    return store.create(body)


@router.get("/experiments/{change_id}", responses=problem_responses(404))
async def get_experiment(change_id: str, store: Experiments) -> ExperimentOut:
    return store.get(change_id)


@router.post(
    "/experiments/{change_id}/end",
    responses=problem_responses(404, 409),
)
async def end_experiment(change_id: str, store: Experiments) -> ExperimentOut:
    return store.end(change_id)
