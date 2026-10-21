"""Installation profile (FR-02, FR-03, FR-05)."""

from __future__ import annotations

import math
from itertools import pairwise
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from cvidee.api.schemas.common import ApiModel, UtcDateTime
from cvidee.store.enums import CircuitKind, EmitterType, SpecStatus


class BoilerInfo(ApiModel):
    model: str
    control: str
    data_source: str
    heat_demand_source: str


class Loop(ApiModel):
    """One explicitly identified underfloor-heating loop."""

    key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    label: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]


class Circuit(ApiModel):
    id: str
    name: str
    kind: CircuitKind
    emitter: EmitterType
    loops: int | None = Field(default=None, ge=1, description="Underfloor groups, if known.")
    loops_inventory: list[Loop] | None = Field(
        default=None,
        description="Stable loop identities; omit in legacy writes to preserve the inventory.",
    )
    rooms: list[str] = Field(description="Room keys served by this circuit.")
    note: str = ""


class Zone(ApiModel):
    """A stable, circuit-scoped heating zone in the installation profile."""

    key: str
    name: str
    circuit_key: str | None


class RoomComfortWindow(ApiModel):
    """One recurring local-time comfort target for selected weekdays."""

    kind: Literal["comfort", "night"] = "comfort"
    weekdays: list[int] = Field(
        min_length=1, max_length=7, description="Monday=0 through Sunday=6."
    )
    start_time: Annotated[str, StringConstraints(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")]
    end_time: Annotated[str, StringConstraints(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")]
    target_temperature_c: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_weekdays(self) -> RoomComfortWindow:
        if not math.isfinite(self.target_temperature_c):
            raise ValueError("Het comfortdoel moet een eindige temperatuur zijn.")
        if any(day < 0 or day > 6 for day in self.weekdays):
            raise ValueError("Weekdagen zijn 0 (maandag) tot en met 6 (zondag).")
        if len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("Weekdagen mogen per tijdvak niet dubbel voorkomen.")
        if self.start_time == self.end_time:
            raise ValueError("Begin- en eindtijd van een tijdvak moeten verschillen.")
        return self


class RoomComfort(ApiModel):
    """Explicit user intent; unconfigured stays distinct from no expectation."""

    status: Literal["not_configured", "scheduled", "no_expectation"] = "not_configured"
    timezone: Literal["Europe/Amsterdam"] = "Europe/Amsterdam"
    windows: list[RoomComfortWindow] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_status(self) -> RoomComfort:
        if self.status == "scheduled" and not self.windows:
            raise ValueError("Een ingesteld weekschema bevat ten minste één tijdvak.")
        if self.status != "scheduled" and self.windows:
            raise ValueError("Tijdvakken zijn alleen toegestaan bij status 'scheduled'.")
        minutes: dict[int, list[tuple[int, int]]] = {day: [] for day in range(7)}
        for window in self.windows:
            start = _minutes(window.start_time)
            end = _minutes(window.end_time)
            for day in window.weekdays:
                if end > start:
                    minutes[day].append((start, end))
                else:
                    minutes[day].append((start, 24 * 60))
                    minutes[(day + 1) % 7].append((0, end))
        for intervals in minutes.values():
            ordered = sorted(intervals)
            if any(current[0] < previous[1] for previous, current in pairwise(ordered)):
                raise ValueError("Comforttijdvakken mogen per ruimte en weekdag niet overlappen.")
        return self


def _minutes(value: str) -> int:
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


class Room(ApiModel):
    key: str
    name: str
    has_sensor: bool
    is_thermostat: bool
    schedule_text: str | None = Field(description="E.g. '07:00-22:30'.")
    setpoint: float | None
    night_setpoint: float | None
    comfort: RoomComfort | None = Field(
        default=None,
        description="A recurring user comfort schedule; null on legacy writes means preserve it.",
    )


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
    zones: list[Zone] | None = Field(
        default=None,
        description="Omit only for legacy writes to preserve the current zone inventory.",
    )
    rooms: list[Room]
    specifications: list[Specification]
    revision: int = Field(ge=0, description="Optimistic concurrency: send the revision read.")


class InstallationProfile(InstallationProfileIn):
    zones: list[Zone]
    summary: str = Field(description="One-line summary, e.g. 'Radiatoren beneden, …'.")
    updated_at: UtcDateTime
