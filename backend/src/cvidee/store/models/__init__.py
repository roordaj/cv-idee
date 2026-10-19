"""SQLAlchemy ORM models for every table in ADR-001 (``docs/adr/001-datamodel.md``).

Importing this package registers all tables on :data:`Base.metadata`.
"""

from cvidee.store.base import Base
from cvidee.store.models.changes import Change, ChangeEvaluation, ChangeItem, Experiment
from cvidee.store.models.derived import (
    AnalysisRun,
    BurnerCycle,
    ImportJob,
    MetricValue,
    ModeSegment,
    QualityEvent,
)
from cvidee.store.models.findings import (
    Finding,
    FindingEvidence,
    FindingHypothesis,
    Recommendation,
    RecommendationNote,
    RecommendationSnapshot,
)
from cvidee.store.models.notifications import Notification, NotificationPolicy, NotificationState
from cvidee.store.models.observations import ConnectionEvent, Observation
from cvidee.store.models.profile import (
    InstallationProfile,
    InstallationSpec,
    ProfileCircuit,
    ProfileRoom,
    ProfileZone,
    SpecialPeriod,
)
from cvidee.store.models.settings import SettingsRevision
from cvidee.store.models.signals import SignalDefinition, SignalMapping, SourceEntity

__all__ = [
    "AnalysisRun",
    "Base",
    "BurnerCycle",
    "Change",
    "ChangeEvaluation",
    "ChangeItem",
    "ConnectionEvent",
    "Experiment",
    "Finding",
    "FindingEvidence",
    "FindingHypothesis",
    "ImportJob",
    "InstallationProfile",
    "InstallationSpec",
    "MetricValue",
    "ModeSegment",
    "Notification",
    "NotificationPolicy",
    "NotificationState",
    "Observation",
    "ProfileCircuit",
    "ProfileRoom",
    "ProfileZone",
    "QualityEvent",
    "Recommendation",
    "RecommendationNote",
    "RecommendationSnapshot",
    "SettingsRevision",
    "SignalDefinition",
    "SignalMapping",
    "SourceEntity",
    "SpecialPeriod",
]
