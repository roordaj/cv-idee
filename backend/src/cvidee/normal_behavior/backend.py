"""Lifecycle operations and analysis-run capture for normal-behavior references."""

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cvidee.analysis.types import PipelineResult
from cvidee.api.problems import ProblemError, not_found
from cvidee.api.schemas.normal_behavior import (
    NormalBehaviorEventKind as EventKindOut,
)
from cvidee.api.schemas.normal_behavior import (
    NormalBehaviorEventOut,
    NormalBehaviorModelList,
    NormalBehaviorModelOut,
    NormalBehaviorNewVersion,
    NormalBehaviorReason,
)
from cvidee.api.schemas.normal_behavior import (
    NormalBehaviorStatus as StatusOut,
)
from cvidee.store.enums import (
    MetricName,
    MetricStatus,
    NormalBehaviorEventKind,
    NormalBehaviorStatus,
)
from cvidee.store.models import (
    AnalysisRun,
    InstallationProfile,
    MetricValue,
    NormalBehaviorEvent,
    NormalBehaviorModel,
    NormalBehaviorObservation,
    SpecialPeriod,
)


def _utc(timestamp: int | None) -> datetime | None:
    return None if timestamp is None else datetime.fromtimestamp(timestamp / 1000, UTC)


def _model_out(row: NormalBehaviorModel) -> NormalBehaviorModelOut:
    return NormalBehaviorModelOut(
        metric_name=row.metric_name,
        version=row.version,
        status=StatusOut(row.status.value),
        is_current=row.is_current,
        created_at=datetime.fromtimestamp(row.created_at_ts / 1000, UTC),
        updated_at=datetime.fromtimestamp(row.updated_at_ts / 1000, UTC),
        effective_from=_utc(row.effective_from_ts),
        reason=row.reason,
        pause_reason=row.pause_reason,
        paused_at=_utc(row.paused_at_ts),
        observation_count=len(row.observations),
        events=[
            NormalBehaviorEventOut(
                kind=EventKindOut(event.kind.value),
                occurred_at=datetime.fromtimestamp(event.occurred_at_ts / 1000, UTC),
                reason=event.reason,
                effective_from=_utc(event.effective_from_ts),
            )
            for event in row.events
        ],
    )


def _record_event(
    session: Session,
    row: NormalBehaviorModel,
    kind: NormalBehaviorEventKind,
    now: int,
    *,
    reason: str | None = None,
    effective_from: int | None = None,
) -> None:
    session.add(
        NormalBehaviorEvent(
            model_id=row.id,
            kind=kind,
            occurred_at_ts=now,
            reason=reason,
            effective_from_ts=effective_from,
        )
    )


class NormalBehaviorBackend:
    """Database-backed version lifecycle. Reference values stay in ``metric_values``."""

    def __init__(self, session: Session, clock: Callable[[], int]) -> None:
        self.session = session
        self.clock = clock

    def list(self, limit: int, offset: int) -> NormalBehaviorModelList:
        total = int(self.session.scalar(select(func.count()).select_from(NormalBehaviorModel)) or 0)
        query = (
            select(NormalBehaviorModel)
            .order_by(NormalBehaviorModel.metric_name, NormalBehaviorModel.version.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = list(self.session.scalars(query).unique())
        return NormalBehaviorModelList(
            items=[_model_out(row) for row in rows], total=total, limit=limit, offset=offset
        )

    def _current(self, metric_name: MetricName) -> NormalBehaviorModel:
        row = self.session.scalar(
            select(NormalBehaviorModel).where(
                NormalBehaviorModel.metric_name == metric_name.value,
                NormalBehaviorModel.is_current.is_(True),
            )
        )
        if row is None:
            raise not_found("Normaalgedragmodel", metric_name.value)
        return row

    def pause(self, metric_name: MetricName, body: NormalBehaviorReason) -> NormalBehaviorModelOut:
        row = self._current(metric_name)
        if row.status is NormalBehaviorStatus.PAUSED:
            raise ProblemError(409, "Model is gepauzeerd", "Dit model is al gepauzeerd.")
        reason = body.reason.strip()
        if not reason:
            raise ProblemError(422, "Reden ontbreekt", "Vul een reden voor de pauze in.")
        now = self.clock()
        row.status_before_pause = row.status
        row.status = NormalBehaviorStatus.PAUSED
        row.pause_reason = reason
        row.paused_at_ts = now
        row.updated_at_ts = now
        self.session.flush()
        _record_event(self.session, row, NormalBehaviorEventKind.PAUSED, now, reason=reason)
        self.session.flush()
        return _model_out(row)

    def resume(self, metric_name: MetricName) -> NormalBehaviorModelOut:
        row = self._current(metric_name)
        if row.status is not NormalBehaviorStatus.PAUSED:
            raise ProblemError(409, "Model is niet gepauzeerd", "Dit model is niet gepauzeerd.")
        now = self.clock()
        row.status = row.status_before_pause or NormalBehaviorStatus.INSUFFICIENT_DATA
        row.status_before_pause = None
        row.pause_reason = None
        row.paused_at_ts = None
        row.updated_at_ts = now
        self.session.flush()
        _record_event(self.session, row, NormalBehaviorEventKind.RESUMED, now)
        self.session.flush()
        return _model_out(row)

    def start_version(
        self, metric_name: MetricName, body: NormalBehaviorNewVersion
    ) -> NormalBehaviorModelOut:
        current = self._current(metric_name)
        reason = body.reason.strip()
        if not reason:
            raise ProblemError(
                422, "Reden ontbreekt", "Vul een reden voor de nieuwe referentie in."
            )
        effective_from = int(body.effective_from.timestamp() * 1000)
        now = self.clock()
        current.is_current = False
        current.updated_at_ts = now
        row = NormalBehaviorModel(
            metric_name=metric_name.value,
            version=current.version + 1,
            status=NormalBehaviorStatus.LEARNING,
            is_current=True,
            created_at_ts=now,
            updated_at_ts=now,
            effective_from_ts=effective_from,
            reason=reason,
        )
        self.session.add(row)
        self.session.flush()
        _record_event(
            self.session,
            row,
            NormalBehaviorEventKind.REFERENCE_STARTED,
            now,
            reason=reason,
            effective_from=effective_from,
        )
        self.session.flush()
        return _model_out(row)


def capture_metric_references(session: Session, result: PipelineResult, run: AnalysisRun) -> None:
    """Attach final, valid, non-excluded metrics to the current model in the run transaction.

    A reference row stores only the key of an existing ``metric_values`` row and its
    versioning/coverage metadata. It never copies the metric value. Any overlap with a
    period marked ``exclude_from_baseline`` excludes the whole metric window, which is
    conservative until per-sample aggregates are available.
    """
    for metric in result.metrics:
        if not metric.final or metric.value is None:
            continue
        metric_name = MetricName(metric.name.value)
        window = metric.window.range
        mode = "" if metric.mode is None else metric.mode.value
        cycle_start_ts = -1 if metric.window.cycle_start is None else metric.window.cycle_start
        source = session.get(
            MetricValue,
            (
                metric_name,
                mode,
                metric.window.kind,
                window.start,
                cycle_start_ts,
            ),
        )
        if source is None or source.status is not MetricStatus.OK or not source.final:
            continue
        excluded = session.scalar(
            select(SpecialPeriod.id)
            .where(
                SpecialPeriod.exclude_from_baseline.is_(True),
                SpecialPeriod.start_ts < window.end,
                (SpecialPeriod.end_ts.is_(None)) | (SpecialPeriod.end_ts > window.start),
            )
            .limit(1)
        )
        if excluded is not None:
            continue
        model = session.scalar(
            select(NormalBehaviorModel).where(
                NormalBehaviorModel.metric_name == metric_name.value,
                NormalBehaviorModel.is_current.is_(True),
            )
        )
        now = run.finished_at_ts or run.started_at_ts or run.requested_at_ts
        if model is None:
            model = NormalBehaviorModel(
                metric_name=metric_name.value,
                version=1,
                status=NormalBehaviorStatus.INSUFFICIENT_DATA,
                is_current=True,
                created_at_ts=now,
                updated_at_ts=now,
            )
            session.add(model)
            session.flush()
            _record_event(session, model, NormalBehaviorEventKind.CREATED, now)
        if model.status is NormalBehaviorStatus.PAUSED:
            continue
        if model.status is NormalBehaviorStatus.INSUFFICIENT_DATA:
            model.status = NormalBehaviorStatus.LEARNING
            model.updated_at_ts = now
        profile_id = session.scalar(
            select(InstallationProfile.id)
            .where(
                InstallationProfile.valid_from_ts <= window.start,
                (InstallationProfile.valid_to_ts.is_(None))
                | (InstallationProfile.valid_to_ts > window.start),
            )
            .order_by(InstallationProfile.valid_from_ts.desc())
            .limit(1)
        )
        existing = session.scalar(
            select(NormalBehaviorObservation).where(
                NormalBehaviorObservation.model_id == model.id,
                NormalBehaviorObservation.metric_name == metric_name.value,
                NormalBehaviorObservation.mode == mode,
                NormalBehaviorObservation.window_kind == metric.window.kind.value,
                NormalBehaviorObservation.window_start_ts == window.start,
                NormalBehaviorObservation.cycle_start_ts == cycle_start_ts,
            )
        )
        context = {
            "operating_mode": mode or None,
            "metric_window_kind": metric.window.kind.value,
        }
        if existing is not None:
            existing.window_end_ts = window.end
            existing.unit = metric.unit
            existing.time_basis_seconds = metric.time_basis_seconds
            existing.coverage = metric.coverage
            existing.analysis_run_id = run.id
            existing.settings_revision_id = run.settings_revision_id
            existing.profile_version_id = profile_id
            existing.analysis_version = run.config_hash
            existing.context = context
            continue
        session.add(
            NormalBehaviorObservation(
                model_id=model.id,
                metric_name=metric_name.value,
                mode=mode,
                window_kind=metric.window.kind.value,
                window_start_ts=window.start,
                window_end_ts=window.end,
                cycle_start_ts=cycle_start_ts,
                unit=metric.unit,
                time_basis_seconds=metric.time_basis_seconds,
                coverage=metric.coverage,
                analysis_run_id=run.id,
                settings_revision_id=run.settings_revision_id,
                profile_version_id=profile_id,
                analysis_version=run.config_hash,
                context=context,
            )
        )
