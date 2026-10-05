"""Installation profile (FR-02, FR-03), versioned copy-on-write, and special periods (FR-10)."""

from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cvidee.store.base import Base, enum_column, ts_column
from cvidee.store.enums import CircuitKind, EmitterType, SpecialPeriodKind, SpecStatus


class InstallationProfile(Base):
    """One version of the installation profile, valid in data time [valid_from, valid_to).

    Every edit creates a new version with a full copy of its children, so analyses and
    snapshots can refer to an immutable ``profile_id``. "At most one current version" is a
    repository invariant (a partial unique index cannot express it on a NULL column).
    """

    __tablename__ = "installation_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    valid_from_ts: Mapped[int] = ts_column(index=True)
    valid_to_ts: Mapped[int | None] = ts_column(nullable=True)
    created_at_ts: Mapped[int] = ts_column()
    change_id: Mapped[int | None] = mapped_column(ForeignKey("changes.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(Text)
    # Presentation facts without a relational meaning (boiler description, loops, notes,
    # room schedules); copied with the version like the children.
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default="{}")

    circuits: Mapped[list["ProfileCircuit"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    zones: Mapped[list["ProfileZone"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    rooms: Mapped[list["ProfileRoom"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    specs: Mapped[list["InstallationSpec"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


class ProfileCircuit(Base):
    __tablename__ = "profile_circuits"
    __table_args__ = (UniqueConstraint("profile_id", "key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("installation_profiles.id", ondelete="CASCADE")
    )
    key: Mapped[str] = mapped_column(String(64))  # stable across versions, e.g. 'boven'
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[CircuitKind] = enum_column(CircuitKind, "kind")
    emitter: Mapped[EmitterType] = enum_column(EmitterType, "emitter")

    profile: Mapped[InstallationProfile] = relationship(back_populates="circuits")


class ProfileZone(Base):
    __tablename__ = "profile_zones"
    __table_args__ = (UniqueConstraint("profile_id", "key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("installation_profiles.id", ondelete="CASCADE")
    )
    key: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))
    circuit_key: Mapped[str | None] = mapped_column(String(64))

    profile: Mapped[InstallationProfile] = relationship(back_populates="zones")


class ProfileRoom(Base):
    __tablename__ = "profile_rooms"
    __table_args__ = (UniqueConstraint("profile_id", "key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("installation_profiles.id", ondelete="CASCADE")
    )
    key: Mapped[str] = mapped_column(String(64))  # e.g. 'slaapkamer'
    name: Mapped[str] = mapped_column(String(128))
    circuit_key: Mapped[str | None] = mapped_column(String(64))  # structural: NULL = none
    zone_key: Mapped[str | None] = mapped_column(String(64))
    has_thermostat: Mapped[bool] = mapped_column(Boolean, default=False)
    # The thermostat in this room determines the boiler heat demand (FR-02).
    is_demand_source: Mapped[bool] = mapped_column(Boolean, default=False)

    profile: Mapped[InstallationProfile] = relationship(back_populates="rooms")


class InstallationSpec(Base):
    """A specification value with explicit status: known / unknown / not_applicable.

    A value is present if and only if ``status = 'known'`` (CHECK), so NULL never has to
    be interpreted as "unknown".
    """

    __tablename__ = "installation_specs"
    __table_args__ = (
        UniqueConstraint("profile_id", "scope_key", "key"),
        CheckConstraint(
            "(status = 'known') = (value_num IS NOT NULL OR value_text IS NOT NULL)",
            name="value_iff_known",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("installation_profiles.id", ondelete="CASCADE")
    )
    scope_key: Mapped[str] = mapped_column(String(128), default="")  # '' = boiler/global
    key: Mapped[str] = mapped_column(String(64))  # e.g. 'max_flow_temperature'
    status: Mapped[SpecStatus] = enum_column(SpecStatus, "status")
    value_num: Mapped[float | None] = mapped_column(Float)
    value_text: Mapped[str | None] = mapped_column(String(255))
    unit: Mapped[str | None] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text)
    # The logged change that set this value ("sinds 21 sep (W-07)").
    change_id: Mapped[int | None] = mapped_column(ForeignKey("changes.id", ondelete="SET NULL"))

    profile: Mapped[InstallationProfile] = relationship(back_populates="specs")


class SpecialPeriod(Base):
    """User-marked period (FR-10). Editable (PUT); ``end_ts`` NULL means "still running"."""

    __tablename__ = "special_periods"
    __table_args__ = (
        Index("ix_special_periods_start_ts_end_ts", "start_ts", "end_ts"),
        CheckConstraint("end_ts IS NULL OR end_ts > start_ts", name="end_after_start"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[SpecialPeriodKind] = enum_column(SpecialPeriodKind, "kind")
    start_ts: Mapped[int] = ts_column()
    end_ts: Mapped[int | None] = ts_column(nullable=True)
    description: Mapped[str | None] = mapped_column(String(140))
    exclude_from_baseline: Mapped[bool] = mapped_column(Boolean, default=True)
    exclude_from_comparisons: Mapped[bool] = mapped_column(Boolean, default=True)
    exclude_from_ch_conclusions: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at_ts: Mapped[int] = ts_column()
    updated_at_ts: Mapped[int] = ts_column()
