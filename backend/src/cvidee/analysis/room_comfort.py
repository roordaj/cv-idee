"""Pure per-room comfort metrics over quality-filtered timelines (FR-17)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from typing import TYPE_CHECKING, Literal
from zoneinfo import ZoneInfo

from cvidee.analysis.types import (
    Mode,
    ModeSegment,
    Role,
    Scope,
    ScopeKind,
    SignalRef,
    SignalTimeline,
    TimeRange,
)

if TYPE_CHECKING:
    from cvidee.api.schemas.installation import RoomComfort

MINUTE_MS = 60_000


@dataclass(frozen=True, slots=True)
class RoomComfortPeriod:
    """A special period and its room-specific target behavior."""

    start: int
    end: int
    excluded: bool
    override_kind: str | None = None
    override_target_c: float | None = None


@dataclass(frozen=True, slots=True)
class RoomComfortMetrics:
    """Observed per-room metrics; durations are milliseconds and unknowns stay ``None``."""

    period: TimeRange
    availability: Literal["available", "limited", "not_available"]
    expected_ms: int
    observed_ms: int
    coverage: float | None
    target_comfort_loss_ms: int | None
    setpoint_comfort_loss_ms: int | None
    target_overshoot_ms: int | None
    target_max_overshoot_c: float | None
    setpoint_overshoot_ms: int | None
    setpoint_max_overshoot_c: float | None
    mean_target_deviation_c: float | None
    mean_setpoint_deviation_c: float | None
    warmup_mean_ms: int | None
    warmup_samples: int
    warmup_incomplete: bool
    target_source: Literal["configured_schedule", "special_period", "not_configured"]
    missing_signals: tuple[str, ...]


def analyze_room_comfort(
    room_key: str,
    comfort: RoomComfort,
    actual: SignalTimeline | None,
    setpoint: SignalTimeline | None,
    modes: tuple[ModeSegment, ...],
    start: int,
    end: int,
    comfort_margin_c: float,
    special_periods: tuple[RoomComfortPeriod, ...] = (),
) -> RoomComfortMetrics:
    """Analyze one room without inferring values across rooms or unknown intervals.

    The requested range is half-open UTC. Schedule boundaries are tested on UTC minute
    edges after conversion to the configured local zone, which applies repeated autumn
    minutes twice in real chronology and naturally skips missing spring minutes.
    """
    if start >= end:
        raise ValueError("Comfort analysis requires start before end.")
    if not math.isfinite(comfort_margin_c) or comfort_margin_c < 0:
        raise ValueError("Comfort margin must be finite and non-negative.")
    target_source: Literal["configured_schedule", "special_period", "not_configured"] = (
        "configured_schedule" if comfort.status == "scheduled" else "not_configured"
    )
    can_analyze = comfort.status == "scheduled" or any(
        period.override_kind == "temporary_target" for period in special_periods
    )
    temp_ref = str(SignalRef(Role.ROOM_TEMPERATURE, Scope(ScopeKind.ROOM, room_key)))
    setpoint_ref = str(SignalRef(Role.ROOM_SETPOINT, Scope(ScopeKind.ROOM, room_key)))
    missing = tuple(
        ref for ref, timeline in ((temp_ref, actual), (setpoint_ref, setpoint)) if timeline is None
    )
    if not can_analyze:
        return RoomComfortMetrics(
            period=TimeRange(start, end),
            availability="not_available",
            expected_ms=0,
            observed_ms=0,
            coverage=None,
            target_comfort_loss_ms=None,
            setpoint_comfort_loss_ms=None,
            target_overshoot_ms=None,
            target_max_overshoot_c=None,
            setpoint_overshoot_ms=None,
            setpoint_max_overshoot_c=None,
            mean_target_deviation_c=None,
            mean_setpoint_deviation_c=None,
            warmup_mean_ms=None,
            warmup_samples=0,
            warmup_incomplete=False,
            target_source=target_source,
            missing_signals=missing,
        )

    points = {start, end}
    points.update(range(((start + MINUTE_MS - 1) // MINUTE_MS) * MINUTE_MS, end, MINUTE_MS))
    for timeline in (actual, setpoint):
        if timeline is not None:
            for interval in timeline.intervals:
                if start < interval.start < end:
                    points.add(interval.start)
                if start < interval.end < end:
                    points.add(interval.end)
    for segment in modes:
        if start < segment.start < end:
            points.add(segment.start)
        if start < segment.end < end:
            points.add(segment.end)
    for period in special_periods:
        if start < period.start < end:
            points.add(period.start)
        if start < period.end < end:
            points.add(period.end)
    ordered = sorted(points)

    expected = observed = target_loss = setpoint_loss = 0
    target_over = setpoint_over = 0
    target_max: float | None = None
    setpoint_max: float | None = None
    target_delta_sum = target_delta_basis = 0.0
    setpoint_delta_sum = setpoint_delta_basis = 0.0
    warmups: list[int] = []
    warmup_incomplete = False
    used_special_target = False
    phase_target: float | None = None
    phase_start: int | None = None
    phase_started_with_value = False
    phase_complete = False

    def finish_phase() -> None:
        nonlocal warmup_incomplete
        if phase_target is None:
            return
        if not phase_complete:
            warmup_incomplete = True

    for lo, hi in pairwise(ordered):
        instant = datetime.fromtimestamp(lo / 1000, UTC)
        active_period = _active_period(special_periods, lo)
        target = _period_target(comfort, instant, active_period)
        excluded = any(
            period.start <= lo < period.end and period.excluded for period in special_periods
        )
        if target is None or excluded:
            finish_phase()
            phase_target = None
            phase_start = None
            phase_started_with_value = False
            phase_complete = False
            continue

        if active_period is not None:
            used_special_target |= active_period.override_kind == "temporary_target"

        expected += hi - lo
        if target != phase_target:
            finish_phase()
            phase_target = target
            phase_start = lo
            phase_complete = False
            start_value = _number(None if actual is None else actual.value_at(lo))
            phase_started_with_value = start_value is not None

        mode = _mode_at(modes, lo)
        if mode in (Mode.DHW, Mode.UNKNOWN):
            if mode is Mode.UNKNOWN and phase_start == lo:
                warmup_incomplete = True
            continue
        actual_value = _number(None if actual is None else actual.value_at(lo))
        setpoint_value = _number(None if setpoint is None else setpoint.value_at(lo))
        if actual_value is None:
            if not phase_complete:
                warmup_incomplete = True
            continue
        observed += hi - lo
        target_delta = actual_value - target
        target_delta_sum += target_delta * (hi - lo)
        target_delta_basis += hi - lo
        if target - actual_value > comfort_margin_c:
            target_loss += hi - lo
        elif actual_value > target:
            target_over += hi - lo
            target_max = max(target_max or 0.0, actual_value - target)
        if setpoint_value is not None:
            setpoint_delta = actual_value - setpoint_value
            setpoint_delta_sum += setpoint_delta * (hi - lo)
            setpoint_delta_basis += hi - lo
            if setpoint_value - actual_value > comfort_margin_c:
                setpoint_loss += hi - lo
            elif actual_value > setpoint_value:
                setpoint_over += hi - lo
                setpoint_max = max(setpoint_max or 0.0, actual_value - setpoint_value)

        if not phase_complete and phase_start is not None:
            if not phase_started_with_value:
                warmup_incomplete = True
            elif actual_value >= target - comfort_margin_c:
                warmups.append(lo - phase_start)
                phase_complete = True

    finish_phase()
    if used_special_target:
        target_source = "special_period"
    availability: Literal["available", "limited", "not_available"] = (
        "not_available"
        if actual is None
        else ("available" if observed == expected and expected > 0 else "limited")
    )
    coverage = observed / expected if expected else None
    return RoomComfortMetrics(
        period=TimeRange(start, end),
        availability=availability,
        expected_ms=expected,
        observed_ms=observed,
        coverage=coverage,
        target_comfort_loss_ms=target_loss if observed else None,
        setpoint_comfort_loss_ms=setpoint_loss if setpoint_delta_basis else None,
        target_overshoot_ms=target_over if observed else None,
        target_max_overshoot_c=target_max,
        setpoint_overshoot_ms=setpoint_over if setpoint_delta_basis else None,
        setpoint_max_overshoot_c=setpoint_max,
        mean_target_deviation_c=(
            target_delta_sum / target_delta_basis if target_delta_basis else None
        ),
        mean_setpoint_deviation_c=(
            setpoint_delta_sum / setpoint_delta_basis if setpoint_delta_basis else None
        ),
        warmup_mean_ms=round(sum(warmups) / len(warmups)) if warmups else None,
        warmup_samples=len(warmups),
        warmup_incomplete=warmup_incomplete,
        target_source=target_source,
        missing_signals=missing,
    )


def _number(value: object | None) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        return None
    return float(value)


def _active_period(
    periods: tuple[RoomComfortPeriod, ...], instant: int
) -> RoomComfortPeriod | None:
    active = [p for p in periods if p.start <= instant < p.end]
    return max(active, key=lambda p: (p.start, p.end)) if active else None


def _period_target(
    comfort: RoomComfort, instant: datetime, period: RoomComfortPeriod | None
) -> float | None:
    if period is not None:
        if period.override_kind == "no_expectation":
            return None
        if period.override_kind == "temporary_target":
            return period.override_target_c
    local = instant.astimezone(ZoneInfo(comfort.timezone))
    minute = local.hour * 60 + local.minute
    for window in comfort.windows:
        start = _minutes(window.start_time)
        end = _minutes(window.end_time)
        if end > start:
            active = local.weekday() in window.weekdays and start <= minute < end
        else:
            active = (local.weekday() in window.weekdays and minute >= start) or (
                (local.weekday() - 1) % 7 in window.weekdays and minute < end
            )
        if active:
            return window.target_temperature_c
    return None


def _minutes(value: str) -> int:
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def _mode_at(segments: tuple[ModeSegment, ...], instant: int) -> Mode:
    return next(
        (segment.mode for segment in segments if segment.start <= instant < segment.end),
        Mode.UNKNOWN,
    )
