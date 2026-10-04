"""Persisted enumerations (ADR-001).

The *values* are the storage contract: they are written as TEXT and protected by a
CHECK constraint for closed sets. Open sets that are expected to grow (rule ids,
specification keys, metric names, setting keys, categories) are plain TEXT and validated
in code, so adding a value never needs a migration.

Enums of the analysis contract (ADR-002) are owned by :mod:`cvidee.analysis.types`, those of
the rule contract (ADR-004: ``Certainty``, ``Severity``, ``SpecialPeriodKind``,
``CircuitKind``) by :mod:`cvidee.rules.base`; both are re-exported here. ``cvidee.store``
may import ``cvidee.analysis`` and ``cvidee.rules``, never the other way round.
``ValueKind`` is an ``IntEnum`` there (ordered by strength) and is stored as
its lower-case name.
"""

from enum import StrEnum

from cvidee.analysis.types import (
    ConnectionSource,
    EndReason,
    MetricName,
    MetricWindowKind,
    Mode,
    ModeCertainty,
    ObservationKind,
    QualityEventKind,
    ValueKind,
)
from cvidee.rules.base import Certainty, CircuitKind, Severity, SpecialPeriodKind

__all__ = [
    "Certainty",
    "ChangeActor",
    "CircuitKind",
    "ConnectionSource",
    "DeliveryStatus",
    "EmitterType",
    "EndReason",
    "EvaluationVerdict",
    "EvidenceKind",
    "FindingLifecycle",
    "ImportStatus",
    "MetricName",
    "MetricStatus",
    "MetricWindowKind",
    "Mode",
    "ModeCertainty",
    "NotificationChannel",
    "NotificationKind",
    "ObservationKind",
    "ObservationOrigin",
    "QualityEventKind",
    "RecommendationOutcome",
    "RecommendationStatus",
    "ResolutionReason",
    "RunStatus",
    "RunTrigger",
    "Severity",
    "SnapshotTrigger",
    "SpecStatus",
    "SpecialPeriodKind",
    "TriState",
    "ValueKind",
]


class ObservationOrigin(StrEnum):
    LIVE = "live"
    IMPORT = "import"


class SpecStatus(StrEnum):
    """Explicit status of an installation specification (FR-03): never NULL-means-unknown."""

    KNOWN = "known"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class EmitterType(StrEnum):
    RADIATOR = "radiator"
    UNDERFLOOR = "underfloor"
    OTHER = "other"
    UNKNOWN = "unknown"


class TriState(StrEnum):
    """Boolean fact that can also be explicitly unknown (e.g. heat demand after a stop)."""

    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


class MetricStatus(StrEnum):
    OK = "ok"
    INSUFFICIENT_DATA = "insufficient_data"


class RunTrigger(StrEnum):
    LIVE = "live"
    IMPORT = "import"
    RECOMPUTE = "recompute"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SUPERSEDED = "superseded"


class ImportStatus(StrEnum):
    PENDING = "pending"  # wachtend
    FETCHING = "fetching"  # ophalen
    ANALYSING = "analysing"  # analyseren
    DONE = "done"  # klaar
    INTERRUPTED = "interrupted"  # onderbroken
    FAILED = "failed"  # mislukt
    CANCELLED = "cancelled"  # geannuleerd


class FindingLifecycle(StrEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"


class ResolutionReason(StrEnum):
    RECOVERED = "recovered"  # recovery criterion met
    SETTINGS_CHANGED = "settings_changed"  # no longer a finding under new thresholds
    RULE_CHANGED = "rule_changed"
    SUPERSEDED = "superseded"  # merged into another finding


class EvidenceKind(StrEnum):
    CYCLE = "cycle"
    SIGNAL = "signal"
    TIME_RANGE = "time_range"
    METRIC = "metric"
    QUALITY_EVENT = "quality_event"
    CHANGE = "change"
    BUNDLED_CANDIDATE = "bundled_candidate"


class RecommendationStatus(StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    POSTPONED = "postponed"
    DONE = "done"
    REJECTED = "rejected"
    ROLLBACK_TRIGGERED = "rollback_triggered"


class RecommendationOutcome(StrEnum):
    """FR-25: after execution a recommendation is succeeded, unfavourable or undecided."""

    PENDING = "pending"
    SUCCEEDED = "succeeded"
    UNFAVOURABLE = "unfavourable"
    UNDECIDED = "undecided"


class SnapshotTrigger(StrEnum):
    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    CONTENT_UPDATED = "content_updated"


class ChangeActor(StrEnum):
    USER = "user"
    INSTALLER = "installer"
    OTHER = "other"


class EvaluationVerdict(StrEnum):
    PENDING = "pending"  # observation period not complete yet ("Evaluatie loopt")
    IMPROVED = "improved"
    WORSENED = "worsened"
    TRADE_OFF = "trade_off"
    NOT_ATTRIBUTABLE = "not_attributable"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class NotificationChannel(StrEnum):
    DIRECT = "direct"
    DAILY_DIGEST = "daily_digest"
    WEEKLY_REPORT = "weekly_report"
    NONE = "none"


class NotificationKind(StrEnum):
    FINDING_NEW = "finding_new"
    FINDING_WORSENED = "finding_worsened"
    FINDING_RESOLVED = "finding_resolved"
    DAILY_DIGEST = "daily_digest"
    WEEKLY_REPORT = "weekly_report"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SUPPRESSED = "suppressed"
