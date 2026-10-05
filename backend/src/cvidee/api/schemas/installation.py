"""Installation profile (FR-02, FR-03, FR-05)."""

from __future__ import annotations

from pydantic import Field

from cvidee.api.schemas.common import ApiModel, UtcDateTime
from cvidee.store.enums import CircuitKind, EmitterType, SpecStatus


class BoilerInfo(ApiModel):
    model: str
    control: str
    data_source: str
    heat_demand_source: str


class Circuit(ApiModel):
    id: str
    name: str
    kind: CircuitKind
    emitter: EmitterType
    loops: int | None = Field(default=None, ge=1, description="Underfloor groups, if known.")
    rooms: list[str] = Field(description="Room keys served by this circuit.")
    note: str = ""


class Room(ApiModel):
    key: str
    name: str
    has_sensor: bool
    is_thermostat: bool
    schedule_text: str | None = Field(description="E.g. '07:00-22:30'.")
    setpoint: float | None
    night_setpoint: float | None


class Specification(ApiModel):
    """A boiler/installation specification; unknown stays explicitly unknown (FR-03)."""

    key: str
    label: str
    status: SpecStatus
    value: float | str | None
    unit: str | None
    note: str
    since: UtcDateTime | None = None
    change_id: str | None = None


class InstallationProfileIn(ApiModel):
    boiler: BoilerInfo
    circuits: list[Circuit]
    rooms: list[Room]
    specifications: list[Specification]
    revision: int = Field(ge=0, description="Optimistic concurrency: send the revision read.")


class InstallationProfile(InstallationProfileIn):
    summary: str = Field(description="One-line summary, e.g. 'Radiatoren beneden, …'.")
    updated_at: UtcDateTime
