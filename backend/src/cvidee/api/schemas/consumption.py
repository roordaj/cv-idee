"""Raw measured gas consumption and its explicit meter/pricing basis (FR-04, FR-08)."""

from enum import StrEnum

from pydantic import Field

from cvidee.api.schemas.common import ApiModel, TimeRange, UtcDateTime


class GasMeterScope(StrEnum):
    UNKNOWN = "unknown"
    BOILER_ONLY = "boiler_only"
    WHOLE_HOUSE = "whole_house"


class ConsumptionAvailability(StrEnum):
    AVAILABLE = "available"
    LIMITED = "limited"
    UNAVAILABLE = "unavailable"


class ConsumptionReason(StrEnum):
    NO_METER = "no_meter"
    NO_VALID_INTERVALS = "no_valid_intervals"
    UNKNOWN_METER_SCOPE = "unknown_meter_scope"
    MAPPING_CHANGED = "mapping_changed"
    PROFILE_SCOPE_CHANGED = "profile_scope_changed"
    UNSUPPORTED_UNIT = "unsupported_unit"
    DATA_GAP = "data_gap"
    COUNTER_RESET = "counter_reset"


class ConsumptionEventKind(StrEnum):
    COUNTER_RESET = "counter_reset"
    DATA_GAP = "data_gap"
    MAPPING_CHANGED = "mapping_changed"


class ConsumptionEvent(ApiModel):
    kind: ConsumptionEventKind
    start: UtcDateTime
    end: UtcDateTime
    detail: str = ""


class ConsumptionSegment(ApiModel):
    """A non-negative counter delta between two valid readings from one meter mapping."""

    start: UtcDateTime
    end: UtcDateTime
    start_reading: float = Field(ge=0)
    end_reading: float = Field(ge=0)
    consumption_m3: float = Field(ge=0)
    meter_entity_id: str
    mapping_revision: int
    settings_revision: int | None = None
    gas_price_eur_per_m3: float | None = Field(default=None, ge=0)
    cost_eur: float | None = Field(default=None, ge=0)


class ConsumptionResponse(ApiModel):
    range: TimeRange
    availability: ConsumptionAvailability
    reasons: list[ConsumptionReason]
    meter_scope: GasMeterScope
    meter_entity_id: str | None
    unit: str | None
    coverage_pct: float | None = Field(ge=0, le=100)
    counter_start: float | None = Field(ge=0)
    counter_end: float | None = Field(ge=0)
    consumption_m3: float | None = Field(ge=0)
    cost_eur: float | None = Field(ge=0)
    segments: list[ConsumptionSegment]
    events: list[ConsumptionEvent]


class ConsumptionComparisonStatus(StrEnum):
    AVAILABLE = "available"
    LIMITED = "limited"
    UNAVAILABLE = "unavailable"


class ConsumptionComparisonReason(StrEnum):
    NO_VALID_PERIOD = "no_valid_period"
    NO_METER = "no_meter"
    UNKNOWN_METER_SCOPE = "unknown_meter_scope"
    METER_MISMATCH = "meter_mismatch"
    MAPPING_CHANGED = "mapping_changed"
    SCOPE_CHANGED = "scope_changed"
    UNIT_MISMATCH = "unit_mismatch"
    DURATION_MISMATCH = "duration_mismatch"
    LOW_COVERAGE = "low_coverage"
    COUNTER_RESET = "counter_reset"
    DATA_GAP = "data_gap"
    EXCLUDED_PERIOD = "excluded_period"
    WEATHER_OUT_OF_RANGE = "weather_out_of_range"
    WEATHER_LIMITED = "weather_limited"
    SETPOINT_MISMATCH = "setpoint_mismatch"
    SETPOINT_UNKNOWN = "setpoint_unknown"
    USE_CONTEXT_UNKNOWN = "use_context_unknown"


class ConsumptionPeriodContext(ApiModel):
    outdoor_temperature_c: float | None
    outdoor_coverage_pct: float | None = Field(ge=0, le=100)
    room_setpoints_c: dict[str, float | None]
    heating_runtime_hours: float | None = Field(ge=0)
    heat_demand_hours: float | None = Field(ge=0)
    dhw_runtime_hours: float | None = Field(ge=0)
    zone_use: str
    special_periods: list[str]


class ConsumptionPeriodCandidate(ApiModel):
    range: TimeRange
    status: ConsumptionComparisonStatus
    reasons: list[ConsumptionComparisonReason]
    counter_start: float | None = Field(default=None, ge=0)
    counter_end: float | None = Field(default=None, ge=0)
    consumption_m3: float | None = Field(default=None, ge=0)
    meter_scope: GasMeterScope
    meter_entity_id: str | None
    unit: str | None
    mapping_revision: int | None
    coverage_pct: float | None = Field(default=None, ge=0, le=100)
    consumption_availability: ConsumptionAvailability
    cost_availability: ConsumptionAvailability
    context: ConsumptionPeriodContext


class ConsumptionCandidatesResponse(ApiModel):
    observation: TimeRange
    observation_data: ConsumptionPeriodCandidate
    status: ConsumptionComparisonStatus
    reasons: list[ConsumptionComparisonReason]
    candidates: list[ConsumptionPeriodCandidate]
    consumption_availability: ConsumptionAvailability
    efficiency_availability: ConsumptionAvailability
    cost_availability: ConsumptionAvailability


class ConsumptionComparisonWindow(ApiModel):
    start: UtcDateTime
    end: UtcDateTime


class ConsumptionComparisonRequest(ApiModel):
    observation: ConsumptionComparisonWindow
    reference: ConsumptionComparisonWindow


class ConsumptionComparisonResponse(ApiModel):
    reference: ConsumptionPeriodCandidate
    observation: ConsumptionPeriodCandidate
    status: ConsumptionComparisonStatus
    reasons: list[ConsumptionComparisonReason]
    difference_m3: float | None
    basis: str
    consumption_availability: ConsumptionAvailability
    efficiency_availability: ConsumptionAvailability
    cost_availability: ConsumptionAvailability
