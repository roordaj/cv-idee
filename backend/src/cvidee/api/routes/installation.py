"""Installation profile (FR-02, FR-03)."""

from fastapi import APIRouter

from cvidee.api.routes.deps import Config
from cvidee.api.schemas.common import problem_responses
from cvidee.api.schemas.installation import InstallationProfile, InstallationProfileIn

router = APIRouter(responses=problem_responses(501))


@router.get("/installation", tags=["installation"])
async def get_installation(store: Config) -> InstallationProfile:
    """Boiler, circuits, rooms and specifications; unknown stays explicit."""
    return store.installation_profile()


@router.put("/installation", tags=["installation"], responses=problem_responses(409, 422))
async def update_installation(body: InstallationProfileIn, store: Config) -> InstallationProfile:
    """Replace the profile; ``409`` when ``revision`` is outdated."""
    return store.put_installation(body)
