"""Analysis settings (design additions §1)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from cvidee.api.routes.deps import get_stub_store_problem
from cvidee.api.schemas.common import problem_responses
from cvidee.api.schemas.settings import SettingsHistory, SettingsIn, SettingsResponse
from cvidee.api.stubs.store import StubStore
from cvidee.settings.backend import SettingsBackend

router = APIRouter(tags=["settings"], responses=problem_responses(501))


def get_settings_backend(request: Request) -> SettingsBackend | StubStore:
    stub = getattr(request.app.state, "stub_store", None)
    if isinstance(stub, StubStore):
        return stub
    sessions = getattr(request.app.state, "session_factory", None)
    if sessions is None:
        raise get_stub_store_problem()
    runner = getattr(request.app.state, "runner", None)
    registry = None if runner is None else runner.registry
    return SettingsBackend(sessions, runner, registry)


Settings = Annotated[SettingsBackend | StubStore, Depends(get_settings_backend)]


@router.get("/settings")
async def get_settings(store: Settings) -> SettingsResponse:
    """Current settings, their revision and the JSON schema to render the form."""
    return store.settings()


@router.put("/settings", responses=problem_responses(409, 422))
async def update_settings(body: SettingsIn, store: Settings) -> SettingsResponse:
    """Save settings; ``409`` when saved elsewhere since ``revision`` was read."""
    return store.put_settings(body)


@router.get("/settings/history")
async def settings_history(store: Settings) -> SettingsHistory:
    """Immutable settings revisions, newest first, with the supplied actor and note."""
    return SettingsHistory(items=[]) if isinstance(store, StubStore) else store.settings_history()
