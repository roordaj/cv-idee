"""Zone-count analysis endpoint (FR-18)."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request
from sqlalchemy.orm import Session, sessionmaker

from cvidee.api.problems import ProblemError
from cvidee.api.schemas.zone_analysis import ZoneAnalysisResponse
from cvidee.api.stubs.store import StubStore
from cvidee.api.zone_analysis_read import ZoneAnalysisReadModel

router = APIRouter()


@router.get("/zones/analysis", tags=["zone-analysis"])
def get_zone_analysis(
    request: Request,
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
) -> ZoneAnalysisResponse:
    """Compare complete CH cycles with independently counted zone demand and valve states."""
    factory: sessionmaker[Session] | None = getattr(request.app.state, "session_factory", None)
    if factory is None:
        stub_store: StubStore | None = getattr(request.app.state, "stub_store", None)
        if stub_store is None:
            raise ProblemError(
                503, "Analyse niet beschikbaar", "Er is geen gegevensopslag ingesteld."
            )
        return stub_store.zone_analysis(start, end)
    return ZoneAnalysisReadModel(
        factory, lambda: int(datetime.now(UTC).timestamp() * 1000)
    ).analyze(start, end)
