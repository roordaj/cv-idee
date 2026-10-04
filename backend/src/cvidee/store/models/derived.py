"""Derived data (ADR-002 deterministic keys, replace-from upsert), runs and import jobs.

The four derived tables mirror the result types in :mod:`cvidee.analysis.types`. The
runner deletes every derived row with key ``>= emit_from`` and inserts the run's output in
one transaction; every key column therefore has an index whose first column is the time.
"""

from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from cvidee.store.base import Base, enum_column, ts_column
from cvidee.store.enums import (
    ConnectionSource,
    EndReason,
    ImportStatus,
    MetricStatus,
    MetricWindowKind,
    Mode,
    ModeCertainty,
    QualityEventKind,
    RunStatus,
    RunTrigger,
    TriState,
    ValueKind,
)

_RUN_FK = "analysis_runs.id"
_MODE_VALUES = ", ".join(f"'{m.value}'" for m in Mode)


class AnalysisRun(Base):
    """One runner execution, or a queued recompute request (``status = 'queued'``).

    Window per ADR-002 §4: ``[context_start, end)`` with output keys ``>= emit_from``;
    ``watermark_ts`` is the ``next_watermark`` stored after success. A queued request only
    has ``emit_from_ts`` (the point to recompute from, e.g. a mapping's ``valid_from``).
    """

    __tablename__ = "analysis_runs"
    __table_args__ = (Index("ix_analysis_runs_status_trigger", "status", "trigger"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trigger: Mapped[RunTrigger] = enum_column(RunTrigger, "trigger")
    status: Mapped[RunStatus] = enum_column(RunStatus, "status")
    reason: Mapped[str | None] = mapped_column(String(255))  # e.g. 'settings_changed'
    emit_from_ts: Mapped[int] = ts_column()
    context_start_ts: Mapped[int | None] = ts_column(nullable=True)
    horizon_ts: Mapped[int | None] = ts_column(nullable=True)  # AnalysisWindow.end
    watermark_ts: Mapped[int | None] = ts_column(nullable=True)  # next_watermark on success
    requested_at_ts: Mapped[int] = ts_column()
    started_at_ts: Mapped[int | None] = ts_column(nullable=True)
    finished_at_ts: Mapped[int | None] = ts_column(nullable=True)
    rule_versions: Mapped[dict[str, Any]] = mapped_column(default=dict)  # rule_id -> semver
    config_hash: Mapped[str | None] = mapped_column(String(64))
    settings_revision_id: Mapped[int | None] = mapped_column(ForeignKey("settings_revisions.id"))
    import_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_jobs.id", ondelete="SET NULL")
    )
    stats: Mapped[dict[str, Any]] = mapped_column(default=dict)
    errors: Mapped[list[Any]] = mapped_column(default=list)


class ImportJob(Base):
    """Resumable historical import from HA (FR-06, aanvullingen §4)."""

    __tablename__ = "import_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[ImportStatus] = enum_column(ImportStatus, "status")
    from_ts: Mapped[int] = ts_column()
    to_ts: Mapped[int] = ts_column()
    roles: Mapped[list[Any] | None] = mapped_column()  # NULL = all mapped roles
    cursor_ts: Mapped[int | None] = ts_column(nullable=True)  # resume point (block start)
    blocks_done: Mapped[int] = mapped_column(Integer, default=0)
    blocks_total: Mapped[int] = mapped_column(Integer, default=0)
    observations_imported: Mapped[int] = mapped_column(Integer, default=0)
    duplicates_skipped: Mapped[int] = mapped_column(Integer, default=0)
    earliest_available_ts: Mapped[int | None] = ts_column(nullable=True)
    cycles_found: Mapped[int | None] = mapped_column(Integer)
    coverage: Mapped[float | None] = mapped_column(Float)  # 0..1
    per_signal: Mapped[list[Any]] = mapped_column(default=list)  # [{role, observations, first_ts}]
    errors: Mapped[list[Any]] = mapped_column(default=list)
    created_at_ts: Mapped[int] = ts_column()
    started_at_ts: Mapped[int | None] = ts_column(nullable=True)
    finished_at_ts: Mapped[int | None] = ts_column(nullable=True)


class QualityEvent(Base):
    """``analysis.types.QualityEvent``, split on whole UTC hours. Key: (kind, signal, start)."""

    __tablename__ = "quality_events"
    __table_args__ = (
        # COALESCE: SQLite treats NULLs as distinct in a unique index; '' = no source.
        Index(
            "uq_quality_events_key",
            "kind",
            "signal",
            "other_signal",
            text("coalesce(source, '')"),
            "start_ts",
            unique=True,
        ),
        Index("ix_quality_events_start_ts", "start_ts"),
        CheckConstraint("end_ts IS NULL OR end_ts >= start_ts", name="end_not_before_start"),
        CheckConstraint("NOT (final AND end_ts IS NULL)", name="ongoing_not_final"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[QualityEventKind] = enum_column(QualityEventKind, "kind")
    # str(SignalRef), e.g. 'flow_temperature@boiler'; '' = all signals (SignalRef None).
    signal: Mapped[str] = mapped_column(String(160))
    # Only for CONNECTION_LOST (ADR-003 §6.3); NULL otherwise.
    source: Mapped[ConnectionSource | None] = enum_column(ConnectionSource, "source", nullable=True)
    # Second signal of a MISALIGNED pair; '' = none.
    other_signal: Mapped[str] = mapped_column(String(160), default="", server_default="")
    start_ts: Mapped[int] = ts_column()
    end_ts: Mapped[int | None] = ts_column(nullable=True)  # NULL = ongoing at the horizon
    count: Mapped[int | None] = mapped_column(Integer)  # affected observations (DUPLICATE)
    detail: Mapped[str] = mapped_column(Text, default="")
    final: Mapped[bool] = mapped_column(Boolean)
    run_id: Mapped[int | None] = mapped_column(ForeignKey(_RUN_FK, ondelete="SET NULL"))


class ModeSegment(Base):
    """``analysis.types.ModeSegment``, split on whole UTC hours. Key: ``start_ts``."""

    __tablename__ = "mode_segments"
    __table_args__ = (
        CheckConstraint("end_ts > start_ts", name="end_after_start"),
        CheckConstraint(
            "(mode = 'unknown') = (certainty = 'none')", name="unknown_iff_no_certainty"
        ),
    )

    start_ts: Mapped[int] = ts_column(primary_key=True)
    end_ts: Mapped[int] = ts_column()
    mode: Mapped[Mode] = enum_column(Mode, "mode")
    certainty: Mapped[ModeCertainty] = enum_column(ModeCertainty, "certainty")
    sources: Mapped[list[Any]] = mapped_column(default=list)  # [str(SignalRef)]
    # Boiler fault/blocking code for FAULT/BLOCKED segments (requirements §8); NULL = none.
    device_code: Mapped[str | None] = mapped_column(String(64))
    final: Mapped[bool] = mapped_column(Boolean)
    run_id: Mapped[int | None] = mapped_column(ForeignKey(_RUN_FK, ondelete="SET NULL"))


class BurnerCycle(Base):
    """``analysis.types.BurnerCycle`` (FR-12). Key: ``start_ts``.

    ``end_ts`` NULL = still burning at the horizon (open, provisional, no end reason).
    Incomplete durations are lower bounds ("≥ 4:00"). "Short" is not stored: it depends on
    a threshold setting and is computed from complete CH cycles when summarising.
    """

    __tablename__ = "burner_cycles"
    __table_args__ = (
        Index("ix_burner_cycles_end_ts", "end_ts"),
        CheckConstraint(
            "end_ts IS NOT NULL OR (end_reason IS NULL AND NOT complete AND NOT final)",
            name="open_cycle_provisional",
        ),
        CheckConstraint(
            "end_ts IS NULL OR (end_ts > start_ts AND end_reason IS NOT NULL)",
            name="closed_cycle_has_end_reason",
        ),
        CheckConstraint("duration_ms >= 0", name="duration_not_negative"),
    )

    start_ts: Mapped[int] = ts_column(primary_key=True)
    end_ts: Mapped[int | None] = ts_column(nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    complete: Mapped[bool] = mapped_column(Boolean)
    start_observed: Mapped[bool] = mapped_column(Boolean)
    mode: Mapped[Mode] = enum_column(Mode, "mode")
    end_reason: Mapped[EndReason | None] = enum_column(EndReason, "end_reason", nullable=True)
    phases: Mapped[list[Any]] = mapped_column(default=list)  # [{phase, start, end}]
    # CycleAggregates. NULL = signal unknown / not mapped (as in the analysis type).
    flow_setpoint_c: Mapped[float | None] = mapped_column(Float)
    flow_max_c: Mapped[float | None] = mapped_column(Float)
    flow_mean_c: Mapped[float | None] = mapped_column(Float)
    return_mean_c: Mapped[float | None] = mapped_column(Float)
    modulation_mean_pct: Mapped[float | None] = mapped_column(Float)
    modulation_min_pct: Mapped[float | None] = mapped_column(Float)
    heat_demand_during: Mapped[TriState] = enum_column(TriState, "heat_demand_during")
    heat_demand_after_stop: Mapped[TriState] = enum_column(TriState, "heat_demand_after_stop")
    signal_coverage: Mapped[float] = mapped_column(Float)
    pause_before_ms: Mapped[int | None] = mapped_column(Integer)
    final: Mapped[bool] = mapped_column(Boolean)
    run_id: Mapped[int | None] = mapped_column(ForeignKey(_RUN_FK, ondelete="SET NULL"))


class MetricValue(Base):
    """``analysis.types.MetricValue``.

    Key (ADR-002 §3.5): ``(name, mode, window_kind, window_start_ts, cycle_start_ts)``.
    Sentinels instead of NULL so the key works in SQLite: ``mode = ''`` means all modes,
    ``cycle_start_ts = -1`` means "not a cycle window".
    """

    __tablename__ = "metric_values"
    __table_args__ = (
        Index("ix_metric_values_window_start_ts", "window_start_ts"),
        CheckConstraint("(status = 'ok') = (value_num IS NOT NULL)", name="value_iff_ok"),
        CheckConstraint(f"mode IN ('', {_MODE_VALUES})", name="mode"),
        CheckConstraint(
            "(window_kind = 'cycle') = (cycle_start_ts >= 0)", name="cycle_start_iff_cycle"
        ),
        CheckConstraint("coverage >= 0 AND coverage <= 1", name="coverage_fraction"),
    )

    name: Mapped[str] = mapped_column(String(64), primary_key=True)  # MetricName value
    mode: Mapped[str] = mapped_column(String(16), primary_key=True, default="")
    window_kind: Mapped[MetricWindowKind] = enum_column(
        MetricWindowKind, "window_kind", primary_key=True
    )
    window_start_ts: Mapped[int] = ts_column(primary_key=True)
    cycle_start_ts: Mapped[int] = ts_column(primary_key=True)
    window_end_ts: Mapped[int] = ts_column()
    status: Mapped[MetricStatus] = enum_column(MetricStatus, "status")
    value_num: Mapped[float | None] = mapped_column(Float)  # present iff status = 'ok'
    unit: Mapped[str] = mapped_column(String(16))
    time_basis_seconds: Mapped[float] = mapped_column(Float)  # FR-13 time basis
    coverage: Mapped[float] = mapped_column(Float)  # 0..1 (FR-11)
    provenance_kind: Mapped[ValueKind] = enum_column(ValueKind, "provenance_kind")
    final: Mapped[bool] = mapped_column(Boolean)
    run_id: Mapped[int | None] = mapped_column(ForeignKey(_RUN_FK, ondelete="SET NULL"))
