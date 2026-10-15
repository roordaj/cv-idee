"""Current export values from validated observations and persisted findings."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from cvidee.analysis.metrics_cycles import summarize_cycles
from cvidee.analysis.modes import classify_modes
from cvidee.analysis.pipeline import run_pipeline
from cvidee.analysis.quality import apply_quality
from cvidee.analysis.types import AnalysisWindow, MetricName, Role, SignalRef, TimeRange
from cvidee.findings.stage import StoreTimelines
from cvidee.ha_export.entities import ExportValue
from cvidee.runner.sources import (
    SourceSettings,
    build_pipeline_config,
    load_mapped_signals,
    load_window_input,
)
from cvidee.settings.repository import current_revision, effective_values, pipeline_settings
from cvidee.signals.quality import signal_statuses
from cvidee.store.enums import FindingLifecycle, RecommendationStatus
from cvidee.store.models import Finding


def read_summary(session: Session, now: int) -> dict[str, ExportValue]:
    """A six-hour observed basis, with explicit unknown values when current data fail."""
    values = effective_values(current_revision(session))
    mapped = load_mapped_signals(session)
    sources = SourceSettings()
    config = build_pipeline_config(session, mapped, sources, base=pipeline_settings(None, values))
    end = now - config.settle_ms
    start = end - 6 * 3_600_000
    window = AnalysisWindow(start, start, end)
    observations, events = load_window_input(session, mapped, sources, window)
    result = run_pipeline(observations, events, config, window, now)
    timelines = {t.signal: t for t in result.timelines}
    statuses = {
        s.signal: s for s in signal_statuses(session, mapped, timelines, TimeRange(start, end))
    }
    required = [statuses.get(SignalRef(role)) for role in (Role.FLAME, Role.OPERATING_MODE)]
    coverage = min((s.coverage if s else 0 for s in required), default=0)
    current_window = AnalysisWindow(end, end, now)
    current_raw = StoreTimelines(session, mapped, sources, config, now).build(TimeRange(end, now))
    current = apply_quality(tuple(current_raw.values()), config, current_window).timelines
    current_timelines = {t.signal: t for t in current}
    current_modes = classify_modes(current, config, current_window)
    current_known = all(
        current_timelines.get(SignalRef(role)) is not None
        and current_timelines[SignalRef(role)].value_at(now - 1) is not None
        for role in (Role.FLAME, Role.OPERATING_MODE)
    )
    flame = statuses.get(SignalRef(Role.FLAME))
    fine = (
        flame is not None
        and flame.resolution_ms is not None
        and flame.resolution_ms <= values.short_cycle_min * 30_000
    )
    metrics = {
        m.name: m
        for m in summarize_cycles(
            result.cycles,
            result.metrics,
            TimeRange(start, end),
            config,
            short_cycle_ms=round(values.short_cycle_min * 60_000),
        )
    }
    basis = metrics[MetricName.STARTS_PER_HOUR].time_basis_seconds
    coverage = min(coverage, basis / (6 * 3600))
    adequate = (
        current_known
        and bool(current_modes)
        and current_modes[-1].mode.value != "unknown"
        and coverage >= values.min_assessment_coverage_pct / 100
    )
    metadata = {
        "period_start_ts": start,
        "period_end_ts": end,
        "observed_seconds": basis,
        "coverage_pct": round(coverage * 100, 1),
    }
    demand_status = statuses.get(SignalRef(Role.HEAT_DEMAND)) or statuses.get(
        SignalRef(Role.FLOW_SETPOINT)
    )
    short_supported = (
        demand_status is not None
        and demand_status.coverage >= values.min_assessment_coverage_pct / 100
    )
    output = {}
    for key, metric in (
        ("starts_per_uur", MetricName.STARTS_PER_HOUR),
        ("korte_cycli_6u", MetricName.SHORT_CYCLES),
    ):
        value = metrics[metric].value
        output[key] = ExportValue(
            str(round(value, 2))
            if adequate
            and fine
            and value is not None
            and (key != "korte_cycli_6u" or short_supported)
            else "unknown",
            metadata,
        )
    output["gegevensdekking"] = ExportValue(str(round(coverage * 100, 1)), metadata)
    output["onvoldoende_gegevens"] = ExportValue(
        "off" if adequate and fine and short_supported else "on", metadata
    )
    mode_names = {
        "ch": "cv",
        "dhw": "tapwater",
        "standby": "standby",
        "afterrun": "naloop",
        "fault_blocking": "storing",
        "unknown": "onbekend",
    }
    mode = next(
        (m.mode.value for m in reversed(current_modes) if m.start <= now - 1 < m.end),
        "unknown",
    )
    output["bedrijfsmodus"] = ExportValue(
        mode_names[mode] if current_known else "onbekend", metadata
    )
    findings = list(
        session.scalars(
            select(Finding)
            .where(Finding.lifecycle == FindingLifecycle.ACTIVE)
            .order_by(Finding.priority_score.desc(), Finding.id)
        )
    )
    output["open_bevindingen"] = ExportValue(
        str(len(findings)),
        {
            "findings": [
                {
                    "finding_id": f.human_id,
                    "title": f.title,
                    "certainty": f.certainty.value,
                    "recommendation_statuses": [r.status.value for r in f.recommendations],
                }
                for f in findings
            ]
        },
    )
    severity_order = ("high", "medium", "low", "info")
    severity_names = {"high": "hoog", "medium": "middel", "low": "laag", "info": "info"}
    highest = next(
        (s for s in severity_order if any(f.severity.value == s for f in findings)), None
    )
    output["hoogste_ernst"] = ExportValue("geen" if highest is None else severity_names[highest])
    actions = [
        (f, r)
        for f in findings
        for r in f.recommendations
        if r.status in (RecommendationStatus.OPEN, RecommendationStatus.ACCEPTED)
    ]
    if actions:
        finding, recommendation = actions[0]
        output["volgende_actie"] = ExportValue(
            recommendation.action[:255],
            {
                "finding_id": finding.human_id,
                "title": finding.title,
                "recommendation_status": recommendation.status.value,
                "action": recommendation.action,
            },
        )
    else:
        output["volgende_actie"] = ExportValue(
            "Geen openstaande actie" if adequate else "Controleer de gegevenskwaliteit"
        )
    return output
