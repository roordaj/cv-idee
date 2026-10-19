"""Zone-count analysis API contract (FR-18)."""

from typing import Literal

from pydantic import Field

from cvidee.api.schemas.common import ApiModel, UtcDateTime


class ZoneCountBin(ApiModel):
    active_count: int
    cycles: int
    short_cycles: int
    cycle_starts: list[UtcDateTime] = Field(
        description="Cycle starts included in this bin; usable to open matching timeline evidence."
    )
    few_active_zones: bool | None = Field(
        description=(
            "True only when a user-configured threshold exists and this count is at or below it."
        )
    )


class IncompleteZoneCount(ApiModel):
    cycle_start: UtcDateTime
    known_active_count: int
    known_zone_keys: list[str]
    missing_zone_keys: list[str]
    short: bool


class ZoneSignalRef(ApiModel):
    zone_key: str
    signal_id: str
    meaning: str | None


class ZoneSignalAnalysis(ApiModel):
    role: Literal["zone_demand", "valve_state"]
    availability: Literal["available", "limited", "not_available"]
    mapped_zone_keys: list[str]
    unmapped_zone_keys: list[str]
    signals: list[ZoneSignalRef] = Field(
        description="Mapped zone signal references and user-provided meaning, kept per role."
    )
    eligible_cycles: int
    complete_cycles: int
    coverage_pct: float | None = Field(
        description=(
            "Share of eligible complete CH cycle starts with known states for all configured zones."
        )
    )
    distribution: list[ZoneCountBin]
    incomplete_cycles: list[IncompleteZoneCount]
    unknown_demand_cycles: int
    note: str


class ZoneAnalysisResponse(ApiModel):
    start: UtcDateTime
    end: UtcDateTime
    profile_version: str
    few_active_zones_max: int | None
    zone_demand: ZoneSignalAnalysis
    valve_state: ZoneSignalAnalysis
    short_cycle_threshold_s: float
    exclusions: list[str]
    interpretation: str
