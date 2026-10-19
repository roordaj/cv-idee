"""Pure before/after metrics and conservative verdicts (FR-30, FR-32)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from statistics import median
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from cvidee.analysis.room_comfort import RoomComfortPeriod, analyze_room_comfort
from cvidee.analysis.types import (
    OUTDOOR,
    BurnerCycle,
    CyclePhase,
    EndReason,
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

HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS
EVALUATION_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class ComparisonPolicy:
    days: int = 7
    min_coverage: float = 0.9
    weather_delta_c: float = 2.0
    limited_weather_delta_c: float = 4.0
    comfort_deficit_c: float = 0.5
    comfort_limit_h_week: float = 4.0
    short_cycle_s: float = 180.0
    min_observation_hours: float = 6.0


@dataclass(frozen=True, slots=True)
class PeriodMetrics:
    coverage: float
    observed_hours: float
    starts_per_hour: float | None
    median_burn_s: float | None
    short_share: float | None
    flow_stable_c: float | None
    outdoor_c: float | None
    outdoor_coverage: float
    cold_hours: tuple[tuple[str, float | None], ...]
    room_coverage: tuple[tuple[str, float], ...]
    setpoints: tuple[tuple[str, float | None], ...]
    cycles: int
    excluded_ms: int
    flame_resolution_ms: int | None = None
    setpoint_values: tuple[tuple[str, tuple[float, ...]], ...] = ()
    setpoint_profile: tuple[tuple[str, tuple[tuple[int, float], ...]], ...] = ()
    comfort_profile_mixed: bool = False


@dataclass(frozen=True, slots=True)
class EvaluationFact:
    change_id: str
    reference: TimeRange
    observation: TimeRange
    before: PeriodMetrics
    after: PeriodMetrics
    verdict: str
    weather: str
    setpoints: str
    overlap_ids: tuple[str, ...]
    rollback: bool
    summary: str
    policy: ComparisonPolicy = ComparisonPolicy()


def eligible_ranges(window: TimeRange, exclusions: Sequence[TimeRange]) -> tuple[TimeRange, ...]:
    pieces = [window]
    for cut in sorted(exclusions, key=lambda r: r.start):
        result = []
        for piece in pieces:
            overlap = piece.intersect(cut)
            if overlap is None:
                result.append(piece)
            else:
                if piece.start < overlap.start:
                    result.append(TimeRange(piece.start, overlap.start))
                if overlap.end < piece.end:
                    result.append(TimeRange(overlap.end, piece.end))
        pieces = result
    return tuple(pieces)


def _merge(ranges: Sequence[TimeRange]) -> tuple[TimeRange, ...]:
    merged: list[TimeRange] = []
    for rng in sorted(ranges, key=lambda r: r.start):
        if merged and rng.start <= merged[-1].end:
            merged[-1] = TimeRange(merged[-1].start, max(rng.end, merged[-1].end))
        else:
            merged.append(rng)
    return tuple(merged)


def _intersect(a: Sequence[TimeRange], b: Sequence[TimeRange]) -> tuple[TimeRange, ...]:
    left, right = _merge(a), _merge(b)
    i, j, result = 0, 0, []
    while i < len(left) and j < len(right):
        overlap = left[i].intersect(right[j])
        if overlap is not None:
            result.append(overlap)
        if left[i].end <= right[j].end:
            i += 1
        else:
            j += 1
    return tuple(result)


def _duration(ranges: Sequence[TimeRange]) -> int:
    return sum(r.duration_ms for r in ranges)


def _known(timeline: SignalTimeline | None) -> tuple[TimeRange, ...]:
    return () if timeline is None else _merge([TimeRange(i.start, i.end) for i in timeline.values])


def _mean(timeline: SignalTimeline | None, ranges: Sequence[TimeRange]) -> float | None:
    if timeline is None:
        return None
    total, weight = 0.0, 0
    for interval in timeline.values:
        if isinstance(interval.value, bool) or not isinstance(interval.value, int | float):
            continue
        duration = _duration(_intersect((TimeRange(interval.start, interval.end),), ranges))
        total += interval.value * duration
        weight += duration
    return total / weight if weight else None


def _reference_profile(
    timeline: SignalTimeline | None, ranges: Sequence[TimeRange]
) -> tuple[tuple[float, ...], tuple[tuple[int, float], ...]]:
    """Compare local weekday/quarter-hour targets; a mean alone can hide a schedule change."""
    levels: set[float] = set()
    totals: dict[int, tuple[float, int]] = {}
    if timeline is not None:
        for interval in timeline.values:
            value = interval.value
            if isinstance(value, bool) or not isinstance(value, int | float):
                continue
            for piece in _intersect((TimeRange(interval.start, interval.end),), ranges):
                levels.add(float(value))
                cursor = piece.start
                while cursor < piece.end:
                    end = min(piece.end, (cursor // 900_000 + 1) * 900_000)
                    local = datetime.fromtimestamp(cursor / 1000, UTC).astimezone(
                        ZoneInfo("Europe/Amsterdam")
                    )
                    key = local.weekday() * 96 + local.hour * 4 + local.minute // 15
                    total, weight = totals.get(key, (0.0, 0))
                    totals[key] = (total + value * (end - cursor), weight + end - cursor)
                    cursor = end
    return tuple(sorted(levels)), tuple(
        (key, total / weight) for key, (total, weight) in sorted(totals.items())
    )


def period_metrics(
    window: TimeRange,
    timelines: Sequence[SignalTimeline],
    cycles: Sequence[BurnerCycle],
    modes: Sequence[ModeSegment],
    exclusions: Sequence[TimeRange],
    policy: ComparisonPolicy,
    room_comfort: dict[str, RoomComfort] | None = None,
    comfort_periods: dict[str, tuple[RoomComfortPeriod, ...]] | None = None,
    comfort_profile_mixed: bool = False,
) -> PeriodMetrics:
    by_signal = {t.signal: t for t in timelines}
    eligible = eligible_ranges(window, exclusions)
    eligible_ms = _duration(eligible)
    known_core = eligible
    for role in (Role.FLAME, Role.OPERATING_MODE, Role.HEAT_DEMAND):
        known_core = _intersect(known_core, _known(by_signal.get(SignalRef(role))))
    coverage = _duration(known_core) / eligible_ms if eligible_ms else 0.0
    demand = by_signal.get(SignalRef(Role.HEAT_DEMAND))
    demand_ranges = (
        ()
        if demand is None
        else tuple(TimeRange(i.start, i.end) for i in demand.values if i.value is True)
    )
    heating = known_core
    heating = _intersect(heating, demand_ranges)
    heating = _intersect(
        heating, tuple(TimeRange(m.start, m.end) for m in modes if m.mode is Mode.CH)
    )
    hours = _duration(heating) / HOUR_MS
    relevant = [
        c
        for c in cycles
        if c.mode is Mode.CH
        and window.contains(c.start)
        and not any(c.start < cut.end and (c.end or window.end) > cut.start for cut in exclusions)
    ]
    complete = [c for c in relevant if c.complete and c.end is not None and c.end <= window.end]
    starts = sum(c.counts_as_start for c in relevant)
    short = sum(
        c.end_reason is EndReason.STOP_DURING_DEMAND and c.duration_ms < policy.short_cycle_s * 1000
        for c in complete
    )
    stable = [
        TimeRange(p.start, p.end)
        for c in complete
        for p in c.phases
        if p.phase is CyclePhase.STABLE
    ]
    outdoor = by_signal.get(SignalRef(Role.OUTDOOR_TEMPERATURE, OUTDOOR))
    cold_hours: list[tuple[str, float | None]] = []
    room_coverage: list[tuple[str, float]] = []
    setpoints: list[tuple[str, float | None]] = []
    setpoint_values = []
    setpoint_profile = []
    rooms = sorted(
        {
            t.signal.scope.key
            for t in timelines
            if t.signal.role in (Role.ROOM_TEMPERATURE, Role.ROOM_SETPOINT)
            and t.signal.scope.key is not None
        }
    )
    for room in rooms:
        actual_ref = SignalRef(Role.ROOM_TEMPERATURE, Scope(ScopeKind.ROOM, room))
        target_ref = SignalRef(Role.ROOM_SETPOINT, Scope(ScopeKind.ROOM, room))
        actual, target = by_signal.get(actual_ref), by_signal.get(target_ref)
        setpoints.append((room, _mean(target, eligible)))
        levels, profile = _reference_profile(target, eligible)
        setpoint_values.append((room, levels))
        setpoint_profile.append((room, profile))
        known_ms, cold_ms = 0, 0
        if actual is not None and target is not None:
            cuts = sorted(
                {
                    window.start,
                    window.end,
                    *(
                        v
                        for t in (actual, target)
                        for i in t.intervals
                        for v in (i.start, i.end)
                        if window.start <= v <= window.end
                    ),
                    *(v for r in eligible for v in (r.start, r.end)),
                }
            )
            for lo, hi in pairwise(cuts):
                if not any(r.contains(lo) for r in eligible):
                    continue
                # A setpoint is a reference state valid over this interval, not a
                # simultaneous physical measurement such as flow/return temperature.
                actual_value, target_value = actual.value_at(lo), target.value_at(lo)
                if (
                    isinstance(actual_value, bool)
                    or isinstance(target_value, bool)
                    or not isinstance(actual_value, int | float)
                    or not isinstance(target_value, int | float)
                ):
                    continue
                known_ms += hi - lo
                if target_value - actual_value > policy.comfort_deficit_c:
                    cold_ms += hi - lo
        cold_hours.append((room, cold_ms / known_ms * 168 if known_ms else None))
        room_coverage.append((room, known_ms / eligible_ms if eligible_ms else 0.0))
    flame_timeline = by_signal.get(SignalRef(Role.FLAME))
    report_times = (
        sorted({i.observed_at for i in flame_timeline.values if window.contains(i.observed_at)})
        if flame_timeline
        else []
    )
    flame_gaps = () if flame_timeline is None else flame_timeline.unknowns
    intervals = [
        right - left
        for left, right in pairwise(report_times)
        if flame_timeline is not None
        and not any(gap.start < right and left < gap.end for gap in flame_gaps)
    ]
    resolution = round(median(intervals)) if intervals else None
    if room_comfort is not None:
        if comfort_profile_mixed:
            for room, config in room_comfort.items():
                if config.status == "scheduled":
                    cold_hours = [pair for pair in cold_hours if pair[0] != room]
                    room_coverage = [pair for pair in room_coverage if pair[0] != room]
                    cold_hours.append((room, None))
                    room_coverage.append((room, 0.0))
        else:
            for room, comfort in room_comfort.items():
                if comfort.status != "scheduled":
                    continue
                actual = by_signal.get(
                    SignalRef(Role.ROOM_TEMPERATURE, Scope(ScopeKind.ROOM, room))
                )
                setpoint = by_signal.get(SignalRef(Role.ROOM_SETPOINT, Scope(ScopeKind.ROOM, room)))
                metrics = analyze_room_comfort(
                    room,
                    comfort,
                    actual,
                    setpoint,
                    tuple(modes),
                    window.start,
                    window.end,
                    policy.comfort_deficit_c,
                    () if comfort_periods is None else comfort_periods.get(room, ()),
                )
                weekly_loss = (
                    None
                    if metrics.target_comfort_loss_ms is None or metrics.observed_ms == 0
                    else metrics.target_comfort_loss_ms / metrics.observed_ms * 168
                )
                cold_hours = [pair for pair in cold_hours if pair[0] != room]
                room_coverage = [pair for pair in room_coverage if pair[0] != room]
                cold_hours.append((room, weekly_loss))
                room_coverage.append((room, metrics.coverage or 0.0))
    return PeriodMetrics(
        coverage=coverage,
        observed_hours=hours,
        starts_per_hour=starts / hours if hours else None,
        median_burn_s=median(c.duration_ms / 1000 for c in complete) if complete else None,
        short_share=short / len(complete) if complete else None,
        flow_stable_c=_mean(
            by_signal.get(SignalRef(Role.FLOW_TEMPERATURE)), _intersect(stable, eligible)
        ),
        outdoor_c=_mean(outdoor, eligible),
        outdoor_coverage=_duration(_intersect(_known(outdoor), eligible)) / eligible_ms
        if eligible_ms
        else 0,
        cold_hours=tuple(cold_hours),
        room_coverage=tuple(room_coverage),
        setpoints=tuple(setpoints),
        cycles=len(complete),
        excluded_ms=window.duration_ms - eligible_ms,
        flame_resolution_ms=resolution,
        setpoint_values=tuple(setpoint_values),
        setpoint_profile=tuple(setpoint_profile),
        comfort_profile_mixed=comfort_profile_mixed,
    )


def evaluate_change(
    change_id: str,
    reference: TimeRange,
    observation: TimeRange,
    before: PeriodMetrics,
    after: PeriodMetrics,
    now: int,
    policy: ComparisonPolicy,
    overlaps: tuple[str, ...] = (),
    rollback_room: str | None = None,
    rollback_limit: float | None = None,
) -> EvaluationFact:
    weather = "limited"
    if (
        before.outdoor_c is not None
        and after.outdoor_c is not None
        and min(before.outdoor_coverage, after.outdoor_coverage) >= policy.min_coverage
    ):
        delta = abs(before.outdoor_c - after.outdoor_c)
        weather = (
            "yes"
            if delta <= policy.weather_delta_c
            else "limited"
            if delta <= policy.limited_weather_delta_c
            else "no"
        )
    old_targets, targets = dict(before.setpoints), dict(after.setpoints)
    target_pairs = [
        (old_targets.get(r), targets.get(r)) for r in old_targets.keys() | targets.keys()
    ]
    setpoints = (
        "yes"
        if target_pairs
        and all(
            old is not None and new is not None and abs(old - new) < 1e-6
            for old, new in target_pairs
        )
        else "limited"
    )
    if any(
        old is not None and new is not None and abs(old - new) >= 1e-6 for old, new in target_pairs
    ):
        setpoints = "no"
    if setpoints == "yes":
        old_levels, new_levels = dict(before.setpoint_values), dict(after.setpoint_values)
        old_profiles, new_profiles = dict(before.setpoint_profile), dict(after.setpoint_profile)
        for room in old_targets.keys() | targets.keys():
            left, right = old_levels.get(room, ()), new_levels.get(room, ())
            if left and right and left != right:
                setpoints = "no"
                break
            if len(left) == len(right) == 1:
                continue
            a, b = dict(old_profiles.get(room, ())), dict(new_profiles.get(room, ()))
            if not a or not b or a.keys() != b.keys():
                setpoints = "limited"
            elif any(abs(a[key] - b[key]) >= 1e-6 for key in a):
                setpoints = "no"
                break
    old_cold, cold = dict(before.cold_hours), dict(after.cold_hours)
    rooms = old_cold.keys() | cold.keys()
    room_ok = bool(rooms) and all(
        dict(before.room_coverage).get(r, 0) >= policy.min_coverage
        and dict(after.room_coverage).get(r, 0) >= policy.min_coverage
        for r in rooms
    )
    sufficient = (
        min(before.coverage, after.coverage, before.outdoor_coverage, after.outdoor_coverage)
        >= policy.min_coverage
        and min(before.observed_hours, after.observed_hours) >= policy.min_observation_hours
        and before.cycles > 0
        and after.cycles > 0
        and room_ok
        and all(
            resolution is not None and resolution <= policy.short_cycle_s * 500
            for resolution in (before.flame_resolution_ms, after.flame_resolution_ms)
        )
        and (rollback_room is None or rollback_room in rooms)
    )
    comfort_pairs = [(old_cold.get(r), cold.get(r)) for r in rooms]
    comfort_better = any(
        old is not None and new is not None and round(new, 1) < round(old, 1)
        for old, new in comfort_pairs
    )
    comfort_worse = any(
        old is not None and new is not None and round(new, 1) > round(old, 1)
        for old, new in comfort_pairs
    )
    improvements, deteriorations = comfort_better, comfort_worse
    for old, new, increasing, scale in (
        (before.starts_per_hour, after.starts_per_hour, False, 1),
        (before.median_burn_s, after.median_burn_s, True, 1),
        (before.short_share, after.short_share, False, 100),
    ):
        if old is not None and new is not None and round(old * scale, 1) != round(new * scale, 1):
            improvements |= (new > old) == increasing
            deteriorations |= (new > old) != increasing
    limit = policy.comfort_limit_h_week if rollback_limit is None else rollback_limit
    rollback = sufficient and any(
        value is not None and value > limit
        for room, value in after.cold_hours
        if rollback_room is None or room == rollback_room
    )
    if overlaps:
        verdict, summary = (
            "not_attributable",
            "Andere wijzigingen vallen in de vergelijking; "
            "een individueel effect is niet toe te schrijven.",
        )
    elif now < observation.end:
        verdict, summary, rollback = "pending", "De observatieperiode is nog niet compleet.", False
    elif weather == "no" or setpoints == "no":
        verdict, summary = (
            "not_attributable",
            "Het effect is niet aan deze wijziging toe te schrijven "
            "door verschillen in de omstandigheden.",
        )
    elif not sufficient or setpoints != "yes":
        verdict, summary = (
            "insufficient_evidence",
            "Onvoldoende vergelijkbare gegevens voor een onderbouwd effectoordeel.",
        )
        rollback = False
    elif improvements and deteriorations:
        verdict, summary = (
            "trade_off",
            "Afweging: gunstiger kengetallen gaan samen met verslechtering op andere punten.",
        )
    elif deteriorations:
        verdict, summary = (
            "worsened",
            "De waargenomen kengetallen of het comfort zijn verslechterd.",
        )
    elif improvements:
        verdict, summary = (
            "improved",
            "Waargenomen verbetering onder vergelijkbare omstandigheden; dit bewijst geen oorzaak.",
        )
    else:
        verdict, summary = (
            "insufficient_evidence",
            "Geen onderscheidend effect zichtbaar op de getoonde meetbasis.",
        )
    if now < observation.end:
        rollback = False
        if verdict == "not_attributable":
            summary += " De observatieperiode is nog niet compleet."
    if rollback and verdict == "improved":
        verdict, summary = (
            "trade_off",
            "Kengetallen verbeterden, maar het comfortcriterium is niet gehaald.",
        )
    if weather == "limited":
        summary += " Het weer is beperkt vergelijkbaar."
    return EvaluationFact(
        change_id,
        reference,
        observation,
        before,
        after,
        verdict,
        weather,
        setpoints,
        overlaps,
        rollback,
        summary,
        policy,
    )
