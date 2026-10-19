"""Read model for per-cycle zone counts over the active versioned profile."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from cvidee.analysis.quality import apply_quality
from cvidee.analysis.types import (
    AnalysisWindow,
    Role,
    Scope,
    ScopeKind,
    SignalRef,
    SignalTimeline,
    TimeRange,
)
from cvidee.analysis.zone_context import (
    Zone,
    ZoneContextAnalysis,
    ZoneRole,
    analyze_zone_context,
)
from cvidee.api.problems import ProblemError
from cvidee.api.schemas.zone_analysis import (
    IncompleteZoneCount as IncompleteZoneCountResponse,
)
from cvidee.api.schemas.zone_analysis import (
    ZoneAnalysisResponse,
    ZoneSignalRef,
)
from cvidee.api.schemas.zone_analysis import (
    ZoneCountBin as ZoneCountBinResponse,
)
from cvidee.api.schemas.zone_analysis import (
    ZoneSignalAnalysis as ZoneSignalAnalysisResponse,
)
from cvidee.findings.stage import StoreTimelines
from cvidee.installation import SqlInstallationProfileRepository
from cvidee.periods import SqlSpecialPeriodRepository
from cvidee.runner.sources import SourceSettings, build_pipeline_config, load_mapped_signals
from cvidee.settings.repository import current_revision, effective_values, pipeline_settings
from cvidee.store.derived import SqlDerivedDataRepository

MAX_RANGE = timedelta(days=31)
DEFAULT_RANGE = timedelta(days=7)


def _dt(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, UTC)


def _source_response(
    source: ZoneContextAnalysis,
    role: ZoneRole,
    *,
    threshold: int | None,
    count_no: str,
    count_missing: str,
    signals: list[ZoneSignalRef],
) -> ZoneSignalAnalysisResponse:
    metrics = source.zone_demand if role == "zone_demand" else source.valve_state
    return ZoneSignalAnalysisResponse(
        role=role,
        availability=metrics.availability,
        mapped_zone_keys=list(metrics.mapped_zone_keys),
        unmapped_zone_keys=list(metrics.unmapped_zone_keys),
        signals=signals,
        eligible_cycles=metrics.eligible_cycles,
        complete_cycles=metrics.complete_cycles,
        coverage_pct=None if metrics.coverage is None else metrics.coverage * 100,
        distribution=[
            ZoneCountBinResponse(
                active_count=item.active_count,
                cycles=item.cycles,
                short_cycles=item.short_cycles,
                cycle_starts=[_dt(ts) for ts in item.cycle_starts],
                few_active_zones=(None if threshold is None else item.active_count <= threshold),
            )
            for item in metrics.distribution
        ],
        incomplete_cycles=[
            IncompleteZoneCountResponse(
                cycle_start=_dt(item.cycle_start),
                known_active_count=item.known_active_count,
                known_zone_keys=list(item.known_zone_keys),
                missing_zone_keys=list(item.missing_zone_keys),
                short=item.short,
            )
            for item in metrics.incomplete_cycles
        ],
        unknown_demand_cycles=metrics.unknown_demand_cycles,
        note=(count_no if metrics.availability == "not_available" else count_missing)
        if metrics.availability != "available"
        else "Alle geconfigureerde zonewaarden zijn bekend op de beoordeelde cyclusstarts.",
    )


class ZoneAnalysisReadModel:
    def __init__(self, sessions: sessionmaker[Session], clock: Callable[[], int]) -> None:
        self._sessions = sessions
        self._clock = clock

    def analyze(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> ZoneAnalysisResponse:
        end = end or _dt(self._clock())
        start = start or end - DEFAULT_RANGE
        if (
            start.tzinfo is None
            or start.utcoffset() is None
            or end.tzinfo is None
            or end.utcoffset() is None
        ):
            raise ProblemError(422, "Ongeldig tijdvak", "Begin en einde moeten tijdzones bevatten.")
        start, end = start.astimezone(UTC), end.astimezone(UTC)
        if start >= end or end - start > MAX_RANGE:
            raise ProblemError(
                422, "Ongeldig tijdvak", "Kies maximaal 31 dagen met begin vóór einde."
            )
        requested = TimeRange(round(start.timestamp() * 1000), round(end.timestamp() * 1000))

        with self._sessions() as session:
            profiles = SqlInstallationProfileRepository(session)
            profile = profiles.at(requested.end - 1)
            if profile is None:
                profile = profiles.current_or_default(requested.end)
            period_start = max(requested.start, profile.valid_from_ts)
            if period_start >= requested.end:
                raise ProblemError(
                    422, "Geen profiel in tijdvak", "Geen installatieprofiel in dit tijdvak."
                )
            window = TimeRange(period_start, requested.end)
            values = effective_values(current_revision(session))
            sources = SourceSettings()
            mapped = load_mapped_signals(session)
            config = build_pipeline_config(
                session, mapped, sources, base=pipeline_settings(None, values)
            )
            raw = StoreTimelines(session, mapped, sources, config, window.end).build(window)
            checked = apply_quality(
                tuple(raw.values()), config, AnalysisWindow(window.start, window.start, window.end)
            )
            timelines = {timeline.signal: timeline for timeline in checked.timelines}
            zones = tuple(Zone(zone.key, zone.name) for zone in profile.zones)

            def signal_refs(role: Role) -> list[ZoneSignalRef]:
                return [
                    ZoneSignalRef(
                        zone_key=mapping.signal.scope.key or "",
                        signal_id=str(mapping.signal),
                        meaning=mapping.meaning,
                    )
                    for mapping in mapped
                    if mapping.signal.role is role
                    and mapping.signal.scope.kind is ScopeKind.ZONE
                    and mapping.signal.scope.key in {zone.key for zone in zones}
                    and mapping.valid_from < window.end
                    and (mapping.valid_to is None or mapping.valid_to > window.start)
                ]

            def role_timelines(role: Role) -> dict[str, SignalTimeline]:
                return {
                    zone.key: timelines[ref]
                    for zone in zones
                    if (ref := SignalRef(role, Scope(ScopeKind.ZONE, zone.key))) in timelines
                }

            cycles = tuple(
                SqlDerivedDataRepository(session).burner_cycles(window.start, window.end)
            )
            special_periods = SqlSpecialPeriodRepository(session).in_range(window.start, window.end)
            cycles = tuple(
                cycle
                for cycle in cycles
                if not any(
                    period.exclude_from_ch_conclusions
                    and period.start_ts <= cycle.start
                    and (period.end_ts is None or cycle.start < period.end_ts)
                    for period in special_periods
                )
            )
            result = analyze_zone_context(
                zones,
                cycles,
                role_timelines(Role.ZONE_DEMAND),
                role_timelines(Role.VALVE_STATE),
                timelines.get(SignalRef(Role.HEAT_DEMAND)),
                window,
                round(values.short_cycle_min * 60_000),
                values.few_active_zones_max,
            )
            threshold = values.few_active_zones_max
            return ZoneAnalysisResponse(
                start=_dt(window.start),
                end=_dt(window.end),
                profile_version=str(profile.id),
                few_active_zones_max=threshold,
                zone_demand=_source_response(
                    result,
                    "zone_demand",
                    threshold=threshold,
                    count_no="Geen zones of geen beoordeelbare CV-warmtevraagcontext.",
                    count_missing="Warmtevraagstatus ontbreekt of is onbekend.",
                    signals=signal_refs(Role.ZONE_DEMAND),
                ),
                valve_state=_source_response(
                    result,
                    "valve_state",
                    threshold=threshold,
                    count_no="Geen klepstatusmapping of geen beoordeelbare CV-warmtevraagcontext.",
                    count_missing=(
                        "Klepstatus ontbreekt of is onbekend; dit bewijst geen fysieke opening."
                    ),
                    signals=signal_refs(Role.VALVE_STATE),
                ),
                short_cycle_threshold_s=values.short_cycle_min * 60,
                exclusions=[
                    "Tapwater",
                    "Onbekende modus",
                    "Onbekende CV-warmtevraag",
                    "Onvolledige cycli",
                    "Uitgesloten bijzondere perioden",
                ],
                interpretation=(
                    "Zonevraag en gemelde klepstatus zijn aparte meetbronnen. Een samenhang met "
                    "korte cycli stelt geen oorzaak vast; een gemelde klepstatus bewijst geen "
                    "fysieke opening of warmteafgifte."
                ),
            )
