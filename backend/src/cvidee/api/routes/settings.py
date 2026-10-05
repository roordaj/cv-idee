"""Analysis settings (design additions §1)."""

from fastapi import APIRouter

from cvidee.api.routes.deps import Store
from cvidee.api.schemas.common import problem_responses
from cvidee.api.schemas.settings import SettingsIn, SettingsResponse

router = APIRouter(tags=["settings"], responses=problem_responses(501))


@router.get("/settings")
async def get_settings(store: Store) -> SettingsResponse:
    """Current settings, their revision and the JSON schema to render the form."""
    return store.settings()


@router.put("/settings", responses=problem_responses(409, 422))
async def update_settings(body: SettingsIn, store: Store) -> SettingsResponse:
    """Save settings; ``409`` when saved elsewhere since ``revision`` was read."""
    return store.put_settings(body)
