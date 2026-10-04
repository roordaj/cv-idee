"""Change log (FR-29) and before/after evaluation (FR-30, FR-32)."""

from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cvidee.store.base import Base, enum_column, ts_column
from cvidee.store.enums import ChangeActor, EvaluationVerdict


class Change(Base):
    """A change the user (or installer) made to the installation, at ``changed_at_ts``.

    One change can touch several parameters at once (W-06: pump setting + max. flow);
    those are :class:`ChangeItem` rows, so overlap detection (FR-32) sees them together.
    """

    __tablename__ = "changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    human_id: Mapped[str] = mapped_column(String(16), unique=True)  # 'W-07', never reused
    changed_at_ts: Mapped[int] = ts_column(index=True)
    recorded_at_ts: Mapped[int] = ts_column()
    performed_by: Mapped[ChangeActor] = enum_column(ChangeActor, "performed_by")
    reason: Mapped[str | None] = mapped_column(Text)
    recommendation_id: Mapped[int | None] = mapped_column(
        ForeignKey("recommendations.id", ondelete="SET NULL")
    )

    items: Mapped[list["ChangeItem"]] = relationship(
        back_populates="change", cascade="all, delete-orphan", order_by="ChangeItem.ordinal"
    )
    evaluation: Mapped["ChangeEvaluation | None"] = relationship(
        back_populates="change", cascade="all, delete-orphan"
    )


class ChangeItem(Base):
    """One parameter of a change: key from the known list or ``custom`` + free label."""

    __tablename__ = "change_items"
    __table_args__ = (UniqueConstraint("change_id", "ordinal"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    change_id: Mapped[int] = mapped_column(ForeignKey("changes.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    parameter_key: Mapped[str] = mapped_column(String(64))  # e.g. 'max_flow_temperature'
    parameter_label: Mapped[str] = mapped_column(String(255))  # 'Maximale CV-aanvoer'
    old_value: Mapped[str] = mapped_column(String(255))  # display text, '70 °C'
    new_value: Mapped[str] = mapped_column(String(255))
    old_value_num: Mapped[float | None] = mapped_column(Float)
    new_value_num: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(16))
    # If the parameter is an installation spec, the spec key it updated.
    spec_key: Mapped[str | None] = mapped_column(String(64))

    change: Mapped[Change] = relationship(back_populates="items")


class ChangeEvaluation(Base):
    """Current before/after evaluation of a change; recomputed in place (one per change)."""

    __tablename__ = "change_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    change_id: Mapped[int] = mapped_column(
        ForeignKey("changes.id", ondelete="CASCADE"), unique=True
    )
    computed_at_ts: Mapped[int] = ts_column()
    reference_start_ts: Mapped[int] = ts_column()
    reference_end_ts: Mapped[int] = ts_column()
    observation_start_ts: Mapped[int] = ts_column()
    observation_end_ts: Mapped[int] = ts_column()
    verdict: Mapped[EvaluationVerdict] = enum_column(EvaluationVerdict, "verdict")
    summary: Mapped[str | None] = mapped_column(Text)
    rollback_triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    # [{check, reference, observation, outcome: ok|limited|failed|excluded}]
    comparability: Mapped[list[Any]] = mapped_column(default=list)
    # [{metric, note, before, after, unit, effect, good: bool|None, coverage_before, …}]
    metrics: Mapped[list[Any]] = mapped_column(default=list)
    excluded_periods: Mapped[list[Any]] = mapped_column(default=list)  # special period ids
    overlapping_change_ids: Mapped[list[Any]] = mapped_column(default=list)
    rule_version: Mapped[str] = mapped_column(String(32))
    config_hash: Mapped[str] = mapped_column(String(64))

    change: Mapped[Change] = relationship(back_populates="evaluation")
