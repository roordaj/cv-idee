"""Signals and analysis availability (FR-01, FR-04)."""

from typing import Annotated

from fastapi import APIRouter, Path

from cvidee.api.routes.deps import Store
from cvidee.api.schemas.common import problem_responses
from cvidee.api.schemas.signals import (
    AnalysisList,
    Signal,
    SignalList,
    SignalMappingUpdate,
)

router = APIRouter(tags=["signals"], responses=problem_responses(501))

SignalId = Annotated[
    str, Path(description="Signal id '<role>@<scope>'.", examples=["flame@boiler"])
]


@router.get("/signals")
async def list_signals(store: Store) -> SignalList:
    """All signal roles with their mapping, age and state."""
    return store.signal_list()


@router.put("/signals/{signal_id}", responses=problem_responses(404, 422))
async def update_signal(signal_id: SignalId, body: SignalMappingUpdate, store: Store) -> Signal:
    """Map a signal to an HA entity (or unlink with ``entity_id: null``)."""
    return store.update_signal(signal_id, body)


@router.get("/analyses")
async def list_analyses(store: Store) -> AnalysisList:
    """Availability per analysis given the mapped signals (FR-04)."""
    return store.analyses()
