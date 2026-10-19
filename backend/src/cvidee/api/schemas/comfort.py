"""Room-comfort analysis API contract (FR-17)."""

from typing import Literal

from pydantic import Field

from cvidee.api.schemas.common import ApiModel, UtcDateTime


class RoomComfortResult(ApiModel):
    room_key: str
    room_name: str
    availability: Literal["available", "limited", "not_available"]
    target_source: Literal["configured_schedule", "special_period", "not_configured"]
    current_temperature_c: float | None
    current_setpoint_c: float | None
    expected_hours: float = Field(ge=0)
    observed_hours: float = Field(ge=0)
    coverage_pct: float | None = Field(default=None, ge=0, le=100)
    comfort_loss_target_hours: float | None = Field(default=None, ge=0)
    comfort_loss_setpoint_hours: float | None = Field(default=None, ge=0)
    overshoot_target_hours: float | None = Field(default=None, ge=0)
    max_overshoot_target_c: float | None = None
    overshoot_setpoint_hours: float | None = Field(default=None, ge=0)
    max_overshoot_setpoint_c: float | None = None
    mean_target_deviation_c: float | None = None
    mean_setpoint_deviation_c: float | None = None
    warmup_mean_minutes: float | None = Field(default=None, ge=0)
    warmup_samples: int = Field(ge=0)
    warmup_incomplete: bool
    missing_signals: list[str]


class RoomComfortAnalysisResponse(ApiModel):
    start: UtcDateTime
    end: UtcDateTime
    profile_version: str
    comfort_margin_c: float = Field(ge=0)
    rooms: list[RoomComfortResult]
