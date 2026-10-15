"""Immutable advice snapshots as recorded at the time (FR-41)."""

from fastapi import APIRouter

from cvidee.api.routes.deps import History, Limit, Offset
from cvidee.api.schemas.common import Page, problem_responses
from cvidee.api.schemas.findings import HistoryEntry

router = APIRouter()


@router.get("/history", tags=["history"], responses=problem_responses(422, 501))
async def list_history(store: History, limit: Limit = 50, offset: Offset = 0) -> Page[HistoryEntry]:
    """Advice history, newest first, with original parameters and subsequent rule changes."""
    return store.history(limit, offset)
