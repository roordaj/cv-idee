"""Room-comfort analysis read model over the current versioned profile."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from cvidee.analysis.modes import classify_modes
from cvidee.analysis.quality import apply_quality
from cvidee.analysis.room_comfort import RoomComfortPeriod, analyze_room_comfort
from cvidee.analysis.types import AnalysisWindow, Role, Scope, ScopeKind, SignalRef, TimeRange
from cvidee.api.problems import ProblemError
from cvidee.api.schemas.comfort import RoomComfortAnalysisResponse, RoomComfortResult
from cvidee.api.schemas.data import RoomComfortOverride
from cvidee.api.schemas.installation import RoomComfort
from cvidee.findings.stage import StoreTimelines
from cvidee.installation import SqlInstallationProfileRepository
from cvidee.periods import SqlSpecialPeriodRepository
from cvidee.runner.sources import SourceSettings, build_pipeline_config, load_mapped_signals
from cvidee.settings.repository import current_revision, effective_values, pipeline_settings
from cvidee.signals.catalog import BY_ROLE

MAX_RANGE = timedelta(days=31)
DEFAULT_RANGE = timedelta(days=7)


class RoomComfortReadModel:
    def __init__(self, sessions: sessionmaker[Session], clock: Callable[[], int]) -> None:
        self._sessions = sessions
        self._clock = clock

    def analyze(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> RoomComfortAnalysisResponse:
        end = end or datetime.fromtimestamp(self._clock() / 1000, UTC)
        start = start or end - DEFAULT_RANGE
        if (
            start.tzinfo is None
            or start.utcoffset() is None
            or end.tzinfo is None
            or end.utcoffset() is None
        ):
            raise ProblemError(
                422, "Ongeldig tijdvak", "Begin en einde moeten een tijdzone bevatten."
            )
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
                    422, "Geen profiel in tijdvak", "Kies een tijdvak binnen de profielperiode."
                )
            window = TimeRange(period_start, requested.end)
            values = effective_values(current_revision(session))
            mapped = load_mapped_signals(session)
            config = build_pipeline_config(
                session,
                mapped,
                SourceSettings(),
                base=pipeline_settings(None, values),
            )
            raw = StoreTimelines(session, mapped, SourceSettings(), config, window.end).build(
                window
            )
            checked = apply_quality(
                tuple(raw.values()), config, AnalysisWindow(window.start, window.start, window.end)
            )
            timelines = {timeline.signal: timeline for timeline in checked.timelines}
            modes = classify_modes(
                checked.timelines, config, AnalysisWindow(window.start, window.start, window.end)
            )
            special_periods = SqlSpecialPeriodRepository(session).in_range(window.start, window.end)
            results: list[RoomComfortResult] = []
            room_details = profile.details.get("rooms", {})
            margin = values.comfort_margin_c
            for room in sorted(profile.rooms, key=lambda item: item.key):
                comfort = RoomComfort.model_validate(
                    room_details.get(room.key, {}).get(
                        "comfort", {"status": "not_configured", "windows": []}
                    )
                )
                target_ref = SignalRef(Role.ROOM_TEMPERATURE, Scope(ScopeKind.ROOM, room.key))
                setpoint_ref = SignalRef(Role.ROOM_SETPOINT, Scope(ScopeKind.ROOM, room.key))
                periods = tuple(
                    RoomComfortPeriod(
                        start=period.start_ts,
                        end=window.end if period.end_ts is None else min(window.end, period.end_ts),
                        excluded=period.exclude_from_ch_conclusions,
                        override_kind=next(
                            (
                                override.kind
                                for raw_override in period.room_overrides
                                if (
                                    override := RoomComfortOverride.model_validate(raw_override)
                                ).room_key
                                == room.key
                            ),
                            None,
                        ),
                        override_target_c=next(
                            (
                                override.target_temperature_c
                                for raw_override in period.room_overrides
                                if (
                                    override := RoomComfortOverride.model_validate(raw_override)
                                ).room_key
                                == room.key
                            ),
                            None,
                        ),
                    )
                    for period in special_periods
                    if period.start_ts < window.end
                    and (period.end_ts is None or period.end_ts > window.start)
                )
                metrics = analyze_room_comfort(
                    room.key,
                    comfort,
                    timelines.get(target_ref) if room.circuit_key is not None else None,
                    timelines.get(setpoint_ref),
                    tuple(modes),
                    window.start,
                    window.end,
                    margin,
                    periods,
                )
                missing = [
                    BY_ROLE[Role.ROOM_TEMPERATURE].name + f" {room.name}"
                    if signal == str(target_ref)
                    else BY_ROLE[Role.ROOM_SETPOINT].name + f" {room.name}"
                    for signal in metrics.missing_signals
                ]
                results.append(
                    RoomComfortResult(
                        room_key=room.key,
                        room_name=room.name,
                        availability=metrics.availability,
                        target_source=metrics.target_source,
                        expected_hours=metrics.expected_ms / 3_600_000,
                        observed_hours=metrics.observed_ms / 3_600_000,
                        coverage_pct=None if metrics.coverage is None else metrics.coverage * 100,
                        comfort_loss_target_hours=_hours(metrics.target_comfort_loss_ms),
                        comfort_loss_setpoint_hours=_hours(metrics.setpoint_comfort_loss_ms),
                        overshoot_target_hours=_hours(metrics.target_overshoot_ms),
                        max_overshoot_target_c=metrics.target_max_overshoot_c,
                        overshoot_setpoint_hours=_hours(metrics.setpoint_overshoot_ms),
                        max_overshoot_setpoint_c=metrics.setpoint_max_overshoot_c,
                        mean_target_deviation_c=metrics.mean_target_deviation_c,
                        mean_setpoint_deviation_c=metrics.mean_setpoint_deviation_c,
                        warmup_mean_minutes=(
                            None
                            if metrics.warmup_mean_ms is None
                            else metrics.warmup_mean_ms / 60_000
                        ),
                        warmup_samples=metrics.warmup_samples,
                        warmup_incomplete=metrics.warmup_incomplete,
                        missing_signals=missing,
                    )
                )
            return RoomComfortAnalysisResponse(
                start=datetime.fromtimestamp(window.start / 1000, UTC),
                end=datetime.fromtimestamp(window.end / 1000, UTC),
                profile_version=str(profile.id),
                comfort_margin_c=margin,
                rooms=results,
            )


def _hours(milliseconds: int | None) -> float | None:
    return None if milliseconds is None else milliseconds / 3_600_000
