"""``/api/status`` and ``/api/overview``."""

from fastapi import APIRouter

from cvidee.api.routes.deps import Store
from cvidee.api.schemas.common import problem_responses
from cvidee.api.schemas.system import OverviewResponse, StatusResponse

router = APIRouter(tags=["status"], responses=problem_responses(501))


@router.get("/status")
async def get_status(store: Store) -> StatusResponse:
    """Operating mode, live status, today's coverage, setup, HA and MQTT state."""
    return store.status()


@router.get("/overview")
async def get_overview(store: Store) -> OverviewResponse:
    """Everything the Overzicht screen shows, including the assessment (FR-36, §5c)."""
    return store.overview()
