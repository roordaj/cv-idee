"""Findings, their follow-up status and notes, and recommendation history."""

from fastapi import APIRouter, status

from cvidee.api.routes.deps import Limit, Offset, Store
from cvidee.api.schemas.common import Page, problem_responses
from cvidee.api.schemas.findings import (
    FindingDetail,
    FindingList,
    FindingNote,
    FindingNoteCreate,
    FindingStatusUpdate,
    HistoryEntry,
)

router = APIRouter(responses=problem_responses(501))


@router.get("/findings", tags=["findings"])
async def list_findings(store: Store) -> FindingList:
    """Active findings (FR-21-28)."""
    return store.finding_list()


@router.get("/findings/{finding_id}", tags=["findings"], responses=problem_responses(404, 422))
async def get_finding(finding_id: str, store: Store) -> FindingDetail:
    """Observation, interpretation, evidence, hypotheses and advice (FR-37)."""
    return store.finding(finding_id)


@router.post(
    "/findings/{finding_id}/status", tags=["findings"], responses=problem_responses(404, 422)
)
async def set_finding_status(
    finding_id: str, body: FindingStatusUpdate, store: Store
) -> FindingDetail:
    """Accept, postpone, mark done or reject the recommendation (FR-27)."""
    return store.set_finding_status(finding_id, body)


@router.post(
    "/findings/{finding_id}/notes",
    tags=["findings"],
    status_code=status.HTTP_201_CREATED,
    responses=problem_responses(404, 422),
)
async def add_finding_note(finding_id: str, body: FindingNoteCreate, store: Store) -> FindingNote:
    """Add a personal note to a finding."""
    return store.add_note(finding_id, body)


@router.get("/history", tags=["history"], responses=problem_responses(422))
async def list_history(store: Store, limit: Limit = 50, offset: Offset = 0) -> Page[HistoryEntry]:
    """Recommendation history as recorded at the time (FR-41), newest first."""
    return store.history(limit, offset)
