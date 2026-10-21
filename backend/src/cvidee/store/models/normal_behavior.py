"""Versioned lifecycle metadata and logical references to eligible metric windows."""

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
from cvidee.store.enums import NormalBehaviorEventKind, NormalBehaviorStatus


class NormalBehaviorModel(Base):
    """One immutable numbered reference version for a metric, with mutable lifecycle state."""

    __tablename__ = "normal_behavior_models"
    __table_args__ = (
        CheckConstraint("version > 0", name="version_positive"),
        UniqueConstraint("metric_name", "version"),
        Index("ix_normal_behavior_models_metric_current", "metric_name", "is_current"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    metric_name: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[NormalBehaviorStatus] = enum_column(NormalBehaviorStatus, "status")
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at_ts: Mapped[int] = ts_column()
    updated_at_ts: Mapped[int] = ts_column()
    effective_from_ts: Mapped[int | None] = ts_column(nullable=True)
    reason: Mapped[str | None] = mapped_column(Text)
    pause_reason: Mapped[str | None] = mapped_column(Text)
    paused_at_ts: Mapped[int | None] = ts_column(nullable=True)
    status_before_pause: Mapped[NormalBehaviorStatus | None] = enum_column(
        NormalBehaviorStatus, "status_before_pause", nullable=True
    )

    observations: Mapped[list["NormalBehaviorObservation"]] = relationship(
        back_populates="model", cascade="all, delete-orphan"
    )
    events: Mapped[list["NormalBehaviorEvent"]] = relationship(
        back_populates="model", cascade="all, delete-orphan", order_by="NormalBehaviorEvent.id"
    )


class NormalBehaviorObservation(Base):
    """Idempotent pointer to one existing derived metric row; metric values are not copied."""

    __tablename__ = "normal_behavior_observations"
    __table_args__ = (
        CheckConstraint("window_end_ts > window_start_ts", name="window_end_after_start"),
        CheckConstraint("time_basis_seconds >= 0", name="time_basis_nonnegative"),
        CheckConstraint("coverage >= 0 AND coverage <= 1", name="coverage_fraction"),
        UniqueConstraint(
            "model_id",
            "metric_name",
            "mode",
            "window_kind",
            "window_start_ts",
            "cycle_start_ts",
        ),
        Index("ix_normal_behavior_observations_period", "window_start_ts", "window_end_ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("normal_behavior_models.id", ondelete="CASCADE")
    )
    metric_name: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(16), default="")
    window_kind: Mapped[str] = mapped_column(String(16))
    window_start_ts: Mapped[int] = ts_column()
    window_end_ts: Mapped[int] = ts_column()
    cycle_start_ts: Mapped[int] = ts_column()
    unit: Mapped[str] = mapped_column(String(16))
    time_basis_seconds: Mapped[float] = mapped_column(Float)
    coverage: Mapped[float] = mapped_column(Float)
    analysis_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL")
    )
    settings_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("settings_revisions.id", ondelete="SET NULL")
    )
    profile_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("installation_profiles.id", ondelete="SET NULL")
    )
    analysis_version: Mapped[str | None] = mapped_column(String(64))
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default="{}")

    model: Mapped[NormalBehaviorModel] = relationship(back_populates="observations")


class NormalBehaviorEvent(Base):
    """Append-only audit row for a model creation, pause, resume, or reference reset."""

    __tablename__ = "normal_behavior_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("normal_behavior_models.id", ondelete="CASCADE")
    )
    kind: Mapped[NormalBehaviorEventKind] = enum_column(NormalBehaviorEventKind, "kind")
    occurred_at_ts: Mapped[int] = ts_column()
    reason: Mapped[str | None] = mapped_column(Text)
    effective_from_ts: Mapped[int | None] = ts_column(nullable=True)

    model: Mapped[NormalBehaviorModel] = relationship(back_populates="events")
