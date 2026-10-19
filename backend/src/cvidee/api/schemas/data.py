"""Data quality, timeline, cycles, special periods and historical import (FR-06-13)."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import ConfigDict, Field

from cvidee.api.schemas.common import ApiModel, TimeRange, UtcDateTime
from cvidee.store.enums import (
    EndReason,
    EvaluationVerdict,
    ImportStatus,
    Mode,
    QualityEventKind,
    SpecialPeriodKind,
    TriState,
)

# --- quality ---------------------------------------------------------------------------


class CoverageSegmentKind(StrEnum):
    CONNECTION_LOST = "connection_lost"
    STALE = "stale"
    NOT_MAPPED = "not_mapped"
    DATA_GAP = "data_gap"
    UNKNOWN = "unknown"


class CoverageSegment(ApiModel):
    start: UtcDateTime
    end: UtcDateTime
    kind: CoverageSegmentKind


class SignalCoverage(ApiModel):
    name: str
    signal_ids: list[str]
    coverage_pct: float | None = Field(ge=0, le=100, description="null when not mapped.")
    segments: list[CoverageSegment]


class QualityEvent(ApiModel):
    kind: QualityEventKind | None = Field(description="null for a recovery event.")
    title: str
    consequence: str
    at: UtcDateTime
    end: UtcDateTime | None = None
    signal_ids: list[str] = Field(default_factory=list)
    recovered: bool = False


class ModeShare(ApiModel):
    mode: Mode
    label: str
    minutes: float = Field(ge=0)
    share_pct: float = Field(ge=0, le=100)


class QualityResponse(ApiModel):
    range: TimeRange
    core_coverage_pct: float | None = Field(ge=0, le=100, description="Boiler signals.")
    coverage: list[SignalCoverage]
    events: list[QualityEvent]
    mode_share_range: TimeRange
    mode_share: list[ModeShare]
    flame_resolution_s: float | None
    flame_resolution_text: str


# --- timeline and cycles ---------------------------------------------------------------


class CycleClass(StrEnum):
    SHORT = "short"
    NORMAL = "normal"
    EXCLUDED = "excluded"
    INCOMPLETE = "incomplete"


class Cycle(ApiModel):
    number: int = Field(ge=1, description="Sequence number within the range.")
    start: UtcDateTime
    end: UtcDateTime | None = Field(description="null when the end is unknown (data gap).")
    duration_s: float = Field(ge=0, description="Known duration; a lower bound if incomplete.")
    duration_is_lower_bound: bool
    mode: Mode
    end_reason: EndReason
    max_flow_temperature: float | None
    flow_setpoint: float | None
    mean_modulation_pct: float | None = Field(ge=0, le=100)
    short_during_demand: bool
    classification: CycleClass


class CycleSummary(ApiModel):
    observed_hours: float = Field(ge=0, description="Hours with data in the range.")
    starts_per_hour: float | None = Field(ge=0, description="CH starts per observed hour.")
    ch_cycles: int = Field(ge=0)
    dhw_cycles: int = Field(ge=0)
    short_during_demand: int = Field(ge=0)
    short_cycle_threshold_s: float = Field(gt=0)
    median_burn_s: float | None
    mean_burn_s: float | None
    median_pause_s: float | None
    total_burn_s: float | None = Field(ge=0)
    incomplete_cycles: int = Field(ge=0)


class CycleList(ApiModel):
    range: TimeRange
    summary: CycleSummary
    items: list[Cycle]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class ModeSegment(ApiModel):
    start: UtcDateTime
    end: UtcDateTime
    mode: Mode


class DemandSegment(ApiModel):
    start: UtcDateTime
    end: UtcDateTime
    heat_demand: TriState


class SampledSeries(ApiModel):
    """Values on a regular grid ``start + i * step_s``; ``null`` = no data."""

    start: UtcDateTime
    step_s: float = Field(gt=0)
    flow_temperature: list[float | None]
    return_temperature: list[float | None]
    flow_setpoint: list[float | None]
    modulation_pct: list[float | None]


class ChangeMarker(ApiModel):
    id: str
    at: UtcDateTime
    parameter: str
    old_value: str
    new_value: str
    actor: str
    verdict: EvaluationVerdict
    verdict_text: str


class ChangeRef(ApiModel):
    id: str
    at: UtcDateTime
    parameter: str


class PeriodBand(ApiModel):
    id: str
    kind: SpecialPeriodKind
    start: UtcDateTime
    end: UtcDateTime | None


class TimelineResponse(ApiModel):
    range: TimeRange
    series: SampledSeries
    modes: list[ModeSegment]
    heat_demand: list[DemandSegment]
    cycles: list[Cycle]
    gaps: list[TimeRange]
    changes: list[ChangeMarker]
    last_change_before: ChangeRef | None
    periods: list[PeriodBand]


# --- special periods -------------------------------------------------------------------


class PeriodExclusions(ApiModel):
    """What the period does not count for (all on by default, design additions §3a)."""

    normal_behaviour: bool = True
    comparisons: bool = True
    ch_conclusions: bool = True


class SpecialPeriodIn(ApiModel):
    kind: SpecialPeriodKind
    start: UtcDateTime
    end: UtcDateTime | None = Field(default=None, description="null = still running.")
    description: str = Field(default="", max_length=140)
    excluded_from: PeriodExclusions = PeriodExclusions()


class SpecialPeriod(SpecialPeriodIn):
    id: str
    created_at: UtcDateTime


class SpecialPeriodList(ApiModel):
    items: list[SpecialPeriod]


# --- import ----------------------------------------------------------------------------


class ImportRequest(ApiModel):
    start: UtcDateTime = Field(alias="from")
    end: UtcDateTime = Field(alias="to")
    signal_ids: list[str] | None = Field(default=None, description="null = all mapped.")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ImportSignalProgress(ApiModel):
    signal_id: str
    observations: int = Field(ge=0)
    first_at: UtcDateTime | None


class ImportJob(ApiModel):
    id: str
    status: ImportStatus
    range: TimeRange
    blocks_done: int = Field(ge=0)
    blocks_total: int = Field(ge=1)
    current_block_day: date | None
    observations_imported: int = Field(ge=0)
    duplicates_skipped: int = Field(ge=0)
    signals: list[ImportSignalProgress]
    earliest_available_at: UtcDateTime | None
    cycles_found: int | None = Field(ge=0)
    coverage_pct: float | None = Field(ge=0, le=100)
    warnings: list[str] = Field(description="Attention points after completion.")
    errors: list[str]
    started_at: UtcDateTime
    finished_at: UtcDateTime | None
    eta_s: float | None = Field(default=None, ge=0)


class ImportList(ApiModel):
    items: list[ImportJob]
    earliest_available_at: UtcDateTime | None = Field(
        description="Oldest data the HA recorder still has."
    )
