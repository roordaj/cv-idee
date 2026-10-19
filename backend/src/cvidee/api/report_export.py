"""Pure HTML, PDF and CSV renderers for validated report snapshots (issue #147)."""

from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from datetime import datetime, timedelta
from html import escape
from io import BytesIO, StringIO
from typing import Any
from xml.sax.saxutils import escape as xml_escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from cvidee.api.schemas.reports import ReportChange, ReportSnapshot

AMS = ZoneInfo("Europe/Amsterdam")
CSV_HEADER = (
    "type",
    "id",
    "tijdstip",
    "status",
    "titel",
    "waarde",
    "eenheid",
    "toelichting",
    "dekking",
)
CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def report_filename(report: ReportSnapshot, extension: str) -> str:
    """Return a deterministic ASCII filename for the snapshot's local period."""
    local_start = report.period.start.astimezone(AMS)
    if report.kind.value == "day":
        period = local_start.strftime("%Y-%m-%d")
    else:
        period = f"{local_start.isocalendar().year}-W{local_start.isocalendar().week:02d}"
    return f"cv-rapport-{report.kind.value}-{period}.{extension}"


def render_report_html(report: ReportSnapshot) -> str:
    """Render one accessible, self-contained Dutch HTML report."""
    period = _period_text(report)
    sections = [
        _html_section("Samenvatting", _summary_html(report)),
        _quality_html(report),
        _findings_html(report),
        _changes_html(report),
        _cycles_html(report),
    ]
    return (
        '<!doctype html>\n<html lang="nl-NL"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>CV-rapport {escape(period)}</title><style>{_REPORT_CSS}</style>"
        f"</head><body><main><header><h1>CV-analyserapport</h1>"
        f'<p class="period">{escape(period)}</p>'
        f"<p>Gegenereerd: {_local_time(report.generated_at)}</p></header>"
        f"{''.join(sections)}</main></body></html>\n"
    )


def render_report_csv(report: ReportSnapshot) -> str:
    """Render all snapshot sections as semicolon-delimited nl-NL CSV."""
    rows: list[tuple[Any, ...]] = []

    def add(
        kind: str,
        ident: str = "",
        at: datetime | None = None,
        status: str = "",
        title: str = "",
        value: str | int | float | None = "",
        unit: str = "",
        detail: str = "",
        coverage: str = "",
    ) -> None:
        rows.append(
            (
                kind,
                _csv_text(ident),
                "" if at is None else _local_time(at),
                _csv_text(status),
                _csv_text(title),
                _csv_number(value) if isinstance(value, int | float) else _csv_text(value or ""),
                _csv_text(unit),
                _csv_text(detail),
                _csv_text(coverage),
            )
        )

    summary = report.cycle_summary
    for title, value, unit in (
        ("Waargenomen uren", summary.observed_hours, "uur"),
        ("Starts per uur", summary.starts_per_hour, "/uur"),
        ("CV-cycli", summary.ch_cycles, "cycli"),
        ("Tapwatercycli", summary.dhw_cycles, "cycli"),
        ("Kort branden tijdens warmtevraag", summary.short_during_demand, "cycli"),
        ("Mediane brandduur", summary.median_burn_s, "s"),
        ("Gemiddelde brandduur", summary.mean_burn_s, "s"),
        ("Mediane pauzeduur", summary.median_pause_s, "s"),
        ("Totale brandduur", summary.total_burn_s, "s"),
        ("Onvolledige cycli", summary.incomplete_cycles, "cycli"),
        ("Kernsignaaldekking", report.quality.core_coverage_pct, "%"),
    ):
        add(
            "kengetal",
            title=title,
            value=value,
            unit=unit,
            coverage="onbekend" if value is None else "bekend",
        )

    for signal in report.quality.coverage:
        add(
            "dekking",
            ident=", ".join(signal.signal_ids),
            title=signal.name,
            value=signal.coverage_pct,
            unit="%",
            detail=_coverage_detail(signal.segments),
            coverage="onbekend" if signal.coverage_pct is None else "bekend",
        )
    for event in report.quality.events:
        add(
            "gegevenskwaliteit",
            at=event.at,
            title=event.title,
            detail="; ".join(
                part
                for part in (
                    event.consequence,
                    f"Tot {_local_time(event.end)}" if event.end else "",
                    "Hersteld" if event.recovered else "Actief",
                )
                if part
            ),
            status="Hersteld" if event.recovered else "Actief",
        )
    for share in report.quality.mode_share:
        add(
            "modusverdeling",
            title=share.label,
            value=share.share_pct,
            unit="%",
            detail=f"{_decimal(share.minutes)} min",
        )
    add(
        "gegevenskwaliteit",
        title="Vlamstatusresolutie",
        detail=report.quality.flame_resolution_text,
    )
    for finding in report.findings:
        add(
            "bevinding",
            ident=finding.id,
            at=finding.period.start,
            status=finding.status_text,
            title=finding.title,
            detail=f"{_severity_text(finding.severity.value)}; "
            f"zekerheid {_certainty_text(finding.certainty.value)}; "
            f"{finding.when_text}",
        )
    for advice in report.open_advice:
        add(
            "advies",
            ident=advice.finding_id,
            status=_status_text(advice.status.value),
            title=advice.title,
            detail="; ".join(
                part
                for part in (
                    advice.action,
                    f"Herstelcriterium: {advice.success_criterion}"
                    if advice.success_criterion
                    else "",
                    f"Terugdraaicriterium: {advice.rollback_criterion}"
                    if advice.rollback_criterion
                    else "",
                    f"Ontbrekende signalen: {', '.join(advice.missing_signals)}"
                    if advice.missing_signals
                    else "",
                )
                if part
            ),
        )
    for status_change in report.status_changes:
        add(
            "statuswijziging",
            ident=status_change.finding_id,
            at=status_change.at,
            status=_status_text(status_change.status.value),
            title=status_change.title,
        )
    for report_change in report.changes:
        detail = f"{report_change.reason} {_evaluation_detail(report_change)}".strip()
        add(
            "wijziging",
            ident=report_change.change_id,
            at=report_change.at,
            status="Nog geen conclusie"
            if report_change.evaluation is None
            else _verdict_text(report_change.evaluation.verdict.value),
            title=report_change.parameter,
            value=f"{report_change.old_value} → {report_change.new_value}",
            detail=detail,
        )
    for cycle in report.cycles:
        add(
            "cyclus",
            ident=str(cycle.number),
            at=cycle.start,
            status=_cycle_class_text(cycle.classification.value),
            title=f"{_mode_text(cycle.mode.value)}-cyclus {cycle.number}",
            value=cycle.duration_s,
            unit="s",
            detail=f"Start: {_local_time(cycle.start)}; einde: "
            f"{'Onbekend' if cycle.end is None else _local_time(cycle.end)}; "
            f"eindreden: {_end_reason_text(cycle.end_reason.value)}; ondergrens: "
            f"{'ja' if cycle.duration_is_lower_bound else 'nee'}; "
            f"{_cycle_details(cycle)}",
        )

    output = StringIO(newline="")
    writer = csv.writer(
        output, delimiter=";", quotechar='"', doublequote=True, lineterminator="\r\n"
    )
    writer.writerow(CSV_HEADER)
    writer.writerows(rows)
    return output.getvalue()


def render_report_pdf(report: ReportSnapshot) -> bytes:
    """Render a paginated PDF with the same sections and order as the HTML report."""
    output = BytesIO()
    period = _period_text(report)
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=25 * mm,
        bottomMargin=20 * mm,
        title=f"CV-analyserapport {period}",
        author="CV-analyse",
    )
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=20
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportHeading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13
        )
    )
    styles.add(ParagraphStyle(name="ReportBody", parent=styles["BodyText"], leading=14))
    story: list[Any] = [
        Paragraph("CV-analyserapport", styles["ReportTitle"]),
        Paragraph(xml_escape(period), styles["ReportBody"]),
        Paragraph(f"Gegenereerd: {_local_time(report.generated_at)}", styles["ReportBody"]),
        Spacer(1, 8 * mm),
    ]
    _pdf_section(story, "Samenvatting", _summary_rows(report), styles)
    _pdf_section(story, "Gegevenskwaliteit", _quality_rows(report), styles)
    _pdf_section(story, "Bevindingen en adviezen", _finding_rows(report), styles)
    _pdf_section(story, "Wijzigingen en evaluaties", _change_rows(report), styles)
    _pdf_section(story, "Cycli", _cycle_rows(report), styles)

    def draw_page(canvas: Any, page_document: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(18 * mm, A4[1] - 14 * mm, f"CV-analyserapport · {period}")
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Pagina {page_document.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return output.getvalue()


def _period_text(report: ReportSnapshot) -> str:
    start = report.period.start.astimezone(AMS)
    end = report.period.end
    if report.kind.value == "day":
        weekdays = (
            "maandag",
            "dinsdag",
            "woensdag",
            "donderdag",
            "vrijdag",
            "zaterdag",
            "zondag",
        )
        return f"Dagrapport · {weekdays[start.weekday()]} {start:%d-%m-%Y}"
    if end is None:
        end_text = "onbekend"
    else:
        last_day = end.astimezone(AMS).date() - timedelta(days=1)
        end_text = last_day.strftime("%d-%m-%Y")
    return f"Weekrapport · {start:%d-%m-%Y} t/m {end_text}"


def _local_time(value: datetime) -> str:
    return value.astimezone(AMS).strftime("%d-%m-%Y %H:%M")


def _decimal(value: float | int) -> str:
    return str(value).replace(".", ",")


def _csv_number(value: int | float) -> str:
    return _decimal(value)


def _evaluation_detail(change: ReportChange) -> str:
    evaluation = change.evaluation
    if evaluation is None:
        return "Nog geen conclusie"
    parts = [f"Oordeel: {_verdict_text(evaluation.verdict.value)}"]
    if evaluation.summary:
        parts.append(evaluation.summary)
    if evaluation.comparability:
        parts.append(
            "Vergelijkbaarheid: "
            + json.dumps(evaluation.comparability, ensure_ascii=False, sort_keys=True)
        )
    if evaluation.metrics:
        parts.append(
            "Kengetallen: " + json.dumps(evaluation.metrics, ensure_ascii=False, sort_keys=True)
        )
    return "; ".join(parts)


def _csv_text(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.lstrip(" \t\r\n")[:1] in CSV_FORMULA_PREFIXES:
        return f"'{text}"
    return text


def _summary_rows(report: ReportSnapshot) -> list[tuple[str, str, str]]:
    summary = report.cycle_summary
    return [
        ("Waargenomen uren", _decimal(summary.observed_hours), "uur"),
        ("Starts per uur", _unknown(summary.starts_per_hour), "/uur"),
        ("CV-cycli", str(summary.ch_cycles), "cycli"),
        ("Tapwatercycli", str(summary.dhw_cycles), "cycli"),
        ("Kort branden tijdens warmtevraag", str(summary.short_during_demand), "cycli"),
        ("Mediane brandduur", _unknown(summary.median_burn_s), "s"),
        ("Gemiddelde brandduur", _unknown(summary.mean_burn_s), "s"),
        ("Mediane pauzeduur", _unknown(summary.median_pause_s), "s"),
        ("Totale brandduur", _unknown(summary.total_burn_s), "s"),
        ("Onvolledige cycli", str(summary.incomplete_cycles), "cycli"),
        ("Kernsignaaldekking", _unknown(report.quality.core_coverage_pct), "%"),
    ]


def _quality_rows(report: ReportSnapshot) -> list[tuple[str, str, str]]:
    rows = [
        (
            f"{signal.name} ({', '.join(signal.signal_ids)})",
            _unknown(signal.coverage_pct),
            _coverage_detail(signal.segments)
            or ("%" if signal.coverage_pct is not None else "Onbekend"),
        )
        for signal in report.quality.coverage
    ]
    rows.extend(
        (
            event.title,
            event.consequence,
            f"{_local_time(event.at)}"
            + (f" t/m {_local_time(event.end)}" if event.end else "")
            + (" · hersteld" if event.recovered else " · actief"),
        )
        for event in report.quality.events
    )
    rows.extend(
        (f"Bedrijfsmodus · {share.label}", _decimal(share.share_pct), "%")
        for share in report.quality.mode_share
    )
    rows.append(("Vlamstatusresolutie", report.quality.flame_resolution_text, ""))
    rows.insert(
        0,
        (
            "Kernsignaaldekking",
            _unknown(report.quality.core_coverage_pct),
            "%" if report.quality.core_coverage_pct is not None else "",
        ),
    )
    if not rows:
        rows.append(("Gegevenskwaliteit", "Onbekend", ""))
    return rows


def _finding_rows(report: ReportSnapshot) -> list[tuple[str, str, str]]:
    rows = [
        (
            finding.title,
            f"{finding.id} · {finding.status_text}",
            _severity_text(finding.severity.value),
        )
        for finding in report.findings
    ]
    rows.extend(
        (
            advice.title,
            "; ".join(
                part
                for part in (
                    advice.action,
                    f"Herstelcriterium: {advice.success_criterion}"
                    if advice.success_criterion
                    else "",
                    f"Terugdraaicriterium: {advice.rollback_criterion}"
                    if advice.rollback_criterion
                    else "",
                    f"Ontbrekende signalen: {', '.join(advice.missing_signals)}"
                    if advice.missing_signals
                    else "",
                )
                if part
            ),
            _status_text(advice.status.value),
        )
        for advice in report.open_advice
    )
    rows.extend(
        (change.title, _status_text(change.status.value), _local_time(change.at))
        for change in report.status_changes
    )
    if not rows:
        rows.append(("Bevindingen en adviezen", "Geen items in deze periode", ""))
    return rows


def _change_rows(report: ReportSnapshot) -> list[tuple[str, str, str]]:
    rows = []
    for change in report.changes:
        value = f"{change.old_value} → {change.new_value}"
        verdict = _evaluation_detail(change)
        rows.append((change.parameter, value, f"{_local_time(change.at)} · {verdict}"))
    return rows or [("Wijzigingen", "Geen items in deze periode", "")]


def _cycle_rows(report: ReportSnapshot) -> list[tuple[str, str, str]]:
    rows = [
        (
            f"{_mode_text(cycle.mode.value)}-cyclus {cycle.number}",
            f"{_decimal(cycle.duration_s)} s",
            f"{_cycle_class_text(cycle.classification.value)} · "
            f"{_end_reason_text(cycle.end_reason.value)} · {_cycle_details(cycle)}"
            + (" · duur is ondergrens" if cycle.duration_is_lower_bound else ""),
        )
        for cycle in report.cycles
    ]
    if report.has_more_cycles:
        rows.append(("Cycli", "Meer dan 500", "Niet alle cycli staan in deze export."))
    return rows or [("Cycli", "Geen cycli in deze periode", "")]


def _unknown(value: float | int | None) -> str:
    return "Onbekend" if value is None else _decimal(value)


def _cycle_details(cycle: Any) -> str:
    fields = [
        f"max. aanvoer {_unknown(cycle.max_flow_temperature)} °C",
        f"gewenste aanvoer {_unknown(cycle.flow_setpoint)} °C",
        f"gem. modulatie {_unknown(cycle.mean_modulation_pct)} %",
        f"warmtevraag {'ja' if cycle.short_during_demand else 'nee'}",
    ]
    return "; ".join(fields)


def _status_text(status: str) -> str:
    return {
        "open": "Open",
        "accepted": "Geaccepteerd",
        "postponed": "Uitgesteld",
        "done": "Uitgevoerd",
        "rejected": "Afgewezen",
        "rollback_triggered": "Terugdraaien aanbevolen",
    }.get(status, status)


def _verdict_text(verdict: str) -> str:
    return {
        "pending": "Evaluatie loopt",
        "improved": "Verbeterd",
        "worsened": "Verslechterd",
        "trade_off": "Afweging",
        "not_attributable": "Niet toe te schrijven",
        "insufficient_evidence": "Onvoldoende bewijs",
    }.get(verdict, verdict)


def _severity_text(severity: str) -> str:
    return {"high": "Hoog", "medium": "Middel", "low": "Laag", "info": "Info"}.get(
        severity, severity
    )


def _certainty_text(certainty: str) -> str:
    return {
        "insufficient_evidence": "Onvoldoende bewijs",
        "preliminary": "Voorlopig",
        "moderate": "Matig",
        "reasonable": "Redelijk",
        "high": "Hoog",
        "high_measured": "Hoog (gemeten)",
    }.get(certainty, certainty)


def _mode_text(mode: str) -> str:
    return {
        "ch": "CV",
        "dhw": "Tapwater",
        "standby": "Stand-by",
        "afterrun": "Naloop",
        "fault_blocking": "Blokkering/storing",
        "unknown": "Onbekend",
    }.get(mode, mode)


def _cycle_class_text(cycle_class: str) -> str:
    return {
        "short": "Kort",
        "normal": "Normaal",
        "excluded": "Uitgesloten",
        "incomplete": "Onvolledig",
    }.get(cycle_class, cycle_class)


def _end_reason_text(reason: str) -> str:
    return {
        "stop_during_demand": "Stop tijdens warmtevraag",
        "demand_ended": "Warmtevraag geëindigd",
        "dhw_ended": "Tapwater geëindigd",
        "data_gap": "Datagat",
        "undetermined": "Onbekend",
    }.get(reason, reason)


def _coverage_detail(segments: Any) -> str:
    return "; ".join(
        f"{_local_time(segment.start)}–{_local_time(segment.end)}: {segment.kind.value}"  # noqa: RUF001
        for segment in segments
    )


def _pdf_section(
    story: list[Any], title: str, rows: list[tuple[str, str, str]], styles: Any
) -> None:
    story.extend((Paragraph(xml_escape(title), styles["ReportHeading"]), Spacer(1, 2 * mm)))
    table_data: list[list[Any]] = [["Onderdeel", "Waarde", "Toelichting"]]
    table_data.extend(
        [Paragraph(xml_escape(cell or "—"), styles["ReportBody"]) for cell in row] for row in rows
    )
    table = Table(table_data, colWidths=(54 * mm, 55 * mm, 65 * mm), repeatRows=1, hAlign=TA_LEFT)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf3f2")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#173835")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c7d3d1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.extend((table, Spacer(1, 5 * mm)))


def _html_section(title: str, body: str) -> str:
    return f"<section><h2>{escape(title)}</h2>{body}</section>"


def _html_table(headers: tuple[str, ...], rows: Sequence[tuple[str, ...]]) -> str:
    row_data = list(rows)
    if not row_data:
        row_data = [("Geen items in deze periode",) + ("",) * (len(headers) - 1)]
    head = "".join(f'<th scope="col">{escape(value)}</th>' for value in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(value or '—')}</td>" for value in row) + "</tr>"
        for row in row_data
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _summary_html(report: ReportSnapshot) -> str:
    rows = [(label, value, unit) for label, value, unit in _summary_rows(report)]
    return _html_table(("Kengetal", "Waarde", "Eenheid"), rows)


def _quality_html(report: ReportSnapshot) -> str:
    rows = [
        (
            signal.name,
            ", ".join(signal.signal_ids),
            _unknown(signal.coverage_pct),
            _coverage_detail(signal.segments)
            or ("%" if signal.coverage_pct is not None else "Onbekend"),
        )
        for signal in report.quality.coverage
    ]
    rows.insert(
        0,
        (
            "Kernsignaaldekking",
            "",
            _unknown(report.quality.core_coverage_pct),
            "%" if report.quality.core_coverage_pct is not None else "",
        ),
    )
    rows.extend(
        (
            event.title,
            ", ".join(event.signal_ids),
            event.consequence,
            f"{_local_time(event.at)}"
            + (f" t/m {_local_time(event.end)}" if event.end else "")
            + (" · hersteld" if event.recovered else " · actief"),
        )
        for event in report.quality.events
    )
    rows.extend(
        (f"Bedrijfsmodus · {share.label}", "", _decimal(share.share_pct), "%")
        for share in report.quality.mode_share
    )
    rows.append(("Vlamstatusresolutie", "", report.quality.flame_resolution_text, ""))
    if not rows:
        rows.append(("Gegevenskwaliteit", "", "Onbekend", ""))
    return _html_section(
        "Gegevenskwaliteit",
        _html_table(("Signaal of gebeurtenis", "Signalen", "Waarde", "Datagaten"), rows),
    )


def _findings_html(report: ReportSnapshot) -> str:
    rows = [
        (
            finding.id,
            finding.title,
            finding.status_text,
            _severity_text(finding.severity.value),
            _certainty_text(finding.certainty.value),
        )
        for finding in report.findings
    ]
    rows.extend(
        (
            advice.finding_id,
            advice.title,
            advice.status.value,
            advice.action,
            "; ".join(
                part
                for part in (
                    f"Herstelcriterium: {advice.success_criterion}"
                    if advice.success_criterion
                    else "",
                    f"Terugdraaicriterium: {advice.rollback_criterion}"
                    if advice.rollback_criterion
                    else "",
                    f"Ontbrekende signalen: {', '.join(advice.missing_signals)}"
                    if advice.missing_signals
                    else "",
                )
                if part
            ),
        )
        for advice in report.open_advice
    )
    rows.extend(
        (
            change.finding_id,
            change.title,
            _status_text(change.status.value),
            _local_time(change.at),
            "",
        )
        for change in report.status_changes
    )
    return _html_section(
        "Bevindingen en adviezen",
        _html_table(
            ("ID", "Titel", "Status", "Ernst/advies", "Zekerheid/ontbrekende signalen"), rows
        ),
    )


def _changes_html(report: ReportSnapshot) -> str:
    rows = []
    for change in report.changes:
        verdict = _evaluation_detail(change)
        rows.append(
            (
                change.change_id,
                _local_time(change.at),
                change.parameter,
                f"{change.old_value} → {change.new_value}",
                verdict,
                change.reason,
            )
        )
    return _html_section(
        "Wijzigingen en evaluaties",
        _html_table(("ID", "Tijdstip", "Parameter", "Voor → na", "Oordeel", "Reden"), rows),
    )


def _cycles_html(report: ReportSnapshot) -> str:
    rows = [
        (
            str(cycle.number),
            _mode_text(cycle.mode.value),
            _local_time(cycle.start),
            "Onbekend" if cycle.end is None else _local_time(cycle.end),
            f"{_decimal(cycle.duration_s)} s",
            _cycle_class_text(cycle.classification.value),
            _end_reason_text(cycle.end_reason.value),
            _cycle_details(cycle),
        )
        for cycle in report.cycles
    ]
    section = _html_section(
        "Cycli",
        _html_table(
            (
                "Nr.",
                "Modus",
                "Start",
                "Einde",
                "Duur",
                "Classificatie",
                "Eindreden",
                "Metingen",
            ),
            rows,
        ),
    )
    if report.has_more_cycles:
        section += "<p>Er zijn meer cycli dan in deze rapportexport zijn opgenomen.</p>"
    return section


_REPORT_CSS = """
:root { color-scheme: light; font-family: system-ui, sans-serif; color: #173835; }
body { margin: 0; background: #f4f7f6; line-height: 1.5; }
main { max-width: 1100px; margin: 0 auto; padding: 2rem; background: white; }
h1, h2 { color: #173835; }
header { border-bottom: 2px solid #90b9b2; margin-bottom: 1.5rem; }
.period { font-size: 1.25rem; font-weight: 700; }
section { margin: 2rem 0; break-inside: avoid; }
table { width: 100%; border-collapse: collapse; margin-top: .75rem; }
th, td { border: 1px solid #c7d3d1; padding: .5rem; text-align: left; vertical-align: top; }
th { background: #edf3f2; }
tr:nth-child(even) { background: #f8faf9; }
@media print { body { background: white; } main { padding: 0; } }
"""
