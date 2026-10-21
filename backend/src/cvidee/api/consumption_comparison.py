"""Conservative comparison of two previously observed raw gas-meter periods."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cvidee.analysis.change_evaluation import (
    ComparisonPolicy,
    evaluate_change,
    period_metrics,
)
from cvidee.analysis.quality import apply_quality
from cvidee.analysis.types import (
    AnalysisWindow,
    BurnerCycle,
    ModeSegment,
    Role,
    SignalRef,
    SignalTimeline,
)
from cvidee.analysis.types import TimeRange as AnalysisRange
from cvidee.api.consumption_read import ConsumptionReadModel
from cvidee.api.problems import ProblemError
from cvidee.api.schemas.common import TimeRange
from cvidee.api.schemas.consumption import (
    ConsumptionAvailability,
    ConsumptionCandidatesResponse,
    ConsumptionComparisonReason,
    ConsumptionComparisonRequest,
    ConsumptionComparisonResponse,
    ConsumptionComparisonStatus,
    ConsumptionPeriodCandidate,
    ConsumptionPeriodContext,
)
from cvidee.changes.evaluation import policy_from
from cvidee.findings.stage import StoreTimelines
from cvidee.runner.sources import (
    SourceSettings,
    build_pipeline_config,
    load_mapped_signals,
)
from cvidee.settings.repository import current_revision, effective_values, pipeline_settings
from cvidee.store.derived import SqlDerivedDataRepository
from cvidee.store.enums import Mode
from cvidee.store.models import SpecialPeriod

_DAY_MS = 86_400_000
_MAX_WINDOW = timedelta(days=31)
_MAX_HISTORY_MS = 366 * _DAY_MS
_MAX_PAGE = 100


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ProblemError(422, "Ongeldig tijdvak", "Begin en einde moeten tijdzones bevatten.")
    return value.astimezone(UTC)


def _ms(value: datetime) -> int:
    return round(value.timestamp() * 1000)


def _time_range(start: int, end: int) -> TimeRange:
    return TimeRange(
        start=datetime.fromtimestamp(start / 1000, UTC), end=datetime.fromtimestamp(end / 1000, UTC)
    )


def _overlap(start: int, end: int, period: SpecialPeriod) -> bool:
    return period.start_ts < end and (period.end_ts is None or period.end_ts > start)


class ConsumptionComparisonReadModel:
    """Build eligible observed periods and compare a user-selected pair."""

    def __init__(self, sessions: sessionmaker[Session], clock: Callable[[], int]) -> None:
        self._sessions = sessions
        self._clock = clock

    def candidates(
        self, start: datetime, end: datetime, limit: int = 30, offset: int = 0
    ) -> ConsumptionCandidatesResponse:
        observation = self._validate_range(start, end)
        duration = observation.end - observation.start
        if not 1 <= limit <= _MAX_PAGE or offset < 0:
            raise ProblemError(
                422, "Ongeldige paginering", "Kies maximaal 100 perioden en een offset vanaf nul."
            )
        count = min(366 // max(1, duration // _DAY_MS), 366)
        count = max(1, count)
        end_ts = observation.start - offset * duration
        start_ts = max(
            observation.start - _MAX_HISTORY_MS,
            end_ts - min(limit, count) * duration,
        )
        windows: list[AnalysisRange] = []
        cursor = end_ts
        while cursor - duration >= start_ts:
            windows.append(AnalysisRange(cursor - duration, cursor))
            cursor -= duration
        windows.reverse()
        requested = [AnalysisRange(observation.start, observation.end), *windows]
        with self._sessions() as session:
            policy, timelines, cycles, modes, periods = self._context(session, requested)
            observed = self._candidate(
                session, requested[0], policy, timelines, cycles, modes, periods
            )
            candidates = [
                self._pair(session, window, requested[0], policy, timelines, cycles, modes, periods)
                for window in windows
            ]
        eligible = [
            item
            for item in candidates
            if item.status is not ConsumptionComparisonStatus.UNAVAILABLE
        ]
        reasons = (
            []
            if eligible
            else sorted(
                {reason for candidate in candidates for reason in candidate.reasons},
                key=lambda item: item.value,
            )
        )
        status = (
            ConsumptionComparisonStatus.UNAVAILABLE
            if not eligible
            else ConsumptionComparisonStatus.LIMITED
            if any(item.status is ConsumptionComparisonStatus.LIMITED for item in eligible)
            else ConsumptionComparisonStatus.AVAILABLE
        )
        return ConsumptionCandidatesResponse(
            observation=_time_range(observation.start, observation.end),
            observation_data=observed,
            status=status,
            reasons=reasons
            or ([] if candidates else [ConsumptionComparisonReason.NO_VALID_PERIOD]),
            candidates=candidates,
            consumption_availability=observed.consumption_availability,
            efficiency_availability=ConsumptionAvailability.UNAVAILABLE,
            cost_availability=ConsumptionAvailability.AVAILABLE
            if observed.cost_availability is ConsumptionAvailability.AVAILABLE
            else ConsumptionAvailability.UNAVAILABLE,
        )

    def compare(self, request: ConsumptionComparisonRequest) -> ConsumptionComparisonResponse:
        observation = self._validate_range(request.observation.start, request.observation.end)
        reference = self._validate_range(request.reference.start, request.reference.end)
        with self._sessions() as session:
            policy, timelines, cycles, modes, periods = self._context(
                session, [reference, observation]
            )
            observed = self._candidate(
                session, observation, policy, timelines, cycles, modes, periods
            )
            ref, reasons, status = self._pair_result(
                session, reference, observation, policy, timelines, cycles, modes, periods
            )
            observed = observed.model_copy(update={"status": status, "reasons": reasons})
        return ConsumptionComparisonResponse(
            reference=ref,
            observation=observed,
            status=status,
            reasons=reasons,
            difference_m3=(
                None
                if status is ConsumptionComparisonStatus.UNAVAILABLE
                or ref.consumption_m3 is None
                or observed.consumption_m3 is None
                else round(observed.consumption_m3 - ref.consumption_m3, 3)
            ),
            basis=(
                "Ruwe meterstanden; verschil is geen weerscorrectie, "
                "ruimteverwarmingsverbruik of besparing."
            ),
            consumption_availability=observed.consumption_availability,
            efficiency_availability=ConsumptionAvailability.UNAVAILABLE,
            cost_availability=ConsumptionAvailability.AVAILABLE
            if ref.cost_availability is ConsumptionAvailability.AVAILABLE
            and observed.cost_availability is ConsumptionAvailability.AVAILABLE
            else ConsumptionAvailability.UNAVAILABLE,
        )

    def _validate_range(self, start: datetime, end: datetime) -> AnalysisRange:
        start, end = _utc(start), _utc(end)
        if start >= end or end - start > _MAX_WINDOW or _ms(end) > self._clock():
            raise ProblemError(
                422, "Ongeldig tijdvak", "Kies maximaal 31 dagen met begin vóór einde."
            )
        return AnalysisRange(_ms(start), _ms(end))

    def _context(
        self, session: Session, windows: Sequence[AnalysisRange]
    ) -> tuple[
        ComparisonPolicy,
        dict[SignalRef, SignalTimeline],
        tuple[BurnerCycle, ...],
        tuple[ModeSegment, ...],
        list[SpecialPeriod],
    ]:
        lo, hi = min(window.start for window in windows), max(window.end for window in windows)
        if hi - lo > _MAX_HISTORY_MS:
            raise ProblemError(
                422, "Ongeldig tijdvak", "Kies perioden binnen maximaal 366 dagen historie."
            )
        revision = current_revision(session)
        values = effective_values(revision)
        policy = policy_from(values)
        mapped = load_mapped_signals(session)
        sources = SourceSettings()
        config = build_pipeline_config(
            session, mapped, sources, base=pipeline_settings(None, values)
        )
        store = StoreTimelines(session, mapped, sources, config, hi)
        built = store.build(AnalysisRange(lo, hi))
        quality = apply_quality(tuple(built.values()), config, AnalysisWindow(lo, lo, hi))
        timelines = {timeline.signal: timeline for timeline in quality.timelines}
        repo = SqlDerivedDataRepository(session)
        cycles = tuple(repo.burner_cycles(lo, hi))
        modes = tuple(repo.mode_segments(lo, hi))
        periods = list(
            session.scalars(
                select(SpecialPeriod).where(
                    SpecialPeriod.start_ts < hi,
                    SpecialPeriod.end_ts.is_(None) | (SpecialPeriod.end_ts > lo),
                )
            )
        )
        return policy, timelines, cycles, modes, periods

    def _candidate(
        self,
        session: Session,
        window: AnalysisRange,
        policy: ComparisonPolicy,
        timelines: dict[SignalRef, SignalTimeline],
        cycles: tuple[BurnerCycle, ...],
        modes: tuple[ModeSegment, ...],
        periods: list[SpecialPeriod],
    ) -> ConsumptionPeriodCandidate:
        start, end = (
            datetime.fromtimestamp(window.start / 1000, UTC),
            datetime.fromtimestamp(window.end / 1000, UTC),
        )
        raw = ConsumptionReadModel(self._sessions, self._clock)._read(
            session, start, end, window.start, window.end
        )
        exclusions = tuple(
            AnalysisRange(max(window.start, p.start_ts), min(window.end, p.end_ts or window.end))
            for p in periods
            if p.exclude_from_comparisons and _overlap(window.start, window.end, p)
        )
        metrics = period_metrics(
            window, tuple(timelines.values()), cycles, modes, exclusions, policy
        )
        zone_refs = [ref for ref in timelines if ref.role in (Role.ZONE_DEMAND, Role.VALVE_STATE)]
        zone_use = (
            "available" if any(timelines[ref].known_ms(window) for ref in zone_refs) else "unknown"
        )
        dhw_ms = sum(
            max(0, min(window.end, item.end) - max(window.start, item.start))
            for item in modes
            if item.mode is Mode.DHW
        )
        demand = timelines.get(SignalRef(Role.HEAT_DEMAND))
        demand_ms = sum(
            max(0, min(window.end, item.end) - max(window.start, item.start))
            for item in (() if demand is None else demand.values)
            if item.value is True
        )
        flame = timelines.get(SignalRef(Role.FLAME))
        flame_ms = sum(
            max(
                0,
                min(window.end, item.end, mode.end) - max(window.start, item.start, mode.start),
            )
            for item in (() if flame is None else flame.values)
            if item.value is True
            for mode in modes
            if mode.mode is Mode.CH
        )
        reasons: set[ConsumptionComparisonReason] = set()
        raw_reason_map = {
            "no_meter": ConsumptionComparisonReason.NO_METER,
            "no_valid_intervals": ConsumptionComparisonReason.NO_VALID_PERIOD,
            "unknown_meter_scope": ConsumptionComparisonReason.UNKNOWN_METER_SCOPE,
            "mapping_changed": ConsumptionComparisonReason.MAPPING_CHANGED,
            "profile_scope_changed": ConsumptionComparisonReason.SCOPE_CHANGED,
            "unsupported_unit": ConsumptionComparisonReason.UNIT_MISMATCH,
            "data_gap": ConsumptionComparisonReason.DATA_GAP,
            "counter_reset": ConsumptionComparisonReason.COUNTER_RESET,
        }
        reasons.update(raw_reason_map[reason.value] for reason in raw.reasons)
        mapping = raw.segments[0].mapping_revision if raw.segments else None
        return ConsumptionPeriodCandidate(
            range=_time_range(window.start, window.end),
            status=ConsumptionComparisonStatus.AVAILABLE,
            reasons=sorted(reasons, key=lambda item: item.value),
            counter_start=raw.counter_start,
            counter_end=raw.counter_end,
            consumption_m3=raw.consumption_m3,
            meter_scope=raw.meter_scope,
            meter_entity_id=raw.meter_entity_id,
            unit=raw.unit,
            mapping_revision=mapping,
            coverage_pct=raw.coverage_pct,
            consumption_availability=raw.availability,
            context=ConsumptionPeriodContext(
                outdoor_temperature_c=metrics.outdoor_c,
                outdoor_coverage_pct=round(metrics.outdoor_coverage * 100, 2),
                room_setpoints_c=dict(metrics.setpoints),
                heating_runtime_hours=round(flame_ms / 3_600_000, 2),
                heat_demand_hours=round(demand_ms / 3_600_000, 2)
                if demand is not None and demand.known_ms(window)
                else None,
                dhw_runtime_hours=round(dhw_ms / 3_600_000, 2),
                zone_use=zone_use,
                special_periods=[
                    p.description or p.kind.value
                    for p in periods
                    if _overlap(window.start, window.end, p)
                ],
            ),
            cost_availability=ConsumptionAvailability.AVAILABLE
            if raw.cost_eur is not None
            else ConsumptionAvailability.UNAVAILABLE,
        )

    def _pair(
        self,
        session: Session,
        reference: AnalysisRange,
        observation: AnalysisRange,
        policy: ComparisonPolicy,
        timelines: dict[SignalRef, SignalTimeline],
        cycles: tuple[BurnerCycle, ...],
        modes: tuple[ModeSegment, ...],
        periods: list[SpecialPeriod],
    ) -> ConsumptionPeriodCandidate:
        candidate, reasons, status = self._pair_result(
            session, reference, observation, policy, timelines, cycles, modes, periods
        )
        return candidate.model_copy(update={"status": status, "reasons": reasons})

    def _pair_result(
        self,
        session: Session,
        reference: AnalysisRange,
        observation: AnalysisRange,
        policy: ComparisonPolicy,
        timelines: dict[SignalRef, SignalTimeline],
        cycles: tuple[BurnerCycle, ...],
        modes: tuple[ModeSegment, ...],
        periods: list[SpecialPeriod],
    ) -> tuple[
        ConsumptionPeriodCandidate, list[ConsumptionComparisonReason], ConsumptionComparisonStatus
    ]:
        ref = self._candidate(session, reference, policy, timelines, cycles, modes, periods)
        obs = self._candidate(session, observation, policy, timelines, cycles, modes, periods)
        reasons: set[ConsumptionComparisonReason] = set(ref.reasons) | set(obs.reasons)
        if reference.end > observation.start:
            reasons.add(ConsumptionComparisonReason.DURATION_MISMATCH)
        if reference.end - reference.start != observation.end - observation.start:
            reasons.add(ConsumptionComparisonReason.DURATION_MISMATCH)
        if ref.meter_scope.value == "unknown" or obs.meter_scope.value == "unknown":
            reasons.add(ConsumptionComparisonReason.UNKNOWN_METER_SCOPE)
        if ref.meter_entity_id != obs.meter_entity_id:
            reasons.add(ConsumptionComparisonReason.METER_MISMATCH)
        if ref.unit != obs.unit:
            reasons.add(ConsumptionComparisonReason.UNIT_MISMATCH)
        if ref.mapping_revision != obs.mapping_revision:
            reasons.add(ConsumptionComparisonReason.MAPPING_CHANGED)
        if ref.meter_scope != obs.meter_scope:
            reasons.add(ConsumptionComparisonReason.SCOPE_CHANGED)
        if (
            ref.coverage_pct is None
            or obs.coverage_pct is None
            or min(ref.coverage_pct, obs.coverage_pct) < policy.min_coverage * 100
        ):
            reasons.add(ConsumptionComparisonReason.LOW_COVERAGE)
        for window in (reference, observation):
            raw = ConsumptionReadModel(self._sessions, self._clock)._read(
                session,
                datetime.fromtimestamp(window.start / 1000, UTC),
                datetime.fromtimestamp(window.end / 1000, UTC),
                window.start,
                window.end,
            )
            if any(event.kind.value == "counter_reset" for event in raw.events):
                reasons.add(ConsumptionComparisonReason.COUNTER_RESET)
            if any(event.kind.value in ("data_gap", "mapping_changed") for event in raw.events):
                reasons.add(
                    ConsumptionComparisonReason.DATA_GAP
                    if any(event.kind.value == "data_gap" for event in raw.events)
                    else ConsumptionComparisonReason.MAPPING_CHANGED
                )
        excluded = [
            p
            for p in periods
            if p.exclude_from_comparisons
            and (
                _overlap(reference.start, reference.end, p)
                or _overlap(observation.start, observation.end, p)
            )
        ]
        if excluded:
            reasons.add(ConsumptionComparisonReason.EXCLUDED_PERIOD)
        ref_metrics = period_metrics(
            reference, tuple(timelines.values()), cycles, modes, (), policy
        )
        obs_metrics = period_metrics(
            observation, tuple(timelines.values()), cycles, modes, (), policy
        )
        fact = evaluate_change(
            "gas-periods", reference, observation, ref_metrics, obs_metrics, self._clock(), policy
        )
        if fact.weather == "no":
            reasons.add(ConsumptionComparisonReason.WEATHER_OUT_OF_RANGE)
        elif fact.weather == "limited":
            reasons.add(ConsumptionComparisonReason.WEATHER_LIMITED)
        if fact.setpoints == "no":
            reasons.add(ConsumptionComparisonReason.SETPOINT_MISMATCH)
        if fact.setpoints == "limited":
            reasons.add(ConsumptionComparisonReason.SETPOINT_UNKNOWN)
        if ref.meter_entity_id is None or obs.meter_entity_id is None:
            reasons.add(ConsumptionComparisonReason.NO_METER)
        # A gas counter does not reveal cooking, hot-water draws or occupancy even
        # when its scope is confirmed; those remain unknown without separate measures.
        if ref.meter_entity_id is not None and obs.meter_entity_id is not None:
            reasons.add(ConsumptionComparisonReason.USE_CONTEXT_UNKNOWN)
        blocking = {
            ConsumptionComparisonReason.DURATION_MISMATCH,
            ConsumptionComparisonReason.NO_METER,
            ConsumptionComparisonReason.UNKNOWN_METER_SCOPE,
            ConsumptionComparisonReason.METER_MISMATCH,
            ConsumptionComparisonReason.MAPPING_CHANGED,
            ConsumptionComparisonReason.SCOPE_CHANGED,
            ConsumptionComparisonReason.UNIT_MISMATCH,
            ConsumptionComparisonReason.LOW_COVERAGE,
            ConsumptionComparisonReason.COUNTER_RESET,
            ConsumptionComparisonReason.DATA_GAP,
            ConsumptionComparisonReason.EXCLUDED_PERIOD,
            ConsumptionComparisonReason.WEATHER_OUT_OF_RANGE,
            ConsumptionComparisonReason.SETPOINT_MISMATCH,
        }
        status = (
            ConsumptionComparisonStatus.UNAVAILABLE
            if reasons & blocking or ref.consumption_m3 is None or obs.consumption_m3 is None
            else ConsumptionComparisonStatus.LIMITED
            if reasons
            else ConsumptionComparisonStatus.AVAILABLE
        )
        return ref, sorted(reasons, key=lambda item: item.value), status
