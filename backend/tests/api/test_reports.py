"""Calendar boundaries for daily and weekly reports."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from cvidee.api.live_read import LiveReadModel
from cvidee.api.report_read import ReportsReadModel, report_bounds
from cvidee.api.schemas.reports import ReportPeriodKind
from cvidee.config import Settings
from cvidee.store.engine import create_db_engine, create_session_factory, database_url
from cvidee.store.schema import upgrade_to_head


def test_day_bounds_follow_amsterdam_dst() -> None:
    start, end = report_bounds(
        ReportPeriodKind.DAY,
        date(2026, 3, 29),
        int(datetime(2026, 3, 31, 12, tzinfo=UTC).timestamp() * 1000),
    )

    assert start == datetime(2026, 3, 28, 23, tzinfo=UTC)
    assert end == datetime(2026, 3, 29, 22, tzinfo=UTC)


def test_week_defaults_to_previous_complete_amsterdam_week() -> None:
    start, end = report_bounds(
        ReportPeriodKind.WEEK,
        None,
        int(datetime(2026, 10, 19, 12, tzinfo=UTC).timestamp() * 1000),
    )

    assert start == datetime(2026, 10, 11, 22, tzinfo=UTC)
    assert end == datetime(2026, 10, 18, 22, tzinfo=UTC)


def test_empty_report_keeps_metrics_and_coverage_unknown(tmp_path: Path) -> None:
    now_ms = int(datetime(2026, 10, 19, 12, tzinfo=UTC).timestamp() * 1000)
    url = database_url(tmp_path / "report.sqlite")
    upgrade_to_head(url)
    sessions = create_session_factory(create_db_engine(url))
    monitoring = LiveReadModel(sessions, Settings(), None, None, clock=lambda: now_ms)

    report = ReportsReadModel(sessions, monitoring, clock=lambda: now_ms).report(
        ReportPeriodKind.DAY, date(2026, 10, 18)
    )

    assert report.quality.core_coverage_pct is None
    assert all(row.coverage_pct is None for row in report.quality.coverage)
    assert report.cycle_summary.starts_per_hour is None
    assert report.cycle_summary.total_burn_s is None
    assert report.cycles == []
    assert report.findings == []


@pytest.mark.parametrize(
    ("kind", "reference_date"),
    [
        (ReportPeriodKind.DAY, date(2026, 10, 19)),
        (ReportPeriodKind.DAY, date(2026, 10, 20)),
        (ReportPeriodKind.WEEK, date(2026, 10, 19)),
        (ReportPeriodKind.WEEK, date(2026, 10, 18)),
    ],
)
def test_report_rejects_incomplete_periods(kind: ReportPeriodKind, reference_date: date) -> None:
    now_ms = int(datetime(2026, 10, 19, 12, tzinfo=UTC).timestamp() * 1000)

    with pytest.raises(ValueError, match="Kies"):
        report_bounds(kind, reference_date, now_ms)
