"""Runner stage 6: evaluate the rule registry and hand the candidates to the engine (#34).

Runs inside the run's transaction after the derived rows were replaced. The rule context is
built from stored derived data (so rules can look further back than the pipeline window) and a
store-backed :class:`~cvidee.rules.base.TimelineSource`. An empty registry (the default until
the MVP rules land) makes the stage a no-op.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from cvidee.analysis.timeline import build_timelines
from cvidee.analysis.types import (
    AnalysisWindow,
    MetricWindowKind,
    PipelineConfig,
    PipelineResult,
    SignalRef,
    SignalTimeline,
    TimeRange,
)
from cvidee.api.findings_read import FindingsReadModel
from cvidee.api.schemas.settings import AnalysisSettings
from cvidee.findings.bundling import bundle_signature
from cvidee.findings.engine import EngineResult, FindingsEngine, RecoverySettings
from cvidee.findings.history import profile_settings
from cvidee.findings.repository import SqlFindingRepository
from cvidee.installation import SqlInstallationProfileRepository, profile_facts
from cvidee.periods import rule_periods
from cvidee.rules.availability import AvailabilityPolicy, assess_analyses
from cvidee.rules.base import RuleContext
from cvidee.rules.registry import RuleRegistry
from cvidee.runner.sources import MappedSignal, SourceSettings, load_window_input
from cvidee.settings.repository import rule_params
from cvidee.signals.quality import signal_statuses
from cvidee.store.derived import SqlDerivedDataRepository
from cvidee.store.enums import RecommendationStatus, SnapshotTrigger
from cvidee.store.models import AnalysisRun, Finding, RecommendationSnapshot

__all__ = ["FindingsStage", "StoreTimelines"]


class StoreTimelines:
    """Timelines read from stored observations on demand (cached per range)."""

    def __init__(
        self,
        session: Session,
        mapped: Sequence[MappedSignal],
        sources: SourceSettings,
        config: PipelineConfig,
        horizon: int,
    ) -> None:
        self._session = session
        self._mapped = mapped
        self._sources = sources
        self._config = config
        self._horizon = horizon
        self._cache: dict[TimeRange, dict[SignalRef, SignalTimeline]] = {}

    def build(self, rng: TimeRange) -> dict[SignalRef, SignalTimeline]:
        end = min(rng.end, self._horizon)
        if end <= rng.start:
            return {}
        key = TimeRange(rng.start, end)
        if key not in self._cache:
            window = AnalysisWindow(context_start=key.start, emit_from=key.start, end=end)
            observations, events = load_window_input(
                self._session, self._mapped, self._sources, window
            )
            built = build_timelines(observations, events, self._config, window)
            self._cache[key] = {t.signal: t for t in built}
        return self._cache[key]

    def timeline(self, signal: SignalRef, rng: TimeRange) -> SignalTimeline | None:
        for key, cached in self._cache.items():  # a cached wider range serves sub-ranges
            if key.start <= rng.start and rng.end <= key.end and signal in cached:
                return cached[signal]
        return self.build(rng).get(signal)


class FindingsStage:
    def __init__(
        self,
        registry: RuleRegistry,
        recovery: RecoverySettings | None = None,
        sources: SourceSettings | None = None,
    ) -> None:
        self.registry = registry
        self.recovery = recovery if recovery is not None else RecoverySettings()
        self._sources = sources if sources is not None else SourceSettings()

    def __call__(
        self,
        session: Session,
        result: PipelineResult,
        run_id: int,
        mapped: Sequence[MappedSignal],
        config: PipelineConfig,
        settings_values: AnalysisSettings | None = None,
    ) -> EngineResult:
        if len(self.registry) == 0:
            return EngineResult()
        now = result.window.end
        params = {
            rule.id: self.registry.default_params(rule.id)
            if settings_values is None
            else rule_params(self.registry, rule.id, settings_values)
            for rule in self.registry
        }
        history = max(rule.history_ms(params[rule.id]) for rule in self.registry)
        period = TimeRange(now - max(history, 1), now)
        timelines = StoreTimelines(session, mapped, self._sources, config, now)
        built = timelines.build(period)
        statuses = signal_statuses(session, mapped, built, period)
        profiles = SqlInstallationProfileRepository(session)
        profile = profile_facts(profiles.at(now) or profiles.current_or_default(now))
        derived = SqlDerivedDataRepository(session)
        metrics = tuple(
            m for kind in MetricWindowKind for m in derived.metric_values(kind, period.start, now)
        )
        ctx = RuleContext(
            now=now,
            period=period,
            profile=profile,
            signals=statuses,
            gateway_signals=tuple(sorted(s.signal for s in config.signals if s.via_can_gateway)),
            availability=assess_analyses(
                statuses,
                profile,
                None
                if settings_values is None
                else AvailabilityPolicy(
                    settings_values.min_assessment_coverage_pct / 100,
                    settings_values.flame_resolution_s * 1000,
                ),
            ),
            cycles=tuple(derived.burner_cycles(period.start, now)),
            mode_segments=tuple(derived.mode_segments(period.start, now)),
            metrics=metrics,
            quality_events=tuple(derived.quality_events(period.start, now)),
            special_periods=rule_periods(session, period),
            timelines=timelines,
            config_hash=config.config_hash,
        )
        recovery = (
            self.recovery
            if settings_values is None
            else RecoverySettings(
                days_without_pattern=settings_values.recovery_days,
                min_coverage=settings_values.recovery_min_coverage_pct / 100,
                require_comparable_weather=settings_values.recovery_comparable_weather_only,
                max_outdoor_delta_k=settings_values.comparable_weather_c,
            )
        )
        engine = FindingsEngine(
            self.registry, SqlFindingRepository(session), recovery, params_for=params.__getitem__
        )
        outcome = engine.evaluate(ctx, run_id)
        session.flush()
        run = session.get(AnalysisRun, run_id)
        for human_id in (*outcome.created, *outcome.updated):
            finding = session.scalar(select(Finding).where(Finding.human_id == human_id))
            if finding is None or not finding.recommendations:
                continue
            recommendation = finding.recommendations[-1]
            if recommendation.status is not RecommendationStatus.OPEN:
                continue
            previous = session.scalar(
                select(RecommendationSnapshot)
                .where(RecommendationSnapshot.recommendation_id == recommendation.id)
                .order_by(RecommendationSnapshot.id.desc())
                .limit(1)
            )
            rendered = (
                FindingsReadModel(session, lambda: now).finding(human_id).model_dump(mode="json")
            )

            if (
                previous is not None
                and previous.config_hash == config.config_hash
                and previous.rule_version == finding.rule_version
                and previous.status == recommendation.status
                and previous.rule_params == finding.rule_params
                and previous.profile_id == int(profile.version)
                and bundle_signature(previous.content) == bundle_signature(rendered)
            ):
                continue
            session.add(
                RecommendationSnapshot(
                    recommendation_id=recommendation.id,
                    finding_id=finding.id,
                    taken_at_ts=now,
                    trigger=SnapshotTrigger.CREATED
                    if previous is None
                    else SnapshotTrigger.CONTENT_UPDATED,
                    status=recommendation.status,
                    outcome=recommendation.outcome,
                    measurement_start_ts=finding.period_start_ts,
                    measurement_end_ts=finding.period_end_ts,
                    rule_id=finding.rule_id,
                    rule_version=finding.rule_version,
                    rule_params=dict(finding.rule_params),
                    profile_id=int(profile.version),
                    settings_revision_id=None if run is None else run.settings_revision_id,
                    config_hash=config.config_hash,
                    settings={
                        **(
                            {}
                            if settings_values is None
                            else settings_values.model_dump(mode="json")
                        ),
                        "installation_profile": profile_settings(session, int(profile.version)),
                    },
                    content=rendered,
                    note=max(recommendation.notes, key=lambda n: (n.created_at_ts, n.id)).text
                    if recommendation.notes
                    else None,
                )
            )
        return outcome


def _known_ms(timeline: SignalTimeline, period: TimeRange) -> int:
    known = 0
    for interval in timeline.values:
        known += max(min(interval.end, period.end) - max(interval.start, period.start), 0)
    return known
