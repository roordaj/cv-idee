"""Stored change evaluation: pure metrics in, explicit comparisons and history out."""

import hashlib
import math
from dataclasses import asdict, replace
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from cvidee.analysis.change_evaluation import (
    DAY_MS,
    EVALUATION_VERSION,
    ComparisonPolicy,
    EvaluationFact,
    evaluate_change,
    period_metrics,
)
from cvidee.analysis.quality import apply_quality
from cvidee.analysis.room_comfort import RoomComfortPeriod
from cvidee.analysis.types import AnalysisWindow, PipelineConfig, TimeRange
from cvidee.api.schemas.changes import (
    ChangeEvaluation as EvaluationOut,
)
from cvidee.api.schemas.changes import (
    Comparability,
    ConditionRow,
    MetricAssessment,
    MetricComparison,
)
from cvidee.api.schemas.common import TimeRange as RangeOut
from cvidee.api.schemas.data import RoomComfortOverride
from cvidee.api.schemas.installation import RoomComfort
from cvidee.api.schemas.settings import AnalysisSettings
from cvidee.changes.log import VERDICTS
from cvidee.findings.history import snapshot_transition
from cvidee.rules.registry import canonical_json
from cvidee.runner.sources import SourceSettings, build_pipeline_config, load_mapped_signals
from cvidee.settings.repository import current_revision, effective_values, pipeline_settings
from cvidee.store.derived import SqlDerivedDataRepository
from cvidee.store.enums import (
    EvaluationVerdict,
    ExperimentStatus,
    RecommendationOutcome,
    RecommendationStatus,
    SnapshotTrigger,
)
from cvidee.store.models import Change, ChangeEvaluation, Experiment, Recommendation, SpecialPeriod
from cvidee.store.models import InstallationProfile as ProfileRow

RULE_VERSION = EVALUATION_VERSION


def policy_from(values: AnalysisSettings) -> ComparisonPolicy:
    return ComparisonPolicy(
        days=values.comparison_days,
        min_coverage=values.min_period_coverage_pct / 100,
        weather_delta_c=values.comparable_weather_c,
        limited_weather_delta_c=values.limited_weather_c,
        comfort_deficit_c=values.comfort_margin_c,
        comfort_limit_h_week=values.allowed_comfort_loss_h_per_week,
        short_cycle_s=values.short_cycle_min * 60,
        min_observation_hours=values.min_observation_hours,
    )


def number(value: float | None, unit: str = "", *, scale: float = 1) -> str:
    return (
        "Onbekend"
        if value is None
        else f"{value * scale:.1f}".replace(".", ",") + (f" {unit}" if unit else "")
    )


def _dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts / 1000, UTC)


def render_evaluation(fact: EvaluationFact) -> EvaluationOut:
    before, after = fact.before, fact.after
    conditions = [
        ConditionRow(
            label="Buitentemperatuur",
            before=number(before.outdoor_c, "°C"),
            after=number(after.outdoor_c, "°C"),
            comparable=Comparability(fact.weather),
        ),
        ConditionRow(
            label="Kamerinstellingen",
            before=" · ".join(f"{r}: {number(v, '°C')}" for r, v in before.setpoints) or "Onbekend",
            after=" · ".join(f"{r}: {number(v, '°C')}" for r, v in after.setpoints) or "Onbekend",
            comparable=Comparability(fact.setpoints),
        ),
        ConditionRow(
            label="Andere wijzigingen",
            before=" · ".join(fact.overlap_ids) or "Geen",
            after=" · ".join(fact.overlap_ids) or "Geen",
            comparable=Comparability.NO if fact.overlap_ids else Comparability.YES,
        ),
        ConditionRow(
            label="Bijzondere perioden",
            before=number(before.excluded_ms / 3_600_000, "u uitgesloten"),
            after=number(after.excluded_ms / 3_600_000, "u uitgesloten"),
            comparable=Comparability.EXCLUDED
            if before.excluded_ms or after.excluded_ms
            else Comparability.YES,
        ),
        ConditionRow(
            label="Resolutie vlamstatus",
            before=number(
                None if before.flame_resolution_ms is None else before.flame_resolution_ms / 1000,
                "s",
            ),
            after=number(
                None if after.flame_resolution_ms is None else after.flame_resolution_ms / 1000, "s"
            ),
            comparable=Comparability.YES
            if all(
                value is not None and value <= fact.policy.short_cycle_s * 250
                for value in (before.flame_resolution_ms, after.flame_resolution_ms)
            )
            else Comparability.LIMITED,
        ),
        ConditionRow(
            label="Gegevensdekking",
            before=number(before.coverage, "%", scale=100),
            after=number(after.coverage, "%", scale=100),
            comparable=Comparability.YES
            if min(before.coverage, after.coverage) >= fact.policy.min_coverage
            else Comparability.LIMITED,
        ),
        ConditionRow(
            label="Comfortdoelen per profielversie",
            before="Meerdere profielversies"
            if before.comfort_profile_mixed
            else "Eén profielversie",
            after="Meerdere profielversies" if after.comfort_profile_mixed else "Eén profielversie",
            comparable=Comparability.LIMITED
            if before.comfort_profile_mixed or after.comfort_profile_mixed
            else Comparability.YES,
        ),
    ]
    old_coverage, new_coverage = dict(before.room_coverage), dict(after.room_coverage)
    conditions.extend(
        ConditionRow(
            label=f"Comfortgegevens {room}",
            before=number(old_coverage.get(room, 0), "%", scale=100),
            after=number(new_coverage.get(room, 0), "%", scale=100),
            comparable=Comparability.YES
            if min(old_coverage.get(room, 0), new_coverage.get(room, 0)) >= fact.policy.min_coverage
            else Comparability.LIMITED,
        )
        for room in sorted(old_coverage.keys() | new_coverage.keys())
    )

    metrics = []
    specs = [
        (
            "CV-starts per uur",
            "Per waargenomen uur met warmtevraag.",
            before.starts_per_hour,
            after.starts_per_hour,
            "/u",
            False,
            1,
        ),
        (
            "Mediaan brandduur",
            "Alleen volledige CV-cycli.",
            before.median_burn_s,
            after.median_burn_s,
            "s",
            True,
            1,
        ),
        (
            "Aandeel korte cycli",
            "Korte stops tijdens aanhoudende vraag.",
            before.short_share,
            after.short_share,
            "%",
            False,
            100,
        ),
        (
            "Gemiddelde aanvoer",
            "Alleen stabiel CV-bedrijf; lager is niet vanzelf beter.",
            before.flow_stable_c,
            after.flow_stable_c,
            "°C",
            None,
            1,
        ),
    ]
    old_cold, cold = dict(before.cold_hours), dict(after.cold_hours)
    for room in sorted(old_cold.keys() | cold.keys()):
        specs.append(
            (
                f"Comfortverlies {room}",
                f"Meer dan {number(fact.policy.comfort_deficit_c, '°C')} onder setpoint; "
                "omgerekend naar een waargenomen week.",
                old_cold.get(room),
                cold.get(room),
                "u/week",
                False,
                1,
            )
        )
    for label, note, old, new, unit, increasing, scale in specs:
        assessment = MetricAssessment.NEUTRAL
        if (
            old is not None
            and new is not None
            and increasing is not None
            and round(old * scale, 1) != round(new * scale, 1)
        ):
            assessment = (
                MetricAssessment.BETTER if (new > old) == increasing else MetricAssessment.WORSE
            )
        maximum = max(old or 0, new or 0)
        metrics.append(
            MetricComparison(
                label=label,
                note=note,
                before=number(old, unit, scale=scale),
                after=number(new, unit, scale=scale),
                before_bar_pct=old / maximum * 100 if old is not None and maximum else 0,
                after_bar_pct=new / maximum * 100 if new is not None and maximum else 0,
                effect_text="Onvoldoende meetgegevens"
                if old is None or new is None
                else "Geen verschil zichtbaar"
                if round((new - old) * scale, 1) == 0
                else f"Verschil: {number(new - old, unit, scale=scale)}",
                assessment=assessment,
            )
        )
    verdict = EvaluationVerdict(fact.verdict)
    return EvaluationOut(
        change_id=fact.change_id,
        verdict=verdict,
        verdict_text=VERDICTS[verdict],
        summary=fact.summary
        + (" Het terugdraaicriterium is geactiveerd." if fact.rollback else ""),
        before=RangeOut(start=_dt(fact.reference.start), end=_dt(fact.reference.end)),
        after=RangeOut(start=_dt(fact.observation.start), end=_dt(fact.observation.end)),
        before_text=(
            f"{_dt(fact.reference.start).astimezone(ZoneInfo('Europe/Amsterdam')):%d-%m-%Y} "
            f"tot {_dt(fact.reference.end).astimezone(ZoneInfo('Europe/Amsterdam')):%d-%m-%Y}"
        ),
        after_text=(
            f"{_dt(fact.observation.start).astimezone(ZoneInfo('Europe/Amsterdam')):%d-%m-%Y} "
            f"tot {_dt(fact.observation.end).astimezone(ZoneInfo('Europe/Amsterdam')):%d-%m-%Y}"
        ),
        conditions=conditions,
        metrics=metrics,
        result_expected_at=_dt(fact.observation.end)
        if verdict is EvaluationVerdict.PENDING
        else None,
    )


def render_persisted_evaluation(row: ChangeEvaluation) -> EvaluationOut:
    """Render the last stored evaluation without recalculating its periods or metrics."""
    verdict = EvaluationVerdict(row.verdict)
    return EvaluationOut(
        change_id=row.change.human_id,
        verdict=verdict,
        verdict_text=VERDICTS[verdict],
        summary=row.summary or "",
        before=RangeOut(start=_dt(row.reference_start_ts), end=_dt(row.reference_end_ts)),
        after=RangeOut(start=_dt(row.observation_start_ts), end=_dt(row.observation_end_ts)),
        before_text=(
            f"{_dt(row.reference_start_ts).astimezone(ZoneInfo('Europe/Amsterdam')):%d-%m-%Y} "
            f"tot {_dt(row.reference_end_ts).astimezone(ZoneInfo('Europe/Amsterdam')):%d-%m-%Y}"
        ),
        after_text=(
            f"{_dt(row.observation_start_ts).astimezone(ZoneInfo('Europe/Amsterdam')):%d-%m-%Y} "
            f"tot {_dt(row.observation_end_ts).astimezone(ZoneInfo('Europe/Amsterdam')):%d-%m-%Y}"
        ),
        conditions=[ConditionRow.model_validate(item) for item in row.comparability],
        metrics=[MetricComparison.model_validate(item) for item in row.metrics],
        result_expected_at=_dt(row.observation_end_ts)
        if verdict is EvaluationVerdict.PENDING
        else None,
    )


def _comfort_context(
    session: Session,
    window: TimeRange,
    special_periods: list[SpecialPeriod],
) -> tuple[dict[str, RoomComfort], dict[str, tuple[RoomComfortPeriod, ...]], bool]:
    rows = list(
        session.scalars(
            select(ProfileRow)
            .where(
                ProfileRow.valid_from_ts < window.end,
                or_(ProfileRow.valid_to_ts.is_(None), ProfileRow.valid_to_ts > window.start),
            )
            .order_by(ProfileRow.valid_from_ts, ProfileRow.id)
        )
    )
    profile = next(
        (
            row
            for row in rows
            if row.valid_from_ts <= window.start
            and (row.valid_to_ts is None or row.valid_to_ts > window.start)
        ),
        None,
    )
    if profile is None:
        return {}, {}, True
    mixed = (
        len(rows) != 1
        or profile.valid_from_ts > window.start
        or (profile.valid_to_ts is not None and profile.valid_to_ts < window.end)
    )
    room_details = profile.details.get("rooms", {})
    comfort_by_room = {
        room.key: RoomComfort.model_validate(
            room_details.get(room.key, {}).get(
                "comfort", {"status": "not_configured", "windows": []}
            )
        )
        for room in profile.rooms
    }
    periods_by_room: dict[str, list[RoomComfortPeriod]] = {key: [] for key in comfort_by_room}
    for period in special_periods:
        start = max(window.start, period.start_ts)
        end = min(window.end, period.end_ts or window.end)
        if start >= end:
            continue
        overrides = {
            override.room_key: override
            for raw_override in period.room_overrides
            if (override := RoomComfortOverride.model_validate(raw_override)).room_key
            in periods_by_room
        }
        for room_key, room_periods in periods_by_room.items():
            room_override = overrides.get(room_key)
            room_periods.append(
                RoomComfortPeriod(
                    start=start,
                    end=end,
                    excluded=period.exclude_from_comparisons,
                    override_kind=None if room_override is None else room_override.kind,
                    override_target_c=None
                    if room_override is None
                    else room_override.target_temperature_c,
                )
            )
    return (
        comfort_by_room,
        {key: tuple(periods) for key, periods in periods_by_room.items()},
        mixed,
    )


def evaluate_stored_change(
    session: Session,
    change: Change,
    now: int,
    settings: AnalysisSettings | None = None,
    config: PipelineConfig | None = None,
) -> EvaluationFact:
    from cvidee.findings.stage import StoreTimelines

    values = settings or effective_values(current_revision(session))
    policy = policy_from(values)
    reference = TimeRange(change.changed_at_ts - policy.days * DAY_MS, change.changed_at_ts)
    observation = TimeRange(change.changed_at_ts, change.changed_at_ts + policy.days * DAY_MS)
    horizon = max(reference.start + 1, min(now, observation.end))
    combined = TimeRange(reference.start, horizon)
    sources = SourceSettings()
    mapped = load_mapped_signals(session)
    config = config or build_pipeline_config(
        session, mapped, sources, base=pipeline_settings(None, values)
    )
    built = StoreTimelines(session, mapped, sources, config, horizon).build(combined)
    quality = apply_quality(
        tuple(built.values()), config, AnalysisWindow(combined.start, combined.start, horizon)
    )
    repo = SqlDerivedDataRepository(session)
    cycles = tuple(repo.burner_cycles(reference.start, horizon))
    modes = tuple(repo.mode_segments(reference.start, horizon))
    periods = list(
        session.scalars(
            select(SpecialPeriod).where(
                SpecialPeriod.start_ts < observation.end,
                SpecialPeriod.end_ts.is_(None) | (SpecialPeriod.end_ts > reference.start),
            )
        )
    )
    exclusions = tuple(
        TimeRange(
            max(reference.start, p.start_ts), min(observation.end, p.end_ts or observation.end)
        )
        for p in periods
        if p.exclude_from_comparisons
    )
    before_comfort, before_periods, before_mixed = _comfort_context(session, reference, periods)
    after_comfort, after_periods, after_mixed = _comfort_context(session, observation, periods)
    before = period_metrics(
        reference,
        quality.timelines,
        cycles,
        modes,
        exclusions,
        policy,
        before_comfort,
        before_periods,
        before_mixed,
    )
    after = period_metrics(
        observation,
        quality.timelines,
        cycles,
        modes,
        exclusions,
        policy,
        after_comfort,
        after_periods,
        after_mixed,
    )
    overlaps = tuple(
        session.scalars(
            select(Change.human_id)
            .where(
                Change.id != change.id,
                Change.changed_at_ts >= reference.start,
                Change.changed_at_ts < observation.end,
            )
            .order_by(Change.changed_at_ts, Change.id)
        )
    )
    if len(change.items) > 1:
        overlaps += (change.human_id,)
    recommendation = (
        None
        if change.recommendation_id is None
        else session.get(Recommendation, change.recommendation_id)
    )
    rollback_room, rollback_limit = None, None
    criterion_supported = True
    if recommendation is not None and recommendation.rollback_spec:
        spec = recommendation.rollback_spec
        criterion_supported = False
        if spec.get("metric") == "room_cold_hours_per_week" and spec.get("op") == ">":
            scope = str(spec.get("scope_key", ""))
            rollback_room = scope.removeprefix("room:") or None
            threshold = spec.get("threshold")
            if (
                isinstance(threshold, int | float)
                and not isinstance(threshold, bool)
                and math.isfinite(threshold)
                and threshold >= 0
            ):
                rollback_limit = float(threshold)
                criterion_supported = True
    fact = evaluate_change(
        change.human_id,
        reference,
        observation,
        before,
        after,
        now,
        policy,
        overlaps,
        rollback_room,
        rollback_limit,
    )
    if not criterion_supported:
        fact = replace(
            fact,
            rollback=False,
            verdict="insufficient_evidence" if fact.verdict == "improved" else fact.verdict,
            summary=fact.summary
            + " Het opgegeven terugdraaicriterium kon niet automatisch worden beoordeeld.",
        )
    rendered = render_evaluation(fact)
    row = change.evaluation
    if row is None:
        row = ChangeEvaluation(change_id=change.id)
        change.evaluation = row
    row.computed_at_ts = now
    row.reference_start_ts, row.reference_end_ts = reference.start, reference.end
    row.observation_start_ts, row.observation_end_ts = observation.start, observation.end
    row.verdict, row.summary, row.rollback_triggered = (
        rendered.verdict,
        rendered.summary,
        fact.rollback,
    )
    row.comparability = [condition.model_dump(mode="json") for condition in rendered.conditions]
    row.metrics = [metric.model_dump(mode="json") for metric in rendered.metrics]
    row.excluded_periods, row.overlapping_change_ids = (
        [p.id for p in periods if p.exclude_from_comparisons],
        list(overlaps),
    )
    row.rule_version = RULE_VERSION
    row.config_hash = hashlib.sha256(
        canonical_json(
            {
                "policy": asdict(policy),
                "pipeline": config.config_hash,
                "rollback_spec": None if recommendation is None else recommendation.rollback_spec,
                "room_comfort": {
                    "before": _comfort_hash_context(before_comfort, before_periods, before_mixed),
                    "after": _comfort_hash_context(after_comfort, after_periods, after_mixed),
                },
            }
        ).encode()
    ).hexdigest()
    if recommendation is not None and recommendation.status in (
        RecommendationStatus.DONE,
        RecommendationStatus.ROLLBACK_TRIGGERED,
    ):
        old_status, old_outcome = recommendation.status, recommendation.outcome
        recommendation.outcome = (
            RecommendationOutcome.UNFAVOURABLE
            if fact.verdict in ("worsened", "trade_off")
            else RecommendationOutcome.SUCCEEDED
            if fact.verdict == "improved"
            else RecommendationOutcome.UNDECIDED
        )
        if fact.rollback:
            recommendation.status = RecommendationStatus.ROLLBACK_TRIGGERED
            if recommendation.status != old_status:
                recommendation.status_changed_at_ts = now
        if old_status is RecommendationStatus.ROLLBACK_TRIGGERED and not fact.rollback:
            recommendation.outcome = old_outcome
        if recommendation.status != old_status or recommendation.outcome != old_outcome:
            snapshot_transition(
                session,
                recommendation.finding,
                now,
                trigger=SnapshotTrigger.STATUS_CHANGED
                if recommendation.status != old_status
                else SnapshotTrigger.CONTENT_UPDATED,
                extra_content={
                    "change_evaluation": rendered.model_dump(mode="json"),
                    "evaluation_parameters": {
                        **asdict(policy),
                        "effective_rollback_limit_h_week": policy.comfort_limit_h_week
                        if rollback_limit is None
                        else rollback_limit,
                        "rollback_room": rollback_room,
                        "rollback_spec": recommendation.rollback_spec,
                    },
                    "evaluation_config_hash": row.config_hash,
                },
            )
    experiment = session.scalar(select(Experiment).where(Experiment.change_id == change.id))
    if experiment is not None and experiment.status is ExperimentStatus.RUNNING:
        if fact.verdict != EvaluationVerdict.PENDING:
            experiment.status = ExperimentStatus.COMPLETED
            experiment.completed_at_ts = now
        experiment.updated_at_ts = now
    session.flush()
    return fact


def _comfort_hash_context(
    comfort: dict[str, RoomComfort],
    periods: dict[str, tuple[RoomComfortPeriod, ...]],
    mixed: bool,
) -> dict[str, object]:
    return {
        "profiles_mixed": mixed,
        "rooms": {
            key: {
                "comfort": value.model_dump(mode="json"),
                "periods": [
                    {
                        "start": period.start,
                        "end": period.end,
                        "excluded": period.excluded,
                        "override_kind": period.override_kind,
                        "override_target_c": period.override_target_c,
                    }
                    for period in periods.get(key, ())
                ],
            }
            for key, value in comfort.items()
        },
    }


def evaluate_changes(
    session: Session,
    now: int,
    settings: AnalysisSettings | None = None,
    config: PipelineConfig | None = None,
) -> tuple[EvaluationFact, ...]:
    return tuple(
        evaluate_stored_change(session, change, now, settings, config)
        for change in session.scalars(
            select(Change).where(Change.changed_at_ts <= now).order_by(Change.id)
        )
    )
