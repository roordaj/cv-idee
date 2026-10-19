"""Daily and weekly read-only report snapshots (FR-40, issue #146)."""

import time
from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy.orm import Session, sessionmaker

from cvidee.api.report_read import ReportsReadModel
from cvidee.api.routes.deps import get_monitoring
from cvidee.api.schemas.common import problem_responses
from cvidee.api.schemas.reports import ReportPeriodKind, ReportSnapshot

router = APIRouter(prefix="/reports", tags=["reports"], responses=problem_responses(422, 501))


@router.get("/{kind}")
async def get_report(
    kind: ReportPeriodKind,
    request: Request,
    reference_date: Annotated[
        date | None,
        Query(
            description=(
                "Local date; for a week this must be Monday. "
                "Defaults to the previous complete period."
            ),
        ),
    ] = None,
) -> ReportSnapshot:
    """Build a read-only snapshot for the previous or specified complete local period."""
    sessions: sessionmaker[Session] | None = getattr(request.app.state, "session_factory", None)
    if sessions is None:
        raise HTTPException(status_code=501, detail="Rapportage is niet beschikbaar")
    monitoring = get_monitoring(request)
    reports = ReportsReadModel(sessions, monitoring, clock=lambda: int(time.time() * 1000))
    return reports.report(kind, reference_date)
