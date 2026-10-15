"""Change log and before/after evaluation (FR-29, FR-30, FR-32)."""

from fastapi import APIRouter, status

from cvidee.api.routes.deps import Changes
from cvidee.api.schemas.changes import Change, ChangeCreate, ChangeEvaluation, ChangeList
from cvidee.api.schemas.common import problem_responses

router = APIRouter(tags=["changes"], responses=problem_responses(501))


@router.get("/changes")
async def list_changes(store: Changes) -> ChangeList:
    """Recorded changes to boiler or thermostat, newest first."""
    return store.change_list()


@router.post("/changes", status_code=status.HTTP_201_CREATED, responses=problem_responses(404, 422))
async def create_change(body: ChangeCreate, store: Changes) -> Change:
    """Record a change made by the user or installer (the app never makes it)."""
    return store.create_change(body)


@router.get("/changes/{change_id}/evaluation", responses=problem_responses(404, 422))
async def get_change_evaluation(change_id: str, store: Changes) -> ChangeEvaluation:
    """Before/after comparison with comparability conditions and verdict."""
    return store.evaluation(change_id)
