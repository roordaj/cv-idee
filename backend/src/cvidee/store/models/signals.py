"""Signal catalogue, HA source entities and (versioned) signal mappings (FR-01)."""

from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from cvidee.store.base import Base, enum_column, ts_column
from cvidee.store.enums import ValueKind


class SignalDefinition(Base):
    """Canonical signal role. Source of truth is the catalogue in code; synced at startup."""

    __tablename__ = "signal_definitions"

    role: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_type: Mapped[str] = mapped_column(String(16))  # numeric | boolean | enum | text
    unit: Mapped[str | None] = mapped_column(String(16))
    scope_type: Mapped[str] = mapped_column(String(16))  # analysis.types.ScopeKind value
    default_kind: Mapped[ValueKind] = enum_column(ValueKind, "default_kind")
    cumulative: Mapped[bool] = mapped_column(Boolean, default=False)
    plausible_min: Mapped[float | None] = mapped_column(Float)
    plausible_max: Mapped[float | None] = mapped_column(Float)
    default_max_age_ms: Mapped[int] = mapped_column(Integer)
    default_heartbeat_expected: Mapped[bool] = mapped_column(Boolean, default=False)
    required_for: Mapped[list[Any]] = mapped_column(default=list)  # analysis ids
    catalogue_version: Mapped[str] = mapped_column(String(32))


class SourceEntity(Base):
    """A Home Assistant entity we have seen or subscribed to. Raw data hangs off this."""

    __tablename__ = "source_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(255), unique=True)
    friendly_name: Mapped[str | None] = mapped_column(String(255))
    unit: Mapped[str | None] = mapped_column(String(32))
    device_class: Mapped[str | None] = mapped_column(String(64))
    first_seen_ts: Mapped[int] = ts_column()
    last_seen_ts: Mapped[int] = ts_column()


class SignalMapping(Base):
    """Role (+ scope) -> HA entity, versioned in data time via ``valid_from_ts``/``valid_to_ts``.

    ``valid_to_ts`` NULL means "current". At most one current row per (role, scope_key).
    Max. sensor age and ``heartbeat_expected`` live here (single source, aanvullingen §1.5).
    """

    __tablename__ = "signal_mappings"
    __table_args__ = (
        Index(
            "uq_signal_mappings_current",
            "role",
            "scope_key",
            unique=True,
            sqlite_where=text("valid_to_ts IS NULL"),
            postgresql_where=text("valid_to_ts IS NULL"),
        ),
        Index("ix_signal_mappings_source_entity_id", "source_entity_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(ForeignKey("signal_definitions.role"))
    # '' for singleton scopes (boiler, outdoor), else '<kind>:<key>', e.g. 'room:slaapkamer'
    # (same suffix as str(SignalRef)). Never NULL.
    scope_key: Mapped[str] = mapped_column(String(128), default="")
    source_entity_id: Mapped[int] = mapped_column(ForeignKey("source_entities.id"))
    unit: Mapped[str | None] = mapped_column(String(32))
    location: Mapped[str | None] = mapped_column(String(255))
    meaning: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[ValueKind] = enum_column(ValueKind, "kind")
    heartbeat_expected: Mapped[bool] = mapped_column(Boolean, default=False)
    max_age_ms: Mapped[int] = mapped_column(Integer)
    expected_resolution_ms: Mapped[int | None] = mapped_column(Integer)
    value_map: Mapped[dict[str, Any] | None] = mapped_column()  # raw state -> canonical
    valid_from_ts: Mapped[int] = ts_column()
    valid_to_ts: Mapped[int | None] = ts_column(nullable=True)
    created_at_ts: Mapped[int] = ts_column()
