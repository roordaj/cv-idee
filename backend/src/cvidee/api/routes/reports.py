"""Daily and weekly read-only report snapshots (FR-40, issue #146)."""

import time
from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session, sessionmaker

from cvidee.api.report_export import (
    render_report_csv,
    render_report_html,
    render_report_pdf,
    report_filename,
)
from cvidee.api.report_read import ReportsReadModel
from cvidee.api.routes.deps import get_monitoring
from cvidee.api.schemas.common import problem_responses
from cvidee.api.schemas.reports import ReportPeriodKind, ReportSnapshot

router = APIRouter(prefix="/reports", tags=["reports"], responses=problem_responses(422, 501))

_HTML_RESPONSE = {"content": {"text/html": {"schema": {"type": "string"}}}}
_CSV_RESPONSE = {"content": {"text/csv": {"schema": {"type": "string"}}}}
_PDF_RESPONSE = {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}}


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
    return _read_report(kind, request, reference_date)


@router.get("/{kind}/html", response_class=Response, responses={200: _HTML_RESPONSE})
async def download_report_html(
    kind: ReportPeriodKind, request: Request, reference_date: date | None = None
) -> Response:
    """Download the reference HTML rendering of the selected report snapshot."""
    report = _read_report(kind, request, reference_date)
    return _download(
        render_report_html(report), "text/html; charset=utf-8", report_filename(report, "html")
    )


@router.get("/{kind}/csv", response_class=Response, responses={200: _CSV_RESPONSE})
async def download_report_csv(
    kind: ReportPeriodKind, request: Request, reference_date: date | None = None
) -> Response:
    """Download all report items as a spreadsheet-safe nl-NL CSV file."""
    report = _read_report(kind, request, reference_date)
    return _download(
        render_report_csv(report), "text/csv; charset=utf-8", report_filename(report, "csv")
    )


@router.get("/{kind}/pdf", response_class=Response, responses={200: _PDF_RESPONSE})
async def download_report_pdf(
    kind: ReportPeriodKind, request: Request, reference_date: date | None = None
) -> Response:
    """Download a paginated PDF rendering of the selected report snapshot."""
    report = _read_report(kind, request, reference_date)
    return _download(render_report_pdf(report), "application/pdf", report_filename(report, "pdf"))


def _read_report(
    kind: ReportPeriodKind, request: Request, reference_date: date | None
) -> ReportSnapshot:
    sessions: sessionmaker[Session] | None = getattr(request.app.state, "session_factory", None)
    if sessions is None:
        raise HTTPException(status_code=501, detail="Rapportage is niet beschikbaar")
    monitoring = get_monitoring(request)
    reports = ReportsReadModel(sessions, monitoring, clock=lambda: int(time.time() * 1000))
    return reports.report(kind, reference_date)


def _download(content: str | bytes, media_type: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
