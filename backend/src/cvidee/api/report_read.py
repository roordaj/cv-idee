"""Read-only report snapshots assembled from existing analysis and history read models."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from datetime import time as day_time
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cvidee.api.findings_read import FindingsReadModel
from cvidee.api.routes.deps import MonitoringBackend
from cvidee.api.schemas.common import TimeRange
from cvidee.api.schemas.findings import FindingSummary
from cvidee.api.schemas.reports import (
    ReportAdvice,
    ReportChange,
    ReportChangeEvaluation,
    ReportPeriodKind,
    ReportSnapshot,
    ReportStatusChange,
)
from cvidee.api.stubs.fixtures import status_text
from cvidee.changes.log import as_change
from cvidee.findings.repository import SqlFindingRepository
from cvidee.store.enums import RecommendationStatus, SnapshotTrigger
from cvidee.store.models import Change, Finding, Recommendation, RecommendationSnapshot

AMS = ZoneInfo("Europe/Amsterdam")
DAY_MS = 86_400_000
MAX_CYCLES = 500
OPEN_STATUSES = frozenset(
    {
        RecommendationStatus.OPEN,
        RecommendationStatus.POSTPONED,
        RecommendationStatus.ROLLBACK_TRIGGERED,
    }
)


def report_bounds(
    kind: ReportPeriodKind, reference_date: date | None, now_ms: int
) -> tuple[datetime, datetime]:
    """Return a complete local calendar day/week as UTC half-open bounds."""
    now = datetime.fromtimestamp(now_ms / 1000, UTC)
    local_today = now.astimezone(AMS).date()
    if kind is ReportPeriodKind.DAY:
        day = local_today - timedelta(days=1) if reference_date is None else reference_date
        if day >= local_today:
            raise ValueError("Kies een volledig afgesloten dag.")
        local_start = datetime.combine(day, day_time.min, AMS)
        local_end = datetime.combine(day + timedelta(days=1), day_time.min, AMS)
    else:
        if reference_date is None:
            this_monday = local_today - timedelta(days=local_today.weekday())
            monday = this_monday - timedelta(days=7)
        else:
            monday = reference_date
        if monday.weekday() != 0:
            raise ValueError("Kies de maandag van de gewenste week.")
        local_start = datetime.combine(monday, day_time.min, AMS)
        local_end = datetime.combine(monday + timedelta(days=7), day_time.min, AMS)
        if local_end.date() > local_today:
            raise ValueError("Kies een volledig afgesloten week.")
    return local_start.astimezone(UTC), local_end.astimezone(UTC)


class ReportsReadModel:
    """Build one immutable API view without refreshing advice or recomputing evaluations."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        monitoring: MonitoringBackend,
        *,
        clock: Callable[[], int] = lambda: int(time.time() * 1000),
    ) -> None:
        self._sessions = sessions
        self._monitoring = monitoring
        self._clock = clock

    def report(self, kind: ReportPeriodKind, reference_date: date | None = None) -> ReportSnapshot:
        generated_at = self._clock()
        try:
            start, end = report_bounds(kind, reference_date, generated_at)
        except ValueError as exc:
            from cvidee.api.problems import ProblemError

            raise ProblemError(422, "Ongeldige rapportperiode", str(exc)) from exc
        interval = TimeRange(start=start, end=end)
        quality = self._monitoring.quality(start, end)
        cycles = self._monitoring.cycles(MAX_CYCLES, 0, start, end)
        lo, hi = round(start.timestamp() * 1000), round(end.timestamp() * 1000)
        with self._sessions() as session:
            rows = list(
                session.scalars(
                    select(Finding)
                    .where(
                        Finding.first_seen_ts < hi,
                        (Finding.last_seen_ts >= lo)
                        | (Finding.resolved_at_ts.is_not(None) & (Finding.resolved_at_ts >= lo)),
                    )
                    .order_by(Finding.priority_score.desc(), Finding.first_seen_ts)
                )
            )
            repository = SqlFindingRepository(session)
            all_recommendations = list(session.scalars(select(Recommendation)))
            latest_status: dict[int, RecommendationStatus] = {}
            snapshots = list(
                session.scalars(
                    select(RecommendationSnapshot)
                    .where(RecommendationSnapshot.taken_at_ts <= hi)
                    .order_by(
                        RecommendationSnapshot.recommendation_id,
                        RecommendationSnapshot.taken_at_ts,
                        RecommendationSnapshot.id,
                    )
                )
            )
            for snapshot in snapshots:
                latest_status[snapshot.recommendation_id] = snapshot.status
            findings_read = FindingsReadModel(session, self._clock, refresh_status=False)
            findings: list[FindingSummary] = []
            for finding_row in rows:
                rec = repository.recommendation_of(finding_row)
                status = (
                    latest_status.get(rec.id, RecommendationStatus.OPEN)
                    if rec is not None and rec.created_at_ts <= hi
                    else RecommendationStatus.OPEN
                )
                if rec is not None and rec.created_at_ts > hi:
                    continue
                fields = findings_read._summary_fields(finding_row, rec)
                fields["status"] = status
                fields["status_text"] = status_text(status, None)
                findings.append(FindingSummary(**fields))
            open_advice: list[ReportAdvice] = []
            for rec in all_recommendations:
                if rec.created_at_ts > hi:
                    continue
                status = latest_status.get(rec.id, RecommendationStatus.OPEN)
                if status not in OPEN_STATUSES:
                    continue
                finding_row = rec.finding
                open_advice.append(
                    ReportAdvice(
                        finding_id=finding_row.human_id,
                        title=finding_row.title,
                        status=status,
                        action=rec.action,
                        missing_signals=[
                            str(signal) for signal in finding_row.support.get("missing_signals", [])
                        ],
                    )
                )
            snapshot_finding_ids = {snapshot.finding_id for snapshot in snapshots}
            snapshot_findings = {
                finding.id: finding
                for finding in session.scalars(
                    select(Finding).where(Finding.id.in_(snapshot_finding_ids))
                )
            }
            status_changes = [
                ReportStatusChange(
                    at=datetime.fromtimestamp(s.taken_at_ts / 1000, UTC),
                    finding_id=snapshot_findings[s.finding_id].human_id,
                    title=snapshot_findings[s.finding_id].title,
                    status=s.status,
                )
                for s in snapshots
                if lo <= s.taken_at_ts < hi
                and s.trigger is SnapshotTrigger.STATUS_CHANGED
                and s.finding_id in snapshot_findings
            ]
            change_rows = list(
                session.scalars(
                    select(Change)
                    .where(Change.changed_at_ts >= lo, Change.changed_at_ts < hi)
                    .order_by(Change.changed_at_ts, Change.id)
                )
            )
            changes = []
            for change_row in change_rows:
                shown = as_change(change_row, session)
                evaluation = change_row.evaluation
                evaluation_api = None
                if evaluation is not None:
                    evaluation_api = ReportChangeEvaluation(
                        verdict=evaluation.verdict,
                        summary=evaluation.summary,
                        reference=TimeRange(
                            start=datetime.fromtimestamp(evaluation.reference_start_ts / 1000, UTC),
                            end=datetime.fromtimestamp(evaluation.reference_end_ts / 1000, UTC),
                        ),
                        observation=TimeRange(
                            start=datetime.fromtimestamp(
                                evaluation.observation_start_ts / 1000, UTC
                            ),
                            end=datetime.fromtimestamp(evaluation.observation_end_ts / 1000, UTC),
                        ),
                        comparability=list(evaluation.comparability or []),
                        metrics=list(evaluation.metrics or []),
                    )
                changes.append(
                    ReportChange(
                        change_id=change_row.human_id,
                        at=shown.at,
                        parameter=shown.parameter,
                        old_value=shown.old_value,
                        new_value=shown.new_value,
                        reason=shown.reason,
                        evaluation=evaluation_api,
                    )
                )
        return ReportSnapshot(
            kind=kind,
            period=interval,
            generated_at=datetime.fromtimestamp(generated_at / 1000, UTC),
            quality=quality,
            cycle_summary=cycles.summary,
            cycles=cycles.items,
            findings=findings,
            open_advice=open_advice,
            status_changes=status_changes,
            changes=changes,
            has_more_cycles=cycles.total > len(cycles.items),
        )
