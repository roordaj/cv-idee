"""Findings, evidence, hypotheses, recommendations and their snapshots (FR-21 to FR-28, FR-41)."""

from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cvidee.store.base import Base, enum_column, ts_column
from cvidee.store.enums import (
    Certainty,
    EvidenceKind,
    FindingLifecycle,
    RecommendationOutcome,
    RecommendationStatus,
    ResolutionReason,
    Severity,
    SnapshotTrigger,
)


class Finding(Base):
    """One problem, deduplicated on (rule_id, scope_key) while active (FR-39).

    Observation, interpretation and advice are separate (FR-21): ``observation`` and
    ``interpretation`` here, advice in :class:`Recommendation`.
    """

    __tablename__ = "findings"
    __table_args__ = (
        Index(
            "uq_findings_active_key",
            "rule_id",
            "scope_key",
            unique=True,
            sqlite_where=text("lifecycle = 'active'"),
            postgresql_where=text("lifecycle = 'active'"),
        ),
        Index("ix_findings_lifecycle_last_seen_ts", "lifecycle", "last_seen_ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    human_id: Mapped[str] = mapped_column(String(16), unique=True)  # 'B-014', never reused
    rule_id: Mapped[str] = mapped_column(String(64))
    rule_version: Mapped[str] = mapped_column(String(32))
    rule_params: Mapped[dict[str, Any]] = mapped_column(default=dict)
    scope_key: Mapped[str] = mapped_column(String(128), default="")
    category: Mapped[str] = mapped_column(String(32))  # cycles, temperature, data_quality, …
    title: Mapped[str] = mapped_column(String(255))
    severity: Mapped[Severity] = enum_column(Severity, "severity")
    certainty: Mapped[Certainty] = enum_column(Certainty, "certainty")
    relevance: Mapped[list[Any]] = mapped_column(default=list)  # ['energy', 'comfort', …]
    observation: Mapped[str] = mapped_column(Text)
    interpretation: Mapped[str] = mapped_column(Text)
    no_advice_text: Mapped[str | None] = mapped_column(Text)  # why there is no advice
    period_start_ts: Mapped[int] = ts_column()
    period_end_ts: Mapped[int] = ts_column()
    period_note: Mapped[str | None] = mapped_column(String(255))  # '1 tapwatercyclus uitgesl.'
    signals: Mapped[list[Any]] = mapped_column(default=list)  # roles used
    # Onderbouwing (FR-22): {coverage, unknown_ms, relevant_cycles, total_cycles,
    # repetition_days, repetition_window_days, missing_signals[]}; shape owned by #10/#34.
    support: Mapped[dict[str, Any]] = mapped_column(default=dict)
    priority_score: Mapped[float] = mapped_column(Float, default=0.0)
    priority_explanation: Mapped[dict[str, Any]] = mapped_column(default=dict)
    lifecycle: Mapped[FindingLifecycle] = enum_column(FindingLifecycle, "lifecycle")
    resolution_reason: Mapped[ResolutionReason | None] = enum_column(
        ResolutionReason, "resolution_reason", nullable=True
    )
    first_seen_ts: Mapped[int] = ts_column()
    last_seen_ts: Mapped[int] = ts_column()
    resolved_at_ts: Mapped[int | None] = ts_column(nullable=True)
    last_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL")
    )

    hypotheses: Mapped[list["FindingHypothesis"]] = relationship(
        back_populates="finding",
        cascade="all, delete-orphan",
        order_by="FindingHypothesis.ordinal",
    )
    evidence: Mapped[list["FindingEvidence"]] = relationship(
        back_populates="finding", cascade="all, delete-orphan"
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="finding")


class FindingHypothesis(Base):
    """Possible cause with evidence for/against and a distinguishing measurement (FR-23)."""

    __tablename__ = "finding_hypotheses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))
    evidence_for: Mapped[str | None] = mapped_column(Text)
    evidence_against: Mapped[str | None] = mapped_column(Text)
    distinguishing_measurement: Mapped[str | None] = mapped_column(Text)

    finding: Mapped[Finding] = relationship(back_populates="hypotheses")


class FindingEvidence(Base):
    """Pointer to the data behind a finding (FR-37).

    Cycles are referenced by their deterministic key ``cycle_start_ts`` (no FK: derived
    rows are replaced per window but keep their key).
    """

    __tablename__ = "finding_evidence"
    __table_args__ = (Index("ix_finding_evidence_finding_id_kind", "finding_id", "kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"))
    kind: Mapped[EvidenceKind] = enum_column(EvidenceKind, "kind")
    cycle_start_ts: Mapped[int | None] = ts_column(nullable=True)
    role: Mapped[str | None] = mapped_column(String(64))
    scope_key: Mapped[str | None] = mapped_column(String(128))
    start_ts: Mapped[int | None] = ts_column(nullable=True)
    end_ts: Mapped[int | None] = ts_column(nullable=True)
    metric: Mapped[str | None] = mapped_column(String(64))
    value_num: Mapped[float | None] = mapped_column(Float)
    change_id: Mapped[int | None] = mapped_column(ForeignKey("changes.id", ondelete="SET NULL"))
    # For bundled candidates (FR-26): original rule + version + summary text.
    rule_id: Mapped[str | None] = mapped_column(String(64))
    rule_version: Mapped[str | None] = mapped_column(String(32))
    summary: Mapped[str | None] = mapped_column(Text)

    finding: Mapped[Finding] = relationship(back_populates="evidence")


class Recommendation(Base):
    """Advice for a finding (FR-25) with follow-up status (FR-27)."""

    __tablename__ = "recommendations"
    __table_args__ = (Index("ix_recommendations_status", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(64))
    rule_version: Mapped[str] = mapped_column(String(32))
    is_additional_measurement: Mapped[bool] = mapped_column(Boolean, default=False)  # FR-28
    action: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    expected_effect: Mapped[str] = mapped_column(Text)
    comfort_impact: Mapped[str | None] = mapped_column(Text)
    magnitude: Mapped[str] = mapped_column(Text)  # or explicit "niet te onderbouwen"
    magnitude_substantiated: Mapped[bool] = mapped_column(Boolean, default=False)
    conditions: Mapped[str | None] = mapped_column(Text)
    evaluation: Mapped[str | None] = mapped_column(Text)
    success_criterion: Mapped[str | None] = mapped_column(Text)
    rollback_criterion: Mapped[str | None] = mapped_column(Text)
    follow_up: Mapped[str | None] = mapped_column(Text)  # "Daarna"
    # Machine-checkable criteria, e.g. {"metric": "room_cold_hours_per_week",
    # "scope_key": "room:slaapkamer", "op": ">", "threshold": 4}. Per-advice override (§7.9).
    success_spec: Mapped[dict[str, Any] | None] = mapped_column()
    rollback_spec: Mapped[dict[str, Any] | None] = mapped_column()
    status: Mapped[RecommendationStatus] = enum_column(RecommendationStatus, "status")
    postponed_until_ts: Mapped[int | None] = ts_column(nullable=True)
    outcome: Mapped[RecommendationOutcome] = enum_column(RecommendationOutcome, "outcome")
    created_at_ts: Mapped[int] = ts_column()
    status_changed_at_ts: Mapped[int] = ts_column()

    finding: Mapped[Finding] = relationship(back_populates="recommendations")
    notes: Mapped[list["RecommendationNote"]] = relationship(
        back_populates="recommendation", cascade="all, delete-orphan"
    )


class RecommendationNote(Base):
    """User note / explanation on a recommendation (FR-27)."""

    __tablename__ = "recommendation_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("recommendations.id", ondelete="CASCADE"), index=True
    )
    created_at_ts: Mapped[int] = ts_column()
    text: Mapped[str] = mapped_column(Text)

    recommendation: Mapped[Recommendation] = relationship(back_populates="notes")


class RecommendationSnapshot(Base):
    """Immutable advice-history entry (FR-41), written on create and every status change."""

    __tablename__ = "recommendation_snapshots"
    __table_args__ = (
        Index(
            "ix_recommendation_snapshots_recommendation_id_taken_at_ts",
            "recommendation_id",
            "taken_at_ts",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(ForeignKey("recommendations.id"))
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id"))
    taken_at_ts: Mapped[int] = ts_column()
    trigger: Mapped[SnapshotTrigger] = enum_column(SnapshotTrigger, "trigger")
    status: Mapped[RecommendationStatus] = enum_column(RecommendationStatus, "status")
    outcome: Mapped[RecommendationOutcome] = enum_column(RecommendationOutcome, "outcome")
    measurement_start_ts: Mapped[int] = ts_column()
    measurement_end_ts: Mapped[int] = ts_column()
    rule_id: Mapped[str] = mapped_column(String(64))
    rule_version: Mapped[str] = mapped_column(String(32))
    rule_params: Mapped[dict[str, Any]] = mapped_column(default=dict)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("installation_profiles.id"))
    settings_revision_id: Mapped[int | None] = mapped_column(ForeignKey("settings_revisions.id"))
    config_hash: Mapped[str] = mapped_column(String(64))
    # Relevant settings/specs as shown then ("Max aanvoer 60 °C · pomp 2").
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict)
    # Full rendered finding + recommendation as they were (the "waarom").
    content: Mapped[dict[str, Any]] = mapped_column(default=dict)
    note: Mapped[str | None] = mapped_column(Text)
