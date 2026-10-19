"""Report export safety, content parity and PDF pagination."""

import csv
from datetime import UTC, datetime
from io import BytesIO, StringIO
from pathlib import Path

import httpx
from pypdf import PdfReader

from cvidee.analysis.types import EndReason, Mode
from cvidee.api.openapi import openapi_spec
from cvidee.api.report_export import (
    render_report_csv,
    render_report_html,
    render_report_pdf,
    report_filename,
)
from cvidee.api.schemas.common import TimeRange
from cvidee.api.schemas.data import (
    Cycle,
    CycleClass,
    CycleSummary,
    QualityEvent,
    QualityResponse,
    SignalCoverage,
)
from cvidee.api.schemas.findings import FindingSummary
from cvidee.api.schemas.reports import (
    ReportAdvice,
    ReportChange,
    ReportChangeEvaluation,
    ReportPeriodKind,
    ReportSnapshot,
    ReportStatusChange,
)
from cvidee.config import Settings
from cvidee.main import create_app
from cvidee.rules.base import Category, Certainty, Severity
from cvidee.store.engine import create_db_engine, create_session_factory, database_url
from cvidee.store.enums import EvaluationVerdict, FindingLifecycle, RecommendationStatus
from cvidee.store.models import ReportSnapshotRecord
from cvidee.store.schema import upgrade_to_head

START = datetime(2026, 10, 18, 22, tzinfo=UTC)
END = datetime(2026, 10, 19, 22, tzinfo=UTC)


def make_report(cycle_count: int = 1) -> ReportSnapshot:
    period = TimeRange(start=START, end=END)
    quality = QualityResponse(
        range=period,
        core_coverage_pct=None,
        coverage=[
            SignalCoverage(
                name="Vlamstatus",
                signal_ids=["flame@boiler"],
                coverage_pct=None,
                segments=[],
            )
        ],
        events=[
            QualityEvent(
                kind=None,
                title="Datagat; <script>",
                consequence='Onbekend "bewijs"',
                at=START,
                end=START,
                signal_ids=["flame@boiler"],
                recovered=True,
            )
        ],
        mode_share_range=period,
        mode_share=[],
        flame_resolution_s=None,
        flame_resolution_text="Meetresolutie onbekend.",
    )
    cycle = Cycle(
        number=1,
        start=START,
        end=START.replace(minute=15),
        duration_s=900,
        duration_is_lower_bound=False,
        mode=Mode.CH,
        end_reason=EndReason.DEMAND_ENDED,
        max_flow_temperature=55.5,
        flow_setpoint=None,
        mean_modulation_pct=30,
        short_during_demand=False,
        classification=CycleClass.NORMAL,
    )
    cycles = [cycle.model_copy(update={"number": index}) for index in range(1, cycle_count + 1)]
    finding = FindingSummary(
        id="B-014",
        category=Category.CYCLES,
        title='Kort branden <script>alert("x")</script>',
        severity=Severity.HIGH,
        certainty=Certainty.REASONABLE,
        relevance=[],
        lifecycle=FindingLifecycle.ACTIVE,
        status=RecommendationStatus.OPEN,
        status_text="Open",
        period=period,
        when_text="18 okt 23:00",
    )
    evaluation = ReportChangeEvaluation(
        verdict=EvaluationVerdict.TRADE_OFF,
        summary="Meer comfort, minder vergelijkbare dagen.",
        reference=period,
        observation=period,
        comparability=[{"check": "coverage", "outcome": "limited"}],
        metrics=[{"metric": "starts_per_hour", "before": 1.25, "after": 1.0}],
    )
    return ReportSnapshot(
        kind=ReportPeriodKind.DAY,
        period=period,
        generated_at=END,
        quality=quality,
        cycle_summary=CycleSummary(
            observed_hours=12,
            starts_per_hour=1.25,
            ch_cycles=cycle_count,
            dhw_cycles=0,
            short_during_demand=0,
            short_cycle_threshold_s=180,
            median_burn_s=900,
            mean_burn_s=900,
            median_pause_s=None,
            total_burn_s=900,
            incomplete_cycles=0,
        ),
        cycles=cycles,
        findings=[finding],
        open_advice=[
            ReportAdvice(
                finding_id="B-014",
                title='Advies; "ketel"',
                status=RecommendationStatus.OPEN,
                action='=SUM(1;1) en "uitleg"\nvolgende regel',
                missing_signals=["flow_temperature@boiler"],
                success_criterion="Minimaal 2 uur normale brandtijd",
                rollback_criterion="Stop bij comfortklachten",
            )
        ],
        status_changes=[
            ReportStatusChange(
                at=START,
                finding_id="B-014",
                title="Status voorbeeld",
                status=RecommendationStatus.ACCEPTED,
            )
        ],
        changes=[
            ReportChange(
                change_id="W-01",
                at=START,
                parameter="Maximale aanvoer",
                old_value="70 °C",
                new_value="60 °C",
                reason='Gebruiker noteerde:; "lager"',
                evaluation=evaluation,
            )
        ],
        has_more_cycles=cycle_count > 500,
    )


def test_csv_is_quoted_formula_safe_and_keeps_unknowns_explicit() -> None:
    report = make_report()
    csv_text = render_report_csv(report)
    rows = list(csv.reader(StringIO(csv_text, newline=""), delimiter=";"))
    header = rows[0]
    assert header == [
        "type",
        "id",
        "tijdstip",
        "status",
        "titel",
        "waarde",
        "eenheid",
        "toelichting",
        "dekking",
    ]

    advice = next(row for row in rows[1:] if row[0] == "advies")
    assert advice[7].startswith("'=SUM")
    assert "\nvolgende regel" in advice[7]
    assert '"uitleg"' in advice[7]
    assert "Onbekend" in csv_text
    assert "1,25" in csv_text
    assert "60 °C" in csv_text
    assert "limited" in csv_text


def test_html_escapes_untrusted_text_and_has_dutch_report_sections() -> None:
    rendered = render_report_html(make_report())

    assert '<html lang="nl-NL">' in rendered
    assert "Gegevenskwaliteit" in rendered
    assert "Bevindingen en adviezen" in rendered
    assert "Wijzigingen en evaluaties" in rendered
    assert "Kort branden &lt;script&gt;" in rendered
    assert "<script>alert" not in rendered
    assert "Herstelcriterium" in rendered
    assert "Vergelijkbaarheid" in rendered


def test_pdf_contains_report_items_and_page_numbers() -> None:
    data = render_report_pdf(make_report(cycle_count=75))
    reader = PdfReader(BytesIO(data))
    assert data.startswith(b"%PDF-")
    assert len(reader.pages) > 1
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Dagrapport" in text
    assert "CV-analyserapport" in text
    assert "B-014" in text
    assert "Afweging" in text
    assert "Pagina 1" in text
    assert f"Pagina {len(reader.pages)}" in text


def test_filenames_use_local_calendar_period_and_safe_characters() -> None:
    report = make_report()
    assert report_filename(report, "pdf") == "cv-rapport-day-2026-10-19.pdf"

    week_report = report.model_copy(update={"kind": ReportPeriodKind.WEEK})
    assert report_filename(week_report, "csv") == "cv-rapport-week-2026-W43.csv"


async def test_export_routes_return_downloads_and_match_openapi_media_types(
    tmp_path: Path,
) -> None:
    db_url = database_url(tmp_path / "reports.sqlite")
    upgrade_to_head(db_url)
    factory = create_session_factory(create_db_engine(db_url))
    app = create_app(
        Settings.model_validate(
            {"CVIDEE_STUB_DATA": "1", "CVIDEE_DB_PATH": str(tmp_path / "reports.sqlite")}
        )
    )
    app.state.session_factory = factory

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        html = await client.get("/api/reports/day/html?reference_date=2026-10-18")
        csv_response = await client.get("/api/reports/day/csv?reference_date=2026-10-18")
        pdf = await client.get("/api/reports/day/pdf?reference_date=2026-10-18")

    assert html.status_code == csv_response.status_code == pdf.status_code == 200
    assert html.headers["content-type"].startswith("text/html")
    assert csv_response.headers["content-type"].startswith("text/csv")
    assert pdf.headers["content-type"] == "application/pdf"
    assert 'filename="cv-rapport-day-2026-10-18.html"' in html.headers["content-disposition"]
    assert 'filename="cv-rapport-day-2026-10-18.csv"' in csv_response.headers["content-disposition"]
    assert 'filename="cv-rapport-day-2026-10-18.pdf"' in pdf.headers["content-disposition"]
    assert "Gegevenskwaliteit" in html.text
    assert csv_response.text.startswith("type;id;tijdstip;")
    assert PdfReader(BytesIO(pdf.content)).pages

    paths = openapi_spec()["paths"]
    assert "text/html" in paths["/api/reports/{kind}/html"]["get"]["responses"]["200"]["content"]
    assert "text/csv" in paths["/api/reports/{kind}/csv"]["get"]["responses"]["200"]["content"]
    assert (
        "application/pdf" in paths["/api/reports/{kind}/pdf"]["get"]["responses"]["200"]["content"]
    )


async def test_report_downloads_use_existing_api_token_auth(tmp_path: Path) -> None:
    db_url = database_url(tmp_path / "authenticated-reports.sqlite")
    upgrade_to_head(db_url)
    factory = create_session_factory(create_db_engine(db_url))
    app = create_app(
        Settings.model_validate(
            {
                "CVIDEE_API_TOKEN": "report-secret",
                "CVIDEE_DB_PATH": str(tmp_path / "authenticated-reports.sqlite"),
            }
        )
    )
    app.state.session_factory = factory

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        unauthorized = await client.get("/api/reports/day/csv?reference_date=2026-10-18")
        authorized = await client.get(
            "/api/reports/day/csv?reference_date=2026-10-18",
            headers={"Authorization": "Bearer report-secret"},
        )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200


async def test_exports_use_the_created_immutable_snapshot(tmp_path: Path) -> None:
    db_url = database_url(tmp_path / "snapshot-reports.sqlite")
    upgrade_to_head(db_url)
    factory = create_session_factory(create_db_engine(db_url))
    app = create_app(
        Settings.model_validate(
            {"CVIDEE_STUB_DATA": "1", "CVIDEE_DB_PATH": str(tmp_path / "snapshot-reports.sqlite")}
        )
    )
    app.state.session_factory = factory
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/reports/day/snapshots", json={"reference_date": "2026-10-18"}
        )
        assert created.status_code == 200
        snapshot = created.json()
        with factory.begin() as session:
            record = session.get(ReportSnapshotRecord, snapshot["id"])
            assert record is not None
            record.snapshot = {**record.snapshot, "generated_at": "2001-01-01T00:00:00Z"}
        exported = await client.get(f"/api/reports/day/html?snapshot_id={snapshot['id']}")
        delivery = await client.get("/api/reports/day/delivery-status?reference_date=2026-10-18")
    assert exported.status_code == 200
    assert 'filename="cv-rapport-day-2026-10-18.html"' in exported.headers["content-disposition"]
    assert "Gegevenskwaliteit" in exported.text
    assert "01-01-2001 01:00" in exported.text
    assert delivery.status_code == 200
    assert delivery.json() == {
        "enabled": False,
        "available": False,
        "status": None,
        "error": None,
    }
