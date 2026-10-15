"""Persistent historical import jobs (FR-06)."""

from fastapi import APIRouter, status

from cvidee.api.routes.deps import Imports
from cvidee.api.schemas.common import problem_responses
from cvidee.api.schemas.data import ImportJob, ImportList, ImportRequest

router = APIRouter(tags=["import"], responses=problem_responses(501, 422))


@router.get("/import")
async def list_imports(store: Imports) -> ImportList:
    """Imports, newest first; unknown recorder retention stays null."""
    return store.import_list()


@router.post("/import", status_code=status.HTTP_202_ACCEPTED, responses=problem_responses(409, 503))
async def start_import(body: ImportRequest, store: Imports) -> ImportJob:
    """Import recorder history, resuming an interrupted identical request when possible."""
    return store.start_import(body)


@router.get("/import/{import_id}", responses=problem_responses(404))
async def get_import(import_id: str, store: Imports) -> ImportJob:
    """Stored progress; polling does not advance the job."""
    return store.poll_import(import_id)


@router.post("/import/{import_id}/cancel", responses=problem_responses(404, 409))
async def cancel_import(import_id: str, store: Imports) -> ImportJob:
    """Cancel a job while keeping committed observations and checkpoints."""
    return store.cancel_import(import_id)
