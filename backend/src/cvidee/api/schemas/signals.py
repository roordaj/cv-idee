"""Signals, HA entities and analysis availability (FR-01, FR-04)."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from cvidee.analysis.types import Role, ScopeKind
from cvidee.api.schemas.common import ApiModel, UtcDateTime
from cvidee.rules.base import AnalysisId, AvailabilityStatus

ValueKindName = Literal["measured", "reported", "derived", "estimated"]
"""Provenance of a value (``cvidee.analysis.types.ValueKind`` by name)."""


class SignalState(StrEnum):
    OK = "ok"
    STALE = "stale"
    MISSING = "missing"


class SignalGroup(StrEnum):
    """Onboarding grouping (design additions §2.5)."""

    REQUIRED = "required"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"


class Signal(ApiModel):
    """A signal role at a scope and its mapping to a Home Assistant entity."""

    id: str = Field(
        description="Signal id '<role>@<scope>', e.g. 'room_temperature@room:slaapkamer'.",
        examples=["flame@boiler"],
    )
    role: Role
    scope_kind: ScopeKind
    scope_key: str | None
    name: str = Field(description="Dutch display name, e.g. 'Brander/vlam actief'.")
    group: SignalGroup
    entity_id: str | None = Field(description="Mapped HA entity; null = not mapped.")
    unit: str | None
    location: str | None
    value_kind: ValueKindName | None
    meaning: str | None
    needed_for_text: str
    max_age_s: int | None = Field(ge=5, le=86400, description="Maximum sensor age (5 s - 24 h).")
    expects_regular_updates: bool = Field(
        description="Only then can staleness be derived from the age (ADR-003)."
    )
    state: SignalState
    age_s: int | None = Field(ge=0, description="Age of the newest value; null if none.")
    median_update_interval_s: float | None = Field(
        default=None, ge=0, description="Actual median update interval over the last 24 h."
    )
    expected_resolution_s: float | None = Field(default=None, ge=0.001, le=86400)
    valid_from: UtcDateTime | None = None
    value_map: dict[str, float | str | bool | None] | None = None


class SignalList(ApiModel):
    items: list[Signal]
    linked: int = Field(ge=0)
    total: int = Field(ge=0)


class SignalMappingUpdate(ApiModel):
    """``PUT /api/signals/{signal_id}``; ``entity_id = null`` unlinks the signal."""

    entity_id: str | None = Field(pattern=r"^[a-z_]+\.[a-z0-9_]+$")
    unit: str | None = None
    location: str | None = Field(default=None, max_length=80)
    value_kind: ValueKindName | None = None
    meaning: str | None = Field(default=None, max_length=280)
    max_age_s: int | None = Field(default=None, ge=5, le=86400)
    expects_regular_updates: bool | None = None
    expected_resolution_s: float | None = Field(default=None, ge=0.001, le=86400)
    valid_from: UtcDateTime | None = None
    value_map: dict[str, float | str | bool | None] | None = None


class HaEntity(ApiModel):
    """A Home Assistant entity for the entity picker (design additions §3b, #17).

    Optional fields are ``null`` when Home Assistant does not provide them; area and device
    come from the HA registries and are not part of the state list.
    """

    id: str = Field(description="Entity id, e.g. 'sensor.remeha_flow_temp'.")
    friendly_name: str | None = None
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    state: str | None = None
    last_changed: UtcDateTime | None = None
    last_reported: UtcDateTime | None = None


class HaConnectionStatus(ApiModel):
    """``GET /api/ha/status``: whether HA is configured and the live connection is up."""

    configured: bool
    connected: bool


class AnalysisOut(ApiModel):
    """Availability of an analysis (FR-04)."""

    id: AnalysisId
    name: str
    status: AvailabilityStatus
    note: str
    missing_signals: list[str] = Field(description="Signal ids that are not mapped or silent.")


class AnalysisList(ApiModel):
    items: list[AnalysisOut]
