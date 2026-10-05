"""Installation profile and special periods (FR-02, FR-03, FR-05, FR-10)."""

from fastapi import APIRouter, Response, status

from cvidee.api.routes.deps import Store
from cvidee.api.schemas.common import problem_responses
from cvidee.api.schemas.data import SpecialPeriod, SpecialPeriodIn, SpecialPeriodList
from cvidee.api.schemas.installation import InstallationProfile, InstallationProfileIn

router = APIRouter(responses=problem_responses(501))


@router.get("/installation", tags=["installation"])
async def get_installation(store: Store) -> InstallationProfile:
    """Boiler, circuits, rooms and specifications; unknown stays explicit."""
    return store.installation


@router.put("/installation", tags=["installation"], responses=problem_responses(409, 422))
async def update_installation(body: InstallationProfileIn, store: Store) -> InstallationProfile:
    """Replace the profile; ``409`` when ``revision`` is outdated."""
    return store.put_installation(body)


@router.get("/periods", tags=["periods"])
async def list_periods(store: Store) -> SpecialPeriodList:
    """Marked special periods (opstookprotocol, onderhoud, vakantie, …)."""
    return store.period_list()


@router.post(
    "/periods",
    tags=["periods"],
    status_code=status.HTTP_201_CREATED,
    responses=problem_responses(422),
)
async def create_period(body: SpecialPeriodIn, store: Store) -> SpecialPeriod:
    """Mark a special period; analyses over it are recomputed."""
    return store.create_period(body)


@router.put("/periods/{period_id}", tags=["periods"], responses=problem_responses(404, 422))
async def update_period(period_id: str, body: SpecialPeriodIn, store: Store) -> SpecialPeriod:
    """Edit a special period (design additions §3a)."""
    return store.update_period(period_id, body)


@router.delete(
    "/periods/{period_id}",
    tags=["periods"],
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=problem_responses(404, 422),
)
async def delete_period(period_id: str, store: Store) -> None:
    """Remove a special period."""
    store.delete_period(period_id)
