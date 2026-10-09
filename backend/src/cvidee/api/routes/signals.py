"""Signals and analysis availability (FR-01, FR-04)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from cvidee.api.routes.deps import get_stub_store_problem
from cvidee.api.schemas.common import problem_responses
from cvidee.api.schemas.signals import (
    AnalysisList,
    Signal,
    SignalList,
    SignalMappingUpdate,
)
from cvidee.api.stubs.store import StubStore
from cvidee.signals.backend import SignalsBackend

router = APIRouter(tags=["signals"], responses=problem_responses(501))


def get_signals(request: Request) -> SignalsBackend | StubStore:
    stub = getattr(request.app.state, "stub_store", None)
    if isinstance(stub, StubStore):
        return stub
    sessions = getattr(request.app.state, "session_factory", None)
    if sessions is None:
        raise get_stub_store_problem()
    ingest = getattr(request.app.state, "ingest", None)
    return SignalsBackend(
        sessions,
        getattr(request.app.state, "ha_client", None),
        getattr(request.app.state, "runner", None),
        None if ingest is None else ingest.refresh_tracked,
    )


Signals = Annotated[SignalsBackend | StubStore, Depends(get_signals)]

SignalId = Annotated[
    str, Path(description="Signal id '<role>@<scope>'.", examples=["flame@boiler"])
]


@router.get("/signals")
async def list_signals(store: Signals) -> SignalList:
    """All signal roles with their mapping, age and state."""
    return store.signal_list()


@router.put("/signals/{signal_id}", responses=problem_responses(404, 422, 502, 503))
async def update_signal(signal_id: SignalId, body: SignalMappingUpdate, store: Signals) -> Signal:
    """Map a signal to an HA entity (or unlink with ``entity_id: null``)."""
    if isinstance(store, StubStore):
        return store.update_signal(signal_id, body)
    return await store.update_signal(signal_id, body)


@router.get("/analyses")
async def list_analyses(store: Signals) -> AnalysisList:
    """Availability per analysis given the mapped signals (FR-04)."""
    return store.analyses()
