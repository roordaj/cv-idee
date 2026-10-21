"""Lifecycle, excluded-period, and idempotent-reference tests."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cvidee.analysis.types import (
    AnalysisWindow,
    MetricWindow,
    PipelineResult,
    TimeRange,
)
from cvidee.analysis.types import (
    MetricValue as AnalysisMetric,
)
from cvidee.analysis.types import (
    MetricWindowKind as AnalysisMetricWindowKind,
)
from cvidee.api.problems import ProblemError
from cvidee.api.schemas.normal_behavior import NormalBehaviorNewVersion, NormalBehaviorReason
from cvidee.normal_behavior.backend import NormalBehaviorBackend, capture_metric_references
from cvidee.store.engine import create_db_engine, create_session_factory
from cvidee.store.enums import (
    MetricName,
    MetricStatus,
    NormalBehaviorStatus,
    RunStatus,
    RunTrigger,
    SpecialPeriodKind,
    ValueKind,
)
from cvidee.store.models import (
    AnalysisRun,
    MetricValue,
    NormalBehaviorEvent,
    NormalBehaviorModel,
    NormalBehaviorObservation,
    SpecialPeriod,
)
from cvidee.store.schema import upgrade_to_head

T0 = 1_791_100_800_000


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    db_url = f"sqlite:///{tmp_path / 'normal-behavior.sqlite3'}"
    upgrade_to_head(db_url)
    engine = create_db_engine(db_url)
    factory = create_session_factory(engine)
    with factory.begin() as session:
        yield session
    engine.dispose()


def _run(session: Session) -> AnalysisRun:
    run = AnalysisRun(
        trigger=RunTrigger.LIVE,
        status=RunStatus.SUCCEEDED,
        emit_from_ts=T0,
        requested_at_ts=T0 + 100,
        started_at_ts=T0 + 100,
        finished_at_ts=T0 + 200,
        config_hash="analysis-v1",
        stats={},
        errors=[],
        rule_versions={},
    )
    session.add(run)
    session.flush()
    return run


def _metric(session: Session, *, start: int = T0) -> AnalysisMetric:
    window = MetricWindow(AnalysisMetricWindowKind.HOUR, TimeRange(start, start + 3_600_000))
    metric = AnalysisMetric(
        name=MetricName.STARTS,
        window=window,
        value=7.0,
        unit="starts",
        time_basis_seconds=3600.0,
        coverage=1.0,
        final=True,
    )
    session.add(
        MetricValue(
            name=MetricName.STARTS,
            mode="",
            window_kind=window.kind,
            window_start_ts=start,
            cycle_start_ts=-1,
            window_end_ts=start + 3_600_000,
            status=MetricStatus.OK,
            value_num=metric.value,
            unit=metric.unit,
            time_basis_seconds=metric.time_basis_seconds,
            coverage=metric.coverage,
            provenance_kind=ValueKind.DERIVED,
            final=True,
        )
    )
    session.flush()
    return metric


def _result(metric: AnalysisMetric) -> PipelineResult:
    return PipelineResult(
        window=AnalysisWindow(T0, T0, T0 + 3_600_000),
        next_watermark=T0 + 3_600_000,
        timelines=(),
        quality_events=(),
        mode_segments=(),
        cycles=(),
        metrics=(metric,),
    )


def test_capture_is_idempotent_and_does_not_copy_metric_value(session: Session) -> None:
    metric = _metric(session)
    run = _run(session)
    result = _result(metric)

    capture_metric_references(session, result, run)
    capture_metric_references(session, result, run)
    run.config_hash = "analysis-v2"
    capture_metric_references(session, result, run)

    model = session.scalar(select(NormalBehaviorModel))
    assert model is not None
    assert model.status is NormalBehaviorStatus.LEARNING
    assert session.scalar(select(func.count()).select_from(NormalBehaviorObservation)) == 1
    observation = session.scalar(select(NormalBehaviorObservation))
    assert observation is not None
    assert observation.metric_name == MetricName.STARTS.value
    assert observation.analysis_run_id == run.id
    assert observation.analysis_version == "analysis-v2"
    assert observation.context == {
        "operating_mode": None,
        "metric_window_kind": "hour",
    }
    assert not hasattr(observation, "value_num")


def test_excluded_special_period_never_becomes_an_observation(session: Session) -> None:
    metric = _metric(session)
    session.add(
        SpecialPeriod(
            kind=SpecialPeriodKind.COMMISSIONING,
            start_ts=T0 + 60_000,
            end_ts=T0 + 120_000,
            description="Opstookprotocol",
            room_overrides=[],
            exclude_from_baseline=True,
            exclude_from_comparisons=True,
            exclude_from_ch_conclusions=True,
            created_at_ts=T0,
            updated_at_ts=T0,
        )
    )
    run = _run(session)

    capture_metric_references(session, _result(metric), run)

    assert session.scalar(select(func.count()).select_from(NormalBehaviorObservation)) == 0
    assert session.scalar(select(func.count()).select_from(NormalBehaviorModel)) == 0


def test_pause_resume_and_new_version_preserve_history(session: Session) -> None:
    metric = _metric(session)
    run = _run(session)
    capture_metric_references(session, _result(metric), run)
    backend = NormalBehaviorBackend(session, lambda: T0 + 10_000)

    paused = backend.pause(MetricName.STARTS, NormalBehaviorReason(reason="Onderhoud"))
    assert paused.status.value == "paused"
    with pytest.raises(ProblemError) as error:
        backend.pause(MetricName.STARTS, NormalBehaviorReason(reason="Nogmaals"))
    assert error.value.problem.status == 409

    second_metric = _metric(session, start=T0 + 3_600_000)
    capture_metric_references(session, _result(second_metric), _run(session))
    assert session.scalar(select(func.count()).select_from(NormalBehaviorObservation)) == 1

    resumed = backend.resume(MetricName.STARTS)
    assert resumed.status.value == "learning"
    version = backend.start_version(
        MetricName.STARTS,
        NormalBehaviorNewVersion(
            effective_from=datetime(2026, 10, 5, tzinfo=UTC), reason="Nieuwe regeling"
        ),
    )
    assert version.version == 2
    assert version.status.value == "learning"
    assert version.observation_count == 0
    old = session.scalar(select(NormalBehaviorModel).where(NormalBehaviorModel.version == 1))
    assert old is not None
    assert not old.is_current
    assert len(old.observations) == 1
    assert session.scalar(select(func.count()).select_from(NormalBehaviorEvent)) == 4


def test_pause_requires_a_nonblank_reason(session: Session) -> None:
    metric = _metric(session)
    run = _run(session)
    capture_metric_references(session, _result(metric), run)
    backend = NormalBehaviorBackend(session, lambda: T0)

    with pytest.raises(ProblemError) as error:
        backend.pause(MetricName.STARTS, NormalBehaviorReason(reason="  "))

    assert error.value.problem.status == 422
