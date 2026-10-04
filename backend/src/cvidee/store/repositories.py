"""Repository interfaces per aggregate (ADR-001 §8).

* Raw data uses storage-neutral records (:mod:`cvidee.store.records`); derived data and
  connection events use the analysis types from :mod:`cvidee.analysis.types` (ADR-002).
  These are the parts a TimescaleDB implementation would replace.
* Configuration/document aggregates use the ORM entities from :mod:`cvidee.store.models`;
  they stay relational under any backend and SQLAlchemy keeps them dialect-portable.

Repositories never commit: the caller owns the session/transaction (unit of work).
Concrete implementations live in their own modules and belong to the implementing
tickets (observations #16, signals #18, profile #20, periods #21, settings #22,
runner #27, findings #34/#36/#37, changes #38/#39, notifications #41). Only trivial
SQL implementations are provided here.
"""

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from cvidee.analysis.types import (
    BurnerCycle,
    ConnectionEvent,
    MetricValue,
    MetricWindowKind,
    ModeSegment,
    PipelineResult,
    QualityEvent,
)
from cvidee.store.enums import NotificationChannel, Severity
from cvidee.store.models import (
    AnalysisRun,
    Change,
    ChangeEvaluation,
    Finding,
    ImportJob,
    InstallationProfile,
    Notification,
    NotificationPolicy,
    Recommendation,
    RecommendationSnapshot,
    SettingsRevision,
    SignalDefinition,
    SignalMapping,
    SourceEntity,
    SpecialPeriod,
)
from cvidee.store.records import InsertResult, ObservationRecord


class StaleRevisionError(Exception):
    """Optimistic-lock failure: the revision the caller based its edit on is not current."""


# --------------------------------------------------------------------------- time series


class ObservationRepository(Protocol):
    """Raw observations and connection events (#16)."""

    def add_observations(self, records: Iterable[ObservationRecord]) -> InsertResult:
        """Insert, ignoring duplicates on (entity, ts, state)."""
        ...

    def observations(self, entity_id: str, start_ts: int, end_ts: int) -> list[ObservationRecord]:
        """Observations in ``[start_ts, end_ts)`` ordered by ts."""
        ...

    def last_before(self, entity_id: str, ts: int) -> ObservationRecord | None: ...

    def add_connection_events(self, events: Iterable[ConnectionEvent]) -> InsertResult: ...

    def connection_events(self, start_ts: int, end_ts: int) -> list[ConnectionEvent]: ...

    def purge_before(self, ts: int) -> int:
        """Retention: delete raw rows older than ``ts``; returns the number deleted."""
        ...


class DerivedDataRepository(Protocol):
    """Derived tables (cycles, mode segments, quality events, metric values), runner only."""

    def replace_from(self, emit_from_ts: int, result: PipelineResult, run_id: int) -> None:
        """ADR-002 §4.2: delete all derived rows with key ``>= emit_from_ts`` and insert the
        result's items, within the caller's transaction (one commit for the whole run)."""
        ...

    def mode_segments(self, start_ts: int, end_ts: int) -> list[ModeSegment]: ...

    def burner_cycles(self, start_ts: int, end_ts: int) -> list[BurnerCycle]: ...

    def quality_events(self, start_ts: int, end_ts: int) -> list[QualityEvent]: ...

    def metric_values(
        self, window_kind: MetricWindowKind, start_ts: int, end_ts: int
    ) -> list[MetricValue]: ...


class AnalysisRunRepository(Protocol):
    """Runs and queued recompute requests (#27)."""

    def enqueue(self, run: AnalysisRun) -> AnalysisRun:
        """Queue a recompute from ``run.emit_from_ts`` (config change, late data, edit)."""
        ...

    def start(self, run: AnalysisRun) -> AnalysisRun: ...

    def finish(self, run: AnalysisRun) -> None: ...

    def effective_watermark(self) -> int | None:
        """``min(last successful watermark, emit_from of queued requests)``; None if empty."""
        ...


class ImportJobRepository(Protocol):
    """Historical import progress (#19)."""

    def add(self, job: ImportJob) -> ImportJob: ...

    def get(self, job_id: int) -> ImportJob | None: ...

    def active(self) -> ImportJob | None: ...

    def latest(self) -> ImportJob | None: ...


# ------------------------------------------------------------------------- configuration


class SignalRepository(Protocol):
    """Catalogue sync, source entities and versioned mappings (#18)."""

    def sync_definitions(self, definitions: Sequence[SignalDefinition]) -> None: ...

    def ensure_source_entity(self, entity_id: str, now_ts: int) -> SourceEntity: ...

    def current_mappings(self) -> list[SignalMapping]: ...

    def mappings_at(self, ts: int) -> list[SignalMapping]: ...

    def history(self, role: str, scope_key: str = "") -> list[SignalMapping]: ...

    def replace_mapping(self, mapping: SignalMapping) -> SignalMapping:
        """Close the current mapping for (role, scope) at ``mapping.valid_from_ts``, add new."""
        ...

    def unlink(self, role: str, scope_key: str, at_ts: int) -> None: ...


class InstallationProfileRepository(Protocol):
    """Versioned installation profile (#20)."""

    def current(self) -> InstallationProfile | None: ...

    def at(self, ts: int) -> InstallationProfile | None: ...

    def get(self, profile_id: int) -> InstallationProfile | None: ...

    def save_new_version(self, profile: InstallationProfile) -> InstallationProfile:
        """Close the current version at ``profile.valid_from_ts`` and add ``profile``."""
        ...


class SpecialPeriodRepository(Protocol):
    """Special periods (#21); editable, so ``update`` bumps ``updated_at_ts``."""

    def in_range(
        self, start_ts: int | None = None, end_ts: int | None = None
    ) -> list[SpecialPeriod]:
        """Periods overlapping ``[start_ts, end_ts)`` (open-ended periods included)."""
        ...

    def get(self, period_id: int) -> SpecialPeriod | None: ...

    def add(self, period: SpecialPeriod) -> SpecialPeriod: ...

    def update(self, period: SpecialPeriod, now_ts: int) -> SpecialPeriod: ...

    def delete(self, period_id: int) -> None: ...


class SettingsRepository(Protocol):
    """Append-only settings revisions (#22)."""

    def current(self) -> SettingsRevision | None: ...

    def save(
        self,
        values: Mapping[str, Any],
        *,
        based_on: int | None,
        config_hash: str,
        now_ts: int,
        changed_by: str | None = None,
    ) -> SettingsRevision:
        """Append a revision; raise :class:`StaleRevisionError` if ``based_on`` is stale."""
        ...

    def history(self, limit: int = 50) -> list[SettingsRevision]: ...


class NotificationPolicyRepository(Protocol):
    def get_all(self) -> dict[Severity, NotificationChannel]: ...

    def set(self, severity: Severity, channel: NotificationChannel, now_ts: int) -> None: ...


# ----------------------------------------------------------------------------- documents


class FindingRepository(Protocol):
    """Findings with hypotheses and evidence (#34, #35)."""

    def get(self, finding_id: int) -> Finding | None: ...

    def by_human_id(self, human_id: str) -> Finding | None: ...

    def active_by_key(self, rule_id: str, scope_key: str) -> Finding | None: ...

    def list_findings(self, *, include_resolved: bool = False) -> list[Finding]: ...

    def add(self, finding: Finding) -> Finding:
        """Insert and assign the next ``human_id`` ('B-015')."""
        ...


class RecommendationRepository(Protocol):
    """Recommendations, notes and immutable snapshots (#36, #37)."""

    def get(self, recommendation_id: int) -> Recommendation | None: ...

    def for_finding(self, finding_id: int) -> list[Recommendation]: ...

    def add(self, recommendation: Recommendation) -> Recommendation: ...

    def add_snapshot(self, snapshot: RecommendationSnapshot) -> RecommendationSnapshot: ...

    def history(self) -> list[RecommendationSnapshot]: ...

    def due_postponed(self, now_ts: int) -> list[Recommendation]: ...


class ChangeRepository(Protocol):
    """Change log and evaluations (#38, #39)."""

    def get(self, change_id: int) -> Change | None: ...

    def in_range(self, start_ts: int | None = None, end_ts: int | None = None) -> list[Change]: ...

    def add(self, change: Change) -> Change:
        """Insert and assign the next ``human_id`` ('W-08')."""
        ...

    def save_evaluation(self, evaluation: ChangeEvaluation) -> ChangeEvaluation:
        """Upsert the single current evaluation of a change."""
        ...


class NotificationRepository(Protocol):
    """Sent/pending notifications (#41)."""

    def add(self, notification: Notification) -> Notification: ...

    def last_for_finding(self, finding_id: int) -> Notification | None: ...

    def recent(self, limit: int = 20) -> list[Notification]: ...

    def pending(self) -> list[Notification]: ...


# --------------------------------------------------------- trivial SQL implementations


class SqlSettingsRepository:
    """SQLAlchemy implementation of :class:`SettingsRepository`."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def current(self) -> SettingsRevision | None:
        stmt = select(SettingsRevision).order_by(SettingsRevision.id.desc()).limit(1)
        return self._session.scalars(stmt).first()

    def save(
        self,
        values: Mapping[str, Any],
        *,
        based_on: int | None,
        config_hash: str,
        now_ts: int,
        changed_by: str | None = None,
    ) -> SettingsRevision:
        current = self.current()
        current_id = current.id if current is not None else None
        if current_id != based_on:
            raise StaleRevisionError(f"based on {based_on}, current is {current_id}")
        revision = SettingsRevision(
            values=dict(values),
            config_hash=config_hash,
            created_at_ts=now_ts,
            changed_by=changed_by,
        )
        self._session.add(revision)
        self._session.flush()
        return revision

    def history(self, limit: int = 50) -> list[SettingsRevision]:
        stmt = select(SettingsRevision).order_by(SettingsRevision.id.desc()).limit(limit)
        return list(self._session.scalars(stmt))


class SqlNotificationPolicyRepository:
    """SQLAlchemy implementation of :class:`NotificationPolicyRepository`."""

    DEFAULTS: Mapping[Severity, NotificationChannel] = {
        Severity.HIGH: NotificationChannel.DIRECT,
        Severity.MEDIUM: NotificationChannel.DAILY_DIGEST,
        Severity.LOW: NotificationChannel.WEEKLY_REPORT,
        Severity.INFO: NotificationChannel.NONE,
    }

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_all(self) -> dict[Severity, NotificationChannel]:
        policy = dict(self.DEFAULTS)
        for row in self._session.scalars(select(NotificationPolicy)):
            policy[row.severity] = row.channel
        return policy

    def set(self, severity: Severity, channel: NotificationChannel, now_ts: int) -> None:
        row = self._session.get(NotificationPolicy, severity)
        if row is None:
            row = NotificationPolicy(severity=severity, channel=channel, updated_at_ts=now_ts)
            self._session.add(row)
        else:
            row.channel = channel
            row.updated_at_ts = now_ts
        self._session.flush()
