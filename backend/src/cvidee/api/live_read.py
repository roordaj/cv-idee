"""Real monitoring views; unknown intervals never become off time or a green verdict."""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from cvidee.analysis.metrics_cycles import grid_buckets, hourly_cycle_metrics, summarize_cycles
from cvidee.analysis.modes import classify_modes
from cvidee.analysis.quality import apply_quality
from cvidee.analysis.types import (
    AnalysisWindow,
    MetricName,
    Role,
    SignalRef,
    UnknownReason,
)
from cvidee.analysis.types import (
    TimeRange as Range,
)
from cvidee.api.findings_read import FindingsReadModel
from cvidee.api.problems import ProblemError
from cvidee.api.schemas.common import Action, TimeRange
from cvidee.api.schemas.data import (
    CoverageSegment,
    CoverageSegmentKind,
    CycleList,
    CycleSummary,
    ModeShare,
    QualityEvent,
    QualityResponse,
    SignalCoverage,
)
from cvidee.api.schemas.system import (
    Assessment,
    AssessmentLevel,
    AssessmentReason,
    AssessmentReasonCode,
    DataQualityOverview,
    FindingsOverview,
    HaConnectionState,
    HaStatus,
    LiveState,
    LiveStatus,
    LiveValue,
    MqttStatus,
    NextAction,
    OverviewResponse,
    RecomputeStatus,
    SetupState,
    ShellCounts,
    StatusCard,
    StatusResponse,
    TodaySummary,
)
from cvidee.api.timeline_read import TimelineReadModel
from cvidee.config import Settings
from cvidee.findings.stage import StoreTimelines
from cvidee.runner.sources import SourceSettings, build_pipeline_config, load_mapped_signals
from cvidee.settings.repository import current_revision, effective_values, pipeline_settings
from cvidee.signals.backend import SignalsBackend
from cvidee.signals.catalog import BY_ROLE
from cvidee.signals.quality import observed_resolution_ms
from cvidee.store.derived import SqlDerivedDataRepository
from cvidee.store.enums import (
    ConnectionSource,
    ImportStatus,
    Mode,
    RecommendationStatus,
    RunStatus,
    RunTrigger,
    Severity,
)
from cvidee.store.models import AnalysisRun, ConnectionEvent, ImportJob, Observation, SourceEntity

if TYPE_CHECKING:
    from cvidee.ha_export.service import ExportService
    from cvidee.ingest.ha_client import HAClient

AMSTERDAM = ZoneInfo("Europe/Amsterdam")
MODE_LABELS = {
    Mode.CH: "CV-bedrijf",
    Mode.DHW: "Tapwater",
    Mode.STANDBY: "Stand-by",
    Mode.AFTERRUN: "Naloop",
    Mode.FAULT_BLOCKING: "Storing / blokkering",
    Mode.UNKNOWN: "Onbekend",
}


def dt(ts: int | None) -> datetime | None:
    return None if ts is None else datetime.fromtimestamp(ts / 1000, UTC)


def safe_url(value: str | None) -> str | None:
    if value is None:
        return None
    parts = urlsplit(value)
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def _intersect(left: list[tuple[int, int]], right: list[tuple[int, int]]) -> list[tuple[int, int]]:
    result = []
    i = j = 0
    while i < len(left) and j < len(right):
        start, end = max(left[i][0], right[j][0]), min(left[i][1], right[j][1])
        if start < end:
            result.append((start, end))
        if left[i][1] <= right[j][1]:
            i += 1
        else:
            j += 1
    return result


class ReadWindow:
    def __init__(self, session: Session, start: int, end: int) -> None:
        self.start, self.end = start, end
        self.range = Range(start, end)
        self.window = AnalysisWindow(start, start, end)
        self.settings = effective_values(current_revision(session))
        self.mapped = load_mapped_signals(session)
        self.config = build_pipeline_config(
            session, self.mapped, SourceSettings(), base=pipeline_settings(None, self.settings)
        )
        raw = StoreTimelines(session, self.mapped, SourceSettings(), self.config, end).build(
            self.range
        )
        checked = apply_quality(tuple(raw.values()), self.config, self.window)
        self.timelines = {t.signal: t for t in checked.timelines}
        self.modes = classify_modes(checked.timelines, self.config, self.window)
        self.cycles = SqlDerivedDataRepository(session).burner_cycles(start, end)
        flame = self.timelines.get(SignalRef(Role.FLAME))
        self.flame_mapped = any(
            m.signal == SignalRef(Role.FLAME) and m.valid_at(end - 1) for m in self.mapped
        )
        self.resolution = None
        if flame is not None:
            mapping = next(
                (
                    m
                    for m in reversed(self.mapped)
                    if m.signal == flame.signal and m.valid_at(end - 1)
                ),
                None,
            )
            if mapping:
                self.resolution = observed_resolution_ms(session, mapping, self.range, flame)
        known = [(start, end)]
        for role in (Role.FLAME, Role.OPERATING_MODE, Role.FLOW_TEMPERATURE):
            timeline = self.timelines.get(SignalRef(role))
            known = _intersect(
                known, [] if timeline is None else [(v.start, v.end) for v in timeline.values]
            )
        known = _intersect(
            known, [(m.start, m.end) for m in self.modes if m.mode is not Mode.UNKNOWN]
        )
        self.known_ms = sum(b - a for a, b in known)
        self.coverage = self.known_ms / self.range.duration_ms
        self.has_data = any(t.values for t in self.timelines.values())
        self.mode = self.modes[-1].mode if self.modes else Mode.UNKNOWN
        self.mode_since = None if not self.modes else self.modes[-1].start
        successful_horizon = session.scalar(
            select(func.max(AnalysisRun.horizon_ts)).where(
                AnalysisRun.status == RunStatus.SUCCEEDED
            )
        )
        self.metric_end = min(end, successful_horizon) if successful_horizon else start
        self.derived = successful_horizon is not None and successful_horizon > start
        hourly = (
            ()
            if flame is None
            else hourly_cycle_metrics(
                self.cycles,
                self.modes,
                flame,
                self.timelines.get(SignalRef(Role.HEAT_DEMAND)),
                grid_buckets(AnalysisWindow(start, start, self.metric_end), self.config.grid_ms)
                if self.metric_end > start
                else (),
                self.config,
            )
        )
        self.metrics = (
            {
                m.name: m
                for m in summarize_cycles(
                    self.cycles,
                    hourly,
                    Range(start, self.metric_end),
                    self.config,
                    short_cycle_ms=round(self.settings.short_cycle_min * 60_000),
                )
                if m.mode is Mode.CH
            }
            if self.metric_end > start
            else {}
        )

    def assessment(self, connected: bool) -> Assessment:
        reasons = []

        def reason(code: AssessmentReasonCode, text: str, action: Action | None = None) -> None:
            reasons.append(AssessmentReason(code=code, text=text, action=action))

        hours = self.known_ms / 3_600_000
        if not self.flame_mapped:
            reason(
                AssessmentReasonCode.FLAME_NOT_MAPPED,
                "Vlamstatus is niet gekoppeld.",
                Action(label="Koppelen", target="/signalen"),
            )
        if hours < self.settings.min_observation_hours:
            reason(
                AssessmentReasonCode.TOO_FEW_HOURS,
                (
                    f"Pas {hours:.1f} van {self.settings.min_observation_hours:g} uur met gegevens."
                ).replace(".", ","),
                Action(label="Historie importeren", target="/kwaliteit#import"),
            )
        if self.coverage * 100 < self.settings.min_assessment_coverage_pct:
            reason(
                AssessmentReasonCode.LOW_COVERAGE,
                (
                    f"Dekking {round(self.coverage * 100)} % "
                    f"(minimaal {self.settings.min_assessment_coverage_pct} %)."
                ),
                Action(label="Gegevenskwaliteit", target="/kwaliteit"),
            )
        if not self.has_data:
            reason(
                AssessmentReasonCode.NO_DATA_YET, "Nog geen gegevens ontvangen uit Home Assistant."
            )
        elif not self.derived:
            reason(
                AssessmentReasonCode.NO_DATA_YET,
                "De ontvangen gegevens zijn nog niet geanalyseerd.",
            )
        if self.flame_mapped and (
            self.resolution is None or self.resolution > self.settings.flame_resolution_s * 1000
        ):
            reason(
                AssessmentReasonCode.FLAME_RESOLUTION_INSUFFICIENT,
                "De werkelijke meetresolutie van de vlamstatus is nog niet voldoende aangetoond.",
                Action(label="Signalen controleren", target="/signalen"),
            )
        insufficient = bool(reasons)
        if not connected:
            reason(
                AssessmentReasonCode.HA_DISCONNECTED,
                "Geen verbinding met Home Assistant; actuele gegevens zijn onbekend.",
            )
        if self.coverage < 1:
            reason(
                AssessmentReasonCode.DATA_GAP,
                "Niet alle tijd is waargenomen. Onbekende tijd telt niet als uit.",
            )
        return Assessment(
            level=AssessmentLevel.INSUFFICIENT_DATA
            if insufficient
            else AssessmentLevel.LIMITED
            if reasons
            else AssessmentLevel.SUFFICIENT,
            reasons=reasons,
            observed_hours=hours,
            minimum_hours=self.settings.min_observation_hours,
            coverage_pct=round(self.coverage * 100, 1) if self.mapped else None,
        )


class LiveReadModel:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        client: HAClient | None,
        export: ExportService | None,
        clock: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    ) -> None:
        self.sessions, self.settings, self.client, self.export, self.clock = (
            sessions,
            settings,
            client,
            export,
            clock,
        )

    @property
    def connected(self) -> bool:
        return self.client is not None and self.client.connected

    def _bounds(self, start: datetime | None, end: datetime | None) -> tuple[int, int]:
        now = self.clock()
        hi = now if end is None else round(end.timestamp() * 1000)
        lo = hi - 24 * 3_600_000 if start is None else round(start.timestamp() * 1000)
        if lo >= hi or hi - lo > 31 * 86_400_000 or hi > now:
            raise ProblemError(
                422,
                "Ongeldig tijdvak",
                "Kies een voltooid tijdvak van maximaal 31 dagen met begin vóór einde.",
            )
        return lo, hi

    @staticmethod
    def _first(session: Session, now: int) -> int | None:
        mapped = load_mapped_signals(session)
        if not mapped:
            return None
        conditions = [
            (SourceEntity.entity_id == m.entity_id)
            & (Observation.ts >= m.valid_from)
            & (Observation.ts < min(now, m.valid_to or now))
            for m in mapped
        ]
        return session.scalar(
            select(func.min(Observation.ts))
            .join(SourceEntity, SourceEntity.id == Observation.source_entity_id)
            .where(or_(*conditions))
        )

    def _setup(self, session: Session, window: ReadWindow) -> SetupState:
        revision = current_revision(session)
        imported = (
            session.scalar(
                select(ImportJob.id).where(ImportJob.status == ImportStatus.DONE).limit(1)
            )
            is not None
        )
        done = revision is not None and revision.onboarding_completed_at_ts is not None
        return SetupState(
            onboarding_done=done,
            onboarding_completed_at=None
            if revision is None
            else dt(revision.onboarding_completed_at_ts),
            flame_mapped=window.flame_mapped,
            history_imported=imported,
            steps_done=int(self.connected) + int(window.flame_mapped) + int(imported or done),
        )

    def status(self) -> StatusResponse:
        now = self.clock()
        local = datetime.fromtimestamp(now / 1000, UTC).astimezone(AMSTERDAM)
        midnight = round(
            local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000
        )
        with self.sessions() as session:
            first = self._first(session, now)
            lo = max(midnight, first or midnight)
            window = ReadWindow(session, min(lo, now - 1), now)
            signals = SignalsBackend(self.sessions, clock=self.clock).signal_list()
            findings = FindingsReadModel(session, self.clock, refresh_status=False).finding_list()
            latest = session.scalar(select(AnalysisRun).order_by(AnalysisRun.id.desc()).limit(1))
            active_import = session.scalar(
                select(ImportJob)
                .where(
                    ImportJob.status.in_(
                        (ImportStatus.PENDING, ImportStatus.FETCHING, ImportStatus.ANALYSING)
                    )
                )
                .order_by(ImportJob.id.desc())
                .limit(1)
            )
            mapped = load_mapped_signals(session)
            last = (
                session.scalar(
                    select(func.max(Observation.ts))
                    .join(SourceEntity, SourceEntity.id == Observation.source_entity_id)
                    .where(
                        or_(
                            *(
                                (SourceEntity.entity_id == m.entity_id)
                                & (Observation.ts >= m.valid_from)
                                & (Observation.ts < (m.valid_to or now))
                                for m in mapped
                            )
                        )
                    )
                )
                if mapped
                else None
            )
            connection = session.scalar(
                select(ConnectionEvent)
                .where(ConnectionEvent.source == ConnectionSource.WS)
                .order_by(ConnectionEvent.ts.desc())
                .limit(1)
            )
            live = (
                LiveState.LIVE
                if self.connected and last is not None and now - last <= 120_000
                else LiveState.DELAYED
                if self.connected
                else LiveState.HA_OFFLINE
            )
            progress = None
            if active_import:
                live = LiveState.IMPORTING
                progress = (
                    None
                    if not active_import.blocks_total
                    else active_import.blocks_done / active_import.blocks_total * 100
                )
            elif (
                latest
                and latest.status in (RunStatus.QUEUED, RunStatus.RUNNING)
                and latest.trigger == RunTrigger.RECOMPUTE
            ):
                live = LiveState.RECOMPUTING
            export = None if self.export is None else self.export.snapshot()
            return StatusResponse(
                now=datetime.fromtimestamp(now / 1000, UTC),
                stub_data=False,
                live=LiveStatus(
                    state=live,
                    last_data_at=dt(last),
                    since=None if connection is None else dt(connection.ts),
                    progress_pct=progress,
                ),
                source_text="Gegevens via Home Assistant"
                if self.settings.ha_configured
                else "Home Assistant nog niet ingesteld",
                operating_mode=window.mode if self.connected else Mode.UNKNOWN,
                operating_mode_since=dt(window.mode_since) if self.connected else None,
                coverage_today_pct=round(window.coverage * 100, 1) if window.mapped else None,
                counts=ShellCounts(
                    open_findings=findings.open_count,
                    signals_linked=signals.linked,
                    signals_total=signals.total,
                ),
                setup=self._setup(session, window),
                ha=HaStatus(
                    state=HaConnectionState.CONNECTED
                    if self.connected
                    else HaConnectionState.UNREACHABLE,
                    deployment=self.settings.mode.value,
                    version=None,
                    url=safe_url(self.settings.ha_url),
                ),
                mqtt=MqttStatus(
                    broker_found=export is not None and export.transport == "mqtt",
                    connected=export is not None and export.connected,
                    export_mode="none" if export is None else export.transport,
                ),
                recompute=RecomputeStatus(
                    status=latest.status,
                    started_at=dt(latest.started_at_ts),
                    reason_text=latest.reason,
                )
                if latest is not None
                and latest.trigger == RunTrigger.RECOMPUTE
                and latest.status in (RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.FAILED)
                else None,
                active_import_id=None if active_import is None else str(active_import.id),
            )

    def quality(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> QualityResponse:
        lo, hi = self._bounds(start, end)
        with self.sessions() as session:
            window = ReadWindow(session, lo, hi)
            coverage = []
            for signal, timeline in sorted(window.timelines.items()):
                info = BY_ROLE[signal.role]
                coverage.append(
                    SignalCoverage(
                        name=info.name
                        if signal.scope.key is None
                        else f"{info.name} {signal.scope.key}",
                        signal_ids=[str(signal)],
                        coverage_pct=sum(v.end - v.start for v in timeline.values)
                        / (hi - lo)
                        * 100,
                        segments=[
                            CoverageSegment(
                                start=datetime.fromtimestamp(i.start / 1000, UTC),
                                end=datetime.fromtimestamp(i.end / 1000, UTC),
                                kind=CoverageSegmentKind.STALE
                                if i.reason == UnknownReason.STALE
                                else CoverageSegmentKind.CONNECTION_LOST
                                if i.reason == UnknownReason.DISCONNECTED
                                else CoverageSegmentKind.DATA_GAP
                                if i.reason == UnknownReason.NO_DATA
                                else CoverageSegmentKind.UNKNOWN,
                            )
                            for i in timeline.unknowns
                        ],
                    )
                )
            existing = {signal_id for row in coverage for signal_id in row.signal_ids}
            for item in SignalsBackend(self.sessions, clock=self.clock).signal_list().items:
                if item.entity_id is None and item.id not in existing:
                    coverage.append(
                        SignalCoverage(
                            name=item.name,
                            signal_ids=[item.id],
                            coverage_pct=None,
                            segments=[
                                CoverageSegment(
                                    start=datetime.fromtimestamp(lo / 1000, UTC),
                                    end=datetime.fromtimestamp(hi / 1000, UTC),
                                    kind=CoverageSegmentKind.NOT_MAPPED,
                                )
                            ],
                        )
                    )
            events = [
                QualityEvent(
                    kind=e.kind,
                    title={
                        "connection_lost": "Verbinding onderbroken",
                        "stale": "Verouderde gegevens",
                        "implausible": "Onwaarschijnlijke waarde",
                        "data_gap": "Geen gegevens beschikbaar",
                        "invalid": "Ongeldige meetwaarde",
                        "unavailable": "Signaal niet beschikbaar",
                        "counter_reset": "Teller opnieuw gestart",
                    }.get(e.kind.value, e.kind.value.replace("_", " ").capitalize()),
                    consequence=e.detail,
                    at=datetime.fromtimestamp(e.start / 1000, UTC),
                    end=dt(e.end),
                    signal_ids=[] if e.signal is None else [str(e.signal)],
                )
                for e in SqlDerivedDataRepository(session).quality_events(lo, hi)
            ]
            minutes: defaultdict[Mode, float] = defaultdict(float)
            for mode in window.modes:
                minutes[mode.mode] += (mode.end - mode.start) / 60_000
            interval = TimeRange(
                start=datetime.fromtimestamp(lo / 1000, UTC),
                end=datetime.fromtimestamp(hi / 1000, UTC),
            )
            return QualityResponse(
                range=interval,
                core_coverage_pct=round(window.coverage * 100, 1) if window.mapped else None,
                coverage=coverage,
                events=events,
                mode_share_range=interval,
                mode_share=[
                    ModeShare(
                        mode=m,
                        label=MODE_LABELS[m],
                        minutes=n,
                        share_pct=n / ((hi - lo) / 60_000) * 100,
                    )
                    for m, n in minutes.items()
                ],
                flame_resolution_s=None if window.resolution is None else window.resolution / 1000,
                flame_resolution_text="Werkelijke meetresolutie nog onbekend."
                if window.resolution is None
                else f"Mediaan tussen rapporten: {window.resolution / 1000:g} s.".replace(
                    ".", ",", 1
                ),
            )

    def cycles(
        self, limit: int, offset: int, start: datetime | None = None, end: datetime | None = None
    ) -> CycleList:
        lo, hi = self._bounds(start, end)
        with self.sessions() as session:
            window = ReadWindow(session, lo, hi)
            timeline = TimelineReadModel(session, self.clock).timeline(
                datetime.fromtimestamp(lo / 1000, UTC), datetime.fromtimestamp(hi / 1000, UTC)
            )
            items = [c for c in timeline.cycles if c.start.timestamp() * 1000 >= lo]
            metrics = window.metrics

            def value(name: MetricName) -> float | None:
                return metrics[name].value if window.derived else None

            starts_metric = metrics.get(MetricName.STARTS_PER_HOUR)
            return CycleList(
                range=timeline.range,
                summary=CycleSummary(
                    observed_hours=0
                    if starts_metric is None
                    else starts_metric.time_basis_seconds / 3600,
                    starts_per_hour=value(MetricName.STARTS_PER_HOUR),
                    ch_cycles=sum(c.mode == Mode.CH for c in items),
                    dhw_cycles=sum(c.mode == Mode.DHW for c in items),
                    short_during_demand=sum(c.short_during_demand for c in items),
                    short_cycle_threshold_s=window.settings.short_cycle_min * 60,
                    median_burn_s=value(MetricName.BURN_DURATION_MEDIAN),
                    mean_burn_s=value(MetricName.BURN_DURATION_MEAN),
                    median_pause_s=value(MetricName.PAUSE_DURATION_MEDIAN),
                    total_burn_s=value(MetricName.BURN_TIME) or 0,
                    incomplete_cycles=sum(c.duration_is_lower_bound for c in items),
                ),
                items=items[offset : offset + limit],
                total=len(items),
                limit=limit,
                offset=offset,
            )

    def overview(self) -> OverviewResponse:
        now = self.clock()
        with self.sessions() as session:
            first = self._first(session, now)
            lo = max(now - 24 * 3_600_000, first or now - 24 * 3_600_000)
            window = ReadWindow(session, min(lo, now - 1), now)
            assessment = window.assessment(self.connected)
            setup = self._setup(session, window)
            findings = FindingsReadModel(session, self.clock, refresh_status=False).finding_list()
            analyses = SignalsBackend(self.sessions, clock=self.clock).analyses().items
            selected = next(
                (
                    f
                    for f in findings.items
                    if f.status in ("open", "accepted", "rollback_triggered")
                ),
                None,
            )
            next_action = None
            if assessment.level is AssessmentLevel.INSUFFICIENT_DATA:
                next_action = NextAction(
                    kind="setup",
                    title="Koppel de vlamstatus"
                    if not window.flame_mapped
                    else "Verzamel voldoende gegevens",
                    text=(
                        "Ontbrekende gegevens blijven onbekend. Importeer historie "
                        "of wacht op voldoende waarnemingen."
                    ),
                    action=Action(label="Signalen koppelen", target="/signalen")
                    if not window.flame_mapped
                    else Action(label="Historie importeren", target="/kwaliteit#import"),
                )
            elif selected is not None:
                detail = FindingsReadModel(session, self.clock, refresh_status=False).finding(
                    selected.id
                )
                next_action = NextAction(
                    kind="recommendation",
                    title=selected.title,
                    text=detail.recommendation.action
                    if detail.recommendation
                    else detail.no_advice_text or "Bekijk de onderbouwing.",
                    finding_id=selected.id,
                    action=Action(label="Bekijk bevinding", target=f"/bevindingen/{selected.id}"),
                )
            kpis = []
            for signal, timeline in sorted(window.timelines.items()):
                if signal.role not in (
                    Role.FLOW_TEMPERATURE,
                    Role.RETURN_TEMPERATURE,
                    Role.FLOW_SETPOINT,
                    Role.MODULATION,
                    Role.ROOM_TEMPERATURE,
                    Role.OUTDOOR_TEMPERATURE,
                ):
                    continue
                value = timeline.value_at(now - 1)
                info = BY_ROLE[signal.role]
                kpis.append(
                    LiveValue(
                        key=str(signal),
                        signal_id=str(signal),
                        label=info.name
                        if signal.scope.key is None
                        else f"{info.name} {signal.scope.key}",
                        value=float(value)
                        if self.connected
                        and isinstance(value, int | float)
                        and not isinstance(value, bool)
                        else None,
                        unit=info.unit or "",
                        note_text="Gerapporteerd via Home Assistant"
                        if self.connected and value is not None
                        else "Geen actuele gegevens",
                        explanation=(
                            "Actuele waarde uit het gekoppelde signaal; "
                            "onbekende tijd wordt niet ingevuld."
                        ),
                        stale=getattr(timeline.at(now - 1), "reason", None) is UnknownReason.STALE,
                    )
                )
            today_start = round(
                datetime.fromtimestamp(now / 1000, UTC)
                .astimezone(AMSTERDAM)
                .replace(hour=0, minute=0, second=0, microsecond=0)
                .timestamp()
                * 1000
            )
            today_cycles = [c for c in window.cycles if c.start >= today_start]
            good = assessment.level is AssessmentLevel.SUFFICIENT and not findings.items
            title = (
                "Nog geen beoordeling mogelijk"
                if assessment.level is AssessmentLevel.INSUFFICIENT_DATA
                else "Geen bijzonderheden in de afgelopen 24 uur"
                if good
                else MODE_LABELS[window.mode]
            )
            return OverviewResponse(
                window=TimeRange(
                    start=datetime.fromtimestamp(lo / 1000, UTC),
                    end=datetime.fromtimestamp(now / 1000, UTC),
                ),
                assessment=assessment,
                setup=setup,
                status_card=StatusCard(
                    mode=window.mode if self.connected else Mode.UNKNOWN,
                    title=title,
                    text=(
                        "Er zijn nog niet genoeg betrouwbare gegevens "
                        "om te zeggen hoe je installatie draait."
                    )
                    if assessment.level is AssessmentLevel.INSUFFICIENT_DATA
                    else "Bekijk de bevindingen en hun onderbouwing."
                    if findings.items
                    else "Alleen de beschikbare metingen en analyses zijn beoordeeld.",
                ),
                today=TodaySummary(
                    range=TimeRange(
                        start=datetime.fromtimestamp(today_start / 1000, UTC),
                        end=datetime.fromtimestamp(now / 1000, UTC),
                    ),
                    ch_cycles=sum(c.mode == Mode.CH for c in today_cycles),
                    short_during_demand=sum(
                        c.complete
                        and c.end_reason is not None
                        and c.end_reason.value == "stop_during_demand"
                        and c.duration_ms < window.settings.short_cycle_min * 60_000
                        for c in today_cycles
                    ),
                ),
                next_action=next_action,
                kpis=kpis,
                findings=FindingsOverview(
                    open_count=findings.open_count,
                    action_required_count=sum(
                        f.severity is Severity.HIGH
                        or f.status is RecommendationStatus.ROLLBACK_TRIGGERED
                        for f in findings.items
                    ),
                    items=findings.items,
                ),
                data_quality=DataQualityOverview(
                    coverage_pct=assessment.coverage_pct,
                    level=assessment.level,
                    text="Onvoldoende gegevens"
                    if assessment.level is AssessmentLevel.INSUFFICIENT_DATA
                    else "Gegevens beperkt"
                    if assessment.level is AssessmentLevel.LIMITED
                    else "Gegevens voldoende",
                    issues=[],
                ),
                analyses=analyses,
            )
