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
