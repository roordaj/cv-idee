"""Room-comfort metrics read endpoint (FR-17)."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request
from sqlalchemy.orm import Session, sessionmaker

from cvidee.api.comfort_read import RoomComfortReadModel
from cvidee.api.routes.deps import get_stub_store_problem
from cvidee.api.schemas.comfort import RoomComfortAnalysisResponse
from cvidee.api.stubs.store import StubStore

router = APIRouter()


@router.get("/comfort", tags=["comfort"])
def get_room_comfort(
    request: Request,
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
) -> RoomComfortAnalysisResponse:
    """Return independent comfort metrics by room for a UTC range (default: last 7 days)."""
    stub: StubStore | None = getattr(request.app.state, "stub_store", None)
    if stub is not None:
        return stub.room_comfort_analysis(start, end)
    factory: sessionmaker[Session] | None = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise get_stub_store_problem()
    model = RoomComfortReadModel(factory, lambda: int(datetime.now(UTC).timestamp() * 1000))
    return model.analyze(start, end)
