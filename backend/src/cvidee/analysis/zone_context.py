"""Describe zone status counts alongside existing complete CH cycles (FR-18)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Literal

from cvidee.analysis.types import BurnerCycle, EndReason, Mode, SignalTimeline, TimeRange

ZoneRole = Literal["zone_demand", "valve_state"]


@dataclass(frozen=True, slots=True)
class Zone:
    key: str
    name: str


@dataclass(frozen=True, slots=True)
class ZoneCountBin:
    active_count: int
    cycles: int
    short_cycles: int
    cycle_starts: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class IncompleteZoneCount:
    cycle_start: int
    known_active_count: int
    known_zone_keys: tuple[str, ...]
    missing_zone_keys: tuple[str, ...]
    short: bool


@dataclass(frozen=True, slots=True)
class ZoneRoleAnalysis:
    role: ZoneRole
    availability: Literal["available", "limited", "not_available"]
    mapped_zone_keys: tuple[str, ...]
    unmapped_zone_keys: tuple[str, ...]
    eligible_cycles: int
    complete_cycles: int
    incomplete_cycles: tuple[IncompleteZoneCount, ...]
    coverage: float | None
    distribution: tuple[ZoneCountBin, ...]
    unknown_demand_cycles: int


@dataclass(frozen=True, slots=True)
class ZoneContextAnalysis:
    period: TimeRange
    few_active_zones_max: int | None
    zone_demand: ZoneRoleAnalysis
    valve_state: ZoneRoleAnalysis


def analyze_zone_context(
    zones: tuple[Zone, ...],
    cycles: tuple[BurnerCycle, ...],
    zone_demand: dict[str, SignalTimeline],
    valve_state: dict[str, SignalTimeline],
    heat_demand: SignalTimeline | None,
    period: TimeRange,
    short_cycle_ms: int,
    few_active_zones_max: int | None = None,
) -> ZoneContextAnalysis:
    """Group known zone statuses at complete CH cycle starts without changing cycle labels.

    A zone count is complete only when every configured zone has a known boolean value.
    Partial counts are reported separately with the unobserved zone keys; unknown statuses
    never become inactive. DHW, unknown-mode, open and incomplete cycles are excluded.
    """
    if short_cycle_ms <= 0:
        raise ValueError("Short-cycle threshold must be positive.")
    if few_active_zones_max is not None and few_active_zones_max < 1:
        raise ValueError("Few-zone threshold must be positive when configured.")
    keys = tuple(sorted({zone.key for zone in zones}))
    if len(keys) != len(zones):
        raise ValueError("Zone keys must be unique.")

    def analyze_role(role: ZoneRole, timelines: dict[str, SignalTimeline]) -> ZoneRoleAnalysis:
        mapped = tuple(key for key in keys if key in timelines)
        unmapped = tuple(key for key in keys if key not in timelines)
        eligible = complete = unknown_demand = 0
        counts: Counter[int] = Counter()
        short_counts: Counter[int] = Counter()
        starts: dict[int, list[int]] = {}
        incomplete: list[IncompleteZoneCount] = []

        for cycle in cycles:
            if not period.start <= cycle.start < period.end or not cycle.complete:
                continue
            if not keys:
                continue
            if cycle.mode is not Mode.CH:
                continue
            demand = None if heat_demand is None else heat_demand.value_at(cycle.start)
            if demand is not True:
                if demand is None:
                    unknown_demand += 1
                continue
            eligible += 1
            known: list[str] = []
            missing: list[str] = []
            active = 0
            for key in keys:
                timeline = timelines.get(key)
                value = None if timeline is None else timeline.value_at(cycle.start)
                if not isinstance(value, bool):
                    missing.append(key)
                    continue
                known.append(key)
                active += value
            short = (
                cycle.end_reason is EndReason.STOP_DURING_DEMAND
                and cycle.duration_ms < short_cycle_ms
            )
            if missing:
                incomplete.append(
                    IncompleteZoneCount(cycle.start, active, tuple(known), tuple(missing), short)
                )
                continue
            complete += 1
            counts[active] += 1
            short_counts[active] += int(short)
            starts.setdefault(active, []).append(cycle.start)

        distribution = tuple(
            ZoneCountBin(count, n, short_counts[count], tuple(starts[count]))
            for count, n in sorted(counts.items())
        )
        coverage = complete / eligible if eligible else None
        if not mapped or not eligible:
            availability: Literal["available", "limited", "not_available"] = "not_available"
        elif complete == eligible:
            availability = "available"
        else:
            availability = "limited"
        return ZoneRoleAnalysis(
            role,
            availability,
            mapped,
            unmapped,
            eligible,
            complete,
            tuple(incomplete),
            coverage,
            distribution,
            unknown_demand,
        )

    return ZoneContextAnalysis(
        period,
        few_active_zones_max,
        analyze_role("zone_demand", zone_demand),
        analyze_role("valve_state", valve_state),
    )
