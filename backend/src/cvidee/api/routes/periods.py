"""Special periods (FR-10)."""

from fastapi import APIRouter, Response, status

from cvidee.api.routes.deps import Config
from cvidee.api.schemas.common import problem_responses
from cvidee.api.schemas.data import SpecialPeriod, SpecialPeriodIn, SpecialPeriodList

router = APIRouter(responses=problem_responses(501))


@router.get("/periods", tags=["periods"])
async def list_periods(store: Config) -> SpecialPeriodList:
    """Marked special periods (opstookprotocol, onderhoud, vakantie, …)."""
    return store.period_list()


@router.post(
    "/periods",
    tags=["periods"],
    status_code=status.HTTP_201_CREATED,
    responses=problem_responses(422),
)
async def create_period(body: SpecialPeriodIn, store: Config) -> SpecialPeriod:
    """Mark a special period; analyses over it are recomputed."""
    return store.create_period(body)


@router.put("/periods/{period_id}", tags=["periods"], responses=problem_responses(404, 422))
async def update_period(period_id: str, body: SpecialPeriodIn, store: Config) -> SpecialPeriod:
    """Edit a special period (design additions §3a)."""
    return store.update_period(period_id, body)


@router.delete(
    "/periods/{period_id}",
    tags=["periods"],
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=problem_responses(404, 422),
)
async def delete_period(period_id: str, store: Config) -> None:
    """Remove a special period."""
    store.delete_period(period_id)
