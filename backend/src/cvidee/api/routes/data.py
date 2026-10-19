"""Data quality, timeline, cycles and historical import (FR-06-13)."""

from fastapi import APIRouter

from cvidee.api.routes.deps import From, Limit, Monitoring, Offset, Timeline, To
from cvidee.api.schemas.common import problem_responses
from cvidee.api.schemas.data import (
    CycleList,
    QualityResponse,
    TimelineResponse,
)

router = APIRouter(responses=problem_responses(501, 422))


@router.get("/quality", tags=["quality"])
async def get_quality(store: Monitoring, from_: From = None, to: To = None) -> QualityResponse:
    """Coverage per signal, detected events and mode distribution over the selected range."""
    return store.quality(from_, to)


@router.get("/timeline", tags=["cycles"])
async def get_timeline(store: Timeline, from_: From = None, to: To = None) -> TimelineResponse:
    """Sampled series, modes, demand, cycles, gaps, change markers and special periods."""
    return store.timeline(from_, to)


@router.get("/cycles", tags=["cycles"])
async def list_cycles(
    store: Monitoring, from_: From = None, to: To = None, limit: Limit = 100, offset: Offset = 0
) -> CycleList:
    """Burner cycles with end reason and the KPI summary of the range (FR-12, FR-13)."""
    return store.cycles(limit, offset, from_, to)
