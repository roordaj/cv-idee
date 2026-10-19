"""Daily and weekly read-only report snapshots (FR-40, issue #146)."""

import time
from datetime import date
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import select
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
from cvidee.api.schemas.reports import (
    CreatedReportSnapshot,
    ReportDeliveryStatus,
    ReportPeriodKind,
    ReportSnapshot,
    ReportSnapshotIn,
)
from cvidee.notify.backend import read_policy
from cvidee.store.models import Notification, ReportSnapshotRecord

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


@router.post("/{kind}/snapshots")
async def create_report_snapshot(
    kind: ReportPeriodKind, body: ReportSnapshotIn, request: Request
) -> CreatedReportSnapshot:
    """Create and retain one immutable snapshot for preview and subsequent exports."""
    report = _read_report(kind, request, body.reference_date)
    sessions: sessionmaker[Session] | None = getattr(request.app.state, "session_factory", None)
    if sessions is None:
        raise HTTPException(status_code=501, detail="Rapportage is niet beschikbaar")
    snapshot_id = str(uuid4())
    with sessions.begin() as session:
        session.add(
            ReportSnapshotRecord(
                id=snapshot_id,
                kind=kind.value,
                snapshot=report.model_dump(mode="json"),
                generated_at_ts=round(report.generated_at.timestamp() * 1000),
            )
        )
    return CreatedReportSnapshot(id=snapshot_id, report=report)


@router.get("/{kind}/delivery-status")
async def report_delivery_status(
    kind: ReportPeriodKind,
    request: Request,
    reference_date: Annotated[date, Query(description="Local report date; Monday for a week.")],
) -> ReportDeliveryStatus:
    """Return opt-in and delivery state for the selected report period."""
    sessions: sessionmaker[Session] | None = getattr(request.app.state, "session_factory", None)
    if sessions is None:
        raise HTTPException(status_code=501, detail="Rapportage is niet beschikbaar")
    with sessions() as session:
        policy = read_policy(session)
        row = session.scalar(
            select(Notification)
            .where(
                Notification.payload["report_period"].as_string()
                == f"{kind.value}:{reference_date.isoformat()}"
            )
            .order_by(Notification.id.desc())
        )
        status = None if row is None else row.delivery_status
        error = None if row is None else row.error
    enabled = (
        policy.daily_report_enabled
        if kind is ReportPeriodKind.DAY
        else policy.weekly_report_enabled
    )
    return ReportDeliveryStatus(
        enabled=enabled,
        available=getattr(request.app.state.settings, "notify_target", None) is not None,
        status=status,
        error=error,
    )


@router.get("/{kind}/html", response_class=Response, responses={200: _HTML_RESPONSE})
async def download_report_html(
    kind: ReportPeriodKind,
    request: Request,
    reference_date: date | None = None,
    snapshot_id: str | None = None,
) -> Response:
    """Download the reference HTML rendering of the selected report snapshot."""
    report = _select_report(kind, request, reference_date, snapshot_id)
    return _download(
        render_report_html(report), "text/html; charset=utf-8", report_filename(report, "html")
    )


@router.get("/{kind}/csv", response_class=Response, responses={200: _CSV_RESPONSE})
async def download_report_csv(
    kind: ReportPeriodKind,
    request: Request,
    reference_date: date | None = None,
    snapshot_id: str | None = None,
) -> Response:
    """Download all report items as a spreadsheet-safe nl-NL CSV file."""
    report = _select_report(kind, request, reference_date, snapshot_id)
    return _download(
        render_report_csv(report), "text/csv; charset=utf-8", report_filename(report, "csv")
    )


@router.get("/{kind}/pdf", response_class=Response, responses={200: _PDF_RESPONSE})
async def download_report_pdf(
    kind: ReportPeriodKind,
    request: Request,
    reference_date: date | None = None,
    snapshot_id: str | None = None,
) -> Response:
    """Download a paginated PDF rendering of the selected report snapshot."""
    report = _select_report(kind, request, reference_date, snapshot_id)
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


def _select_report(
    kind: ReportPeriodKind,
    request: Request,
    reference_date: date | None,
    snapshot_id: str | None,
) -> ReportSnapshot:
    if snapshot_id is None:
        return _read_report(kind, request, reference_date)
    sessions: sessionmaker[Session] | None = getattr(request.app.state, "session_factory", None)
    if sessions is None:
        raise HTTPException(status_code=501, detail="Rapportage is niet beschikbaar")
    with sessions() as session:
        record = session.get(ReportSnapshotRecord, snapshot_id)
        if record is None or record.kind != kind.value:
            raise HTTPException(status_code=404, detail="Rapportmomentopname niet gevonden")
        return ReportSnapshot.model_validate(record.snapshot)


def _download(content: str | bytes, media_type: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
