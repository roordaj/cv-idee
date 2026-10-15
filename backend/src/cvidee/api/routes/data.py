"""Data quality, timeline, cycles and historical import (FR-06-13)."""

from fastapi import APIRouter, status

from cvidee.api.routes.deps import From, Limit, Offset, Store, Timeline, To
from cvidee.api.schemas.common import problem_responses
from cvidee.api.schemas.data import (
    CycleList,
    ImportJob,
    ImportList,
    ImportRequest,
    QualityResponse,
    TimelineResponse,
)

router = APIRouter(responses=problem_responses(501, 422))


@router.get("/quality", tags=["quality"])
async def get_quality(store: Store, from_: From = None, to: To = None) -> QualityResponse:
    """Coverage per signal, detected events and mode distribution (stub: fixed range)."""
    del from_, to
    return store.quality()


@router.get("/timeline", tags=["cycles"])
async def get_timeline(store: Timeline, from_: From = None, to: To = None) -> TimelineResponse:
    """Sampled series, modes, demand, cycles, gaps, change markers and special periods."""
    return store.timeline(from_, to)


@router.get("/cycles", tags=["cycles"])
async def list_cycles(
    store: Store, from_: From = None, to: To = None, limit: Limit = 100, offset: Offset = 0
) -> CycleList:
    """Burner cycles with end reason and the KPI summary of the range (FR-12, FR-13)."""
    del from_, to
    return store.cycles(limit, offset)


@router.get("/import", tags=["import"])
async def list_imports(store: Store) -> ImportList:
    """Imports, newest first, plus how far back the HA recorder goes."""
    return store.import_list()


@router.post(
    "/import",
    tags=["import"],
    status_code=status.HTTP_202_ACCEPTED,
    responses=problem_responses(409),
)
async def start_import(body: ImportRequest, store: Store) -> ImportJob:
    """Start a historical import (max one at a time, ``409`` otherwise)."""
    return store.start_import(body)


@router.get("/import/{import_id}", tags=["import"], responses=problem_responses(404))
async def get_import(import_id: str, store: Store) -> ImportJob:
    """Import progress; poll every 2 s while active."""
    return store.poll_import(import_id)


@router.post("/import/{import_id}/cancel", tags=["import"], responses=problem_responses(404, 409))
async def cancel_import(import_id: str, store: Store) -> ImportJob:
    """Stop a running import; what was fetched is kept."""
    return store.cancel_import(import_id)
