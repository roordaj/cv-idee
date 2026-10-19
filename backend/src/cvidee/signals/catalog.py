"""Versioned signal definitions with provisional defaults until CAN inventory #5."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from cvidee.analysis.types import Role, Scope, ScopeKind, SignalRef, ValueKind
from cvidee.api.schemas.signals import SignalGroup
from cvidee.rules.availability import AvailabilityPolicy, analysis_requirements
from cvidee.rules.base import AnalysisId
from cvidee.store.models import SignalDefinition

CATALOGUE_VERSION = "1.0.0"


@dataclass(frozen=True)
class SignalDefinitionInfo:
    role: Role
    name: str
    unit: str | None
    value_type: str = "numeric"
    kind: ValueKind = ValueKind.MEASURED
    max_age_s: int = 30
    heartbeat_expected: bool = False
    group: SignalGroup = SignalGroup.OPTIONAL
    cumulative: bool = False


CATALOGUE = (
    SignalDefinitionInfo(
        Role.FLAME,
        "Brander/vlam actief",
        None,
        "boolean",
        ValueKind.REPORTED,
        group=SignalGroup.REQUIRED,
    ),
    SignalDefinitionInfo(
        Role.OPERATING_MODE,
        "CV-/tapwatermodus",
        None,
        "enum",
        ValueKind.REPORTED,
        group=SignalGroup.RECOMMENDED,
    ),
    SignalDefinitionInfo(
        Role.HEAT_DEMAND,
        "Warmtevraag",
        None,
        "boolean",
        ValueKind.REPORTED,
        group=SignalGroup.RECOMMENDED,
    ),
    SignalDefinitionInfo(
        Role.FLOW_SETPOINT,
        "Gewenste ketelaanvoer",
        "°C",
        kind=ValueKind.REPORTED,
        group=SignalGroup.RECOMMENDED,
    ),
    SignalDefinitionInfo(
        Role.FLOW_TEMPERATURE, "Ketelaanvoer", "°C", group=SignalGroup.RECOMMENDED
    ),
    SignalDefinitionInfo(
        Role.RETURN_TEMPERATURE, "Ketelretour", "°C", group=SignalGroup.RECOMMENDED
    ),
    SignalDefinitionInfo(
        Role.MODULATION,
        "Brander-modulatie",
        "%",
        kind=ValueKind.REPORTED,
        group=SignalGroup.RECOMMENDED,
    ),
    SignalDefinitionInfo(
        Role.ROOM_TEMPERATURE,
        "Kamertemp.",
        "°C",
        max_age_s=600,
        heartbeat_expected=True,
        group=SignalGroup.RECOMMENDED,
    ),
    SignalDefinitionInfo(
        Role.ROOM_SETPOINT,
        "Kamer-setpoint",
        "°C",
        kind=ValueKind.REPORTED,
        max_age_s=600,
        group=SignalGroup.RECOMMENDED,
    ),
    SignalDefinitionInfo(
        Role.OUTDOOR_TEMPERATURE,
        "Buitentemperatuur",
        "°C",
        max_age_s=900,
        heartbeat_expected=True,
        group=SignalGroup.RECOMMENDED,
    ),
    SignalDefinitionInfo(
        Role.GAS_CUMULATIVE, "Cumulatief gasverbruik", "m³", max_age_s=3600, cumulative=True
    ),
    SignalDefinitionInfo(
        Role.ZONE_DEMAND, "Zonevraag", None, "boolean", ValueKind.REPORTED, max_age_s=60
    ),
    SignalDefinitionInfo(
        Role.VALVE_STATE, "Klepstatus", None, "boolean", ValueKind.REPORTED, max_age_s=60
    ),
    SignalDefinitionInfo(
        Role.MANIFOLD_FLOW_TEMPERATURE,
        "Verdeleraanvoer",
        "°C",
        max_age_s=60,
        heartbeat_expected=True,
    ),
    SignalDefinitionInfo(
        Role.MANIFOLD_RETURN_TEMPERATURE,
        "Verdelerretour",
        "°C",
        max_age_s=60,
        heartbeat_expected=True,
    ),
    SignalDefinitionInfo(Role.FLOW_RATE, "Debiet", "L/min", max_age_s=60, heartbeat_expected=True),
    SignalDefinitionInfo(
        Role.PUMP_STATE, "Pompstatus", None, "boolean", ValueKind.REPORTED, max_age_s=60
    ),
    SignalDefinitionInfo(Role.HEAT_METER, "Warmtemeter", "kWh", max_age_s=3600, cumulative=True),
)
BY_ROLE = {info.role: info for info in CATALOGUE}
ANALYSIS_NAMES = {
    AnalysisId.CYCLES: "Cycli",
    AnalysisId.TEMPERATURE: "Temperatuur",
    AnalysisId.OPERATING_MODE: "Bedrijfsmodus",
    AnalysisId.COMFORT: "Comfort",
    AnalysisId.ZONES: "Zones",
    AnalysisId.HYDRAULIC: "Hydraulisch",
    AnalysisId.CONSUMPTION: "Verbruik",
    AnalysisId.EFFICIENCY: "Rendement",
    AnalysisId.BEFORE_AFTER: "Voor/na",
}


def parse_signal_id(ident: str) -> SignalRef:
    """Parse a canonical role/scope id, including optional circuit scopes."""
    role, separator, suffix = ident.partition("@")
    kind, _, key = suffix.partition(":")
    if not separator:
        raise ValueError("Signal id needs a scope")
    ref = SignalRef(Role(role), Scope(ScopeKind(kind), key or None))
    if str(ref) != ident:
        raise ValueError("Non-canonical signal id")
    return ref


def needed_for(role: Role) -> tuple[AnalysisId, ...]:
    """Analyses depending on a role, including optional and alternative requirements."""
    return tuple(
        analysis
        for analysis, requirement in analysis_requirements(AvailabilityPolicy()).items()
        if role in (*requirement.required, *requirement.optional)
        or any(
            role in alternative
            for group in (*requirement.required_any, *requirement.optional_any)
            for alternative in group.alternatives
        )
    )


def sync_catalogue(session: Session) -> None:
    """Synchronise code-owned definitions, preserving mappings and observations."""
    for info in CATALOGUE:
        row = session.get(SignalDefinition, info.role.value)
        if row is None:
            row = SignalDefinition(role=info.role.value)
            session.add(row)
        row.value_type = info.value_type
        row.unit = info.unit
        row.scope_type = info.role.scope_kind.value
        row.default_kind = info.kind
        row.cumulative = info.cumulative
        row.default_max_age_ms = info.max_age_s * 1000
        row.default_heartbeat_expected = info.heartbeat_expected
        row.required_for = [analysis.value for analysis in needed_for(info.role)]
        row.catalogue_version = CATALOGUE_VERSION
