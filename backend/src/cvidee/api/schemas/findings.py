"""Findings, recommendations and recommendation history (FR-21-28, FR-37, FR-41)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from cvidee.api.schemas.common import ApiModel, TimeRange, UtcDateTime
from cvidee.rules.base import Category, RecommendationKind, Relevance
from cvidee.store.enums import (
    Certainty,
    FindingLifecycle,
    RecommendationOutcome,
    RecommendationStatus,
    Severity,
)


class RuleRef(ApiModel):
    id: str = Field(examples=["kort-branden"])
    version: str = Field(examples=["1.3"])


class FindingSummary(ApiModel):
    """List item (Bevindingen side list, Overzicht)."""

    id: str = Field(examples=["B-014"])
    category: Category
    title: str
    severity: Severity
    certainty: Certainty
    relevance: list[Relevance]
    lifecycle: FindingLifecycle = FindingLifecycle.ACTIVE
    status: RecommendationStatus = Field(description="Follow-up status (FR-27).")
    status_text: str = Field(description="E.g. 'Uitgesteld tot 11 okt'.")
    period: TimeRange
    when_text: str = Field(description="E.g. 'vandaag 06:00-10:10' or 'sinds 21 sep'.")


class FindingList(ApiModel):
    items: list[FindingSummary]
    open_count: int = Field(ge=0, description="Findings with status open or rollback.")


class EvidenceDisplay(ApiModel):
    """The four evidence tiles as shown in design v3."""

    coverage: str
    cycles: str
    repetition: str
    missing_signals: str


class Evidence(ApiModel):
    """Onderbouwing (FR-22) - structured facts plus their display texts."""

    coverage_pct: float | None = Field(ge=0, le=100)
    unknown_s: int = Field(ge=0)
    excluded_cycles: int = Field(ge=0)
    relevant_cycles: int | None = Field(ge=0)
    pattern_cycles: int | None = Field(ge=0)
    repetition_days: int | None = Field(ge=0)
    repetition_window_days: int | None = Field(ge=1)
    missing_signals: list[str] = Field(description="Signal ids or descriptions not available.")
    display: EvidenceDisplay


class HypothesisOut(ApiModel):
    number: int = Field(ge=1)
    name: str
    evidence_for: str
    missing: str
    distinguishing_measurement: str


class RecommendationOut(ApiModel):
    """Advice in the format of requirements §5 / FR-25; null fields are not shown."""

    kind: RecommendationKind
    action: str
    reason: str | None = None
    expected_effect: str | None = None
    comfort_impact: str | None = None
    magnitude: str | None = None
    conditions: str | None = None
    evaluation: str | None = None
    success_criterion: str | None = None
    rollback_criterion: str | None = None
    follow_up: str | None = None


class BundledEvidence(ApiModel):
    """A supporting candidate bundled into this finding (FR-26)."""

    text: str
    source: str = Field(description="Rule and version, e.g. 'Stop tijdens vraag · v1.1'.")
    rule: RuleRef | None = None
    scope_key: str | None = None
    period: TimeRange | None = None
    certainty: Certainty | None = None
    evidence: Evidence | None = None
    interpretation: str | None = None
    hypotheses: list[HypothesisOut] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    recommendation: RecommendationOut | None = None
    source_finding_id: str | None = None


class GlossaryTerm(ApiModel):
    term: str
    definition: str


class FindingNote(ApiModel):
    id: str
    text: str
    created_at: UtcDateTime


class EvidenceLink(ApiModel):
    """Link from a finding to the data it is based on (FR-37): shown as 'Toon in tijdlijn'."""

    kind: Literal["time_range", "cycle", "signal", "metric", "quality_event"]
    start: UtcDateTime | None = Field(
        default=None, description="Range start, or the cycle/metric/event start."
    )
    end: UtcDateTime | None = None
    signal: str | None = Field(default=None, examples=["flame@boiler"])
    label: str | None = None


class PriorityFactor(ApiModel):
    factor: Literal["severity", "certainty", "relevance", "recency"]
    value: str
    weight: float = Field(gt=0, le=1)


class PriorityOut(ApiModel):
    """Why the finding ranks where it does: score = product of the factor weights."""

    score: float
    formula: str
    factors: list[PriorityFactor]


class FindingDetail(FindingSummary):
    superseded_by: str | None = Field(default=None, description="Parent finding after bundling.")
    rule: RuleRef
    observation: str
    period_text: str
    signals_text: str
    interpretation: str
    hypotheses: list[HypothesisOut]
    evidence: Evidence
    recommendation: RecommendationOut | None
    no_advice_text: str | None
    bundle: list[BundledEvidence]
    glossary: list[GlossaryTerm]
    timeline_range: TimeRange | None = Field(
        description="Range for 'Toon in tijdlijn'; null when not cycle based."
    )
    postponed_until: UtcDateTime | None = None
    notes: list[FindingNote] = Field(default_factory=list)
    evidence_links: list[EvidenceLink] = Field(
        default_factory=list, description="Time ranges, cycles and signals behind the finding."
    )
    priority: PriorityOut | None = Field(
        default=None, description="Prioritisation and its explanation."
    )


class FindingStatusUpdate(ApiModel):
    """``POST /api/findings/{id}/status``; ``rollback_triggered`` is set by the app only."""

    status: Literal["open", "accepted", "postponed", "done", "rejected"]
    postponed_until: UtcDateTime | None = Field(
        default=None, description="Defaults to now + the 'Uitstellen standaard' setting."
    )


class FindingNoteCreate(ApiModel):
    text: str = Field(min_length=1, max_length=2000)


class HistoryEntry(ApiModel):
    """A recommendation snapshot as recorded at the time (FR-41)."""

    id: str
    recorded_at: UtcDateTime
    recommendation: str
    finding_id: str
    observation_period: TimeRange | None
    settings_text: str = Field(description="Relevant settings at the time.")
    rule: RuleRef
    status: RecommendationStatus
    outcome: RecommendationOutcome
    status_text: str
    reasoning: str
    note: str | None
    parameters: dict[str, Any] = Field(default_factory=dict)
    config_hash: str | None = None
    profile_version: str | None = None
    rule_now_text: str = Field(description="What changed in the rule since the snapshot.")
