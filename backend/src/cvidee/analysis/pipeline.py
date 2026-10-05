"""Composition of the pure analysis stages (ADR-002 §3, §4).

:func:`run_pipeline` is the only entry point used by the runner, both live and for
historical import. Stage 6 (rules) lives in :mod:`cvidee.rules` and runs on the persisted
result.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Protocol

from cvidee.analysis.cycles import cycle_settles_at, detect_cycles
from cvidee.analysis.metrics_cycles import grid_buckets, hourly_cycle_metrics
from cvidee.analysis.metrics_temperature import (
    cycle_temperature_metrics,
    hourly_temperature_metrics,
)
from cvidee.analysis.modes import classify_modes
from cvidee.analysis.quality import apply_quality, duplicate_events
from cvidee.analysis.timeline import build_stage1
from cvidee.analysis.types import (
    AnalysisWindow,
    BurnerCycle,
    ConnectionEvent,
    MetricValue,
    ModeSegment,
    Observation,
    PipelineConfig,
    PipelineResult,
    QualityEvent,
    Role,
    SignalRef,
    SignalTimeline,
    TimestampMs,
)


@dataclass(frozen=True, slots=True)
class MetricInput:
    """Everything a stage-5 metric function may use (all over ``window.context``)."""

    timelines: tuple[SignalTimeline, ...]
    modes: tuple[ModeSegment, ...]
    cycles: tuple[BurnerCycle, ...]
    config: PipelineConfig
    window: AnalysisWindow


class MetricStage(Protocol):
    """A stage-5 step: returns metric values; the pipeline keeps those keyed in the emitted
    range and sets ``final``."""

    def __call__(self, data: MetricInput, /) -> Sequence[MetricValue]: ...


def _timeline(data: MetricInput, role: Role) -> SignalTimeline | None:
    return next((t for t in data.timelines if t.signal == SignalRef(role)), None)


def cycle_metrics_stage(data: MetricInput) -> Sequence[MetricValue]:
    """Stage 5a (#28): hourly cycle metrics. Without a flame signal nothing is observed."""
    flame = _timeline(data, Role.FLAME)
    if flame is None:
        return ()
    buckets = grid_buckets(data.window, data.config.grid_ms)
    return hourly_cycle_metrics(
        data.cycles,
        data.modes,
        flame,
        _timeline(data, Role.HEAT_DEMAND),
        buckets,
        data.config,
    )


def temperature_metrics_stage(data: MetricInput) -> Sequence[MetricValue]:
    """Stage 5b (#29): per-cycle and hourly temperature metrics."""
    buckets = grid_buckets(data.window, data.config.grid_ms)
    return (
        *cycle_temperature_metrics(data.cycles, data.timelines, data.config),
        *hourly_temperature_metrics(data.cycles, data.timelines, buckets, data.config),
    )


METRIC_STAGES: tuple[MetricStage, ...] = (cycle_metrics_stage, temperature_metrics_stage)
"""Stage 5 (ADR-002 §3.5): the metric functions; the runner persists what they return."""


def next_watermark(
    cycles: Sequence[BurnerCycle], window: AnalysisWindow, config: PipelineConfig
) -> TimestampMs:
    """``min(window.end - config.end_reason_lookahead_ms, start of the earliest non-final
    cycle)``, clamped to ``[window.emit_from, window.end]``.

    A cycle is non-final if it is open or not yet settled at the horizon:
    :func:`~cvidee.analysis.cycles.cycle_settles_at` is ``None`` or after ``window.end``
    (end-reason lookahead *and* afterrun, ADR-002 §4.3 amended by #26).
    """
    candidate = window.end - config.end_reason_lookahead_ms
    for cycle in cycles:
        settles = cycle_settles_at(cycle, config)
        if settles is None or settles > window.end:
            candidate = min(candidate, cycle.start)
    return min(max(candidate, window.emit_from), window.end)


def _metric_key_start(metric: MetricValue) -> TimestampMs:
    return metric.window.range.start


def run_pipeline(
    observations: Sequence[Observation],
    connection_events: Sequence[ConnectionEvent],
    config: PipelineConfig,
    window: AnalysisWindow,
    now: TimestampMs,
) -> PipelineResult:
    """Run stages 1 to 5 over ``window.context`` and return only emitted items.

    Steps: :func:`~cvidee.analysis.timeline.build_stage1` →
    :func:`~cvidee.analysis.quality.apply_quality` (+
    :func:`~cvidee.analysis.quality.duplicate_events`) →
    :func:`~cvidee.analysis.modes.classify_modes` →
    :func:`~cvidee.analysis.cycles.detect_cycles` → the registered :data:`METRIC_STAGES`.

    Contract (ADR-002):

    * Pure and deterministic: no I/O, no wall clock. ``now`` is a parameter and is only used
      to check ``window.end <= now - config.settle_ms`` (``ValueError`` otherwise).
    * ``observations``/``connection_events`` contain everything in
      ``[window.context_start, window.end)`` plus, per signal/source, the latest item before
      ``context_start`` (carry-in); connection events from the latest "down" before
      ``context_start`` onwards make an outage that ended before the context visible.
      Items at or after ``window.end`` are ignored; input order is irrelevant.
    * Only items whose key lies in ``[window.emit_from, window.end)`` are returned. Items
      ending at or before the returned ``next_watermark`` are ``final``; the rest
      (open cycles, the partial last bucket/segment, ongoing quality events) are
      provisional and will be replaced by a later run.
    """
    if window.end > now - config.settle_ms:
        raise ValueError("run_pipeline: window.end must be <= now - settle_ms")
    if window.context is None:
        return PipelineResult(
            window=window,
            next_watermark=window.emit_from,
            timelines=(),
            quality_events=(),
            mode_segments=(),
            cycles=(),
            metrics=(),
            config_hash=config.config_hash,
        )
    stage1 = build_stage1(observations, connection_events, config, window)
    quality = apply_quality(stage1.timelines, config, window, stage1.outages)
    events = (*quality.events, *duplicate_events(observations, config, window))
    modes = classify_modes(quality.timelines, config, window)
    cycles = detect_cycles(quality.timelines, modes, config, window)
    data = MetricInput(quality.timelines, modes, cycles, config, window)
    metrics = [m for stage in METRIC_STAGES for m in stage(data)]
    watermark = next_watermark(cycles, window, config)

    def done(end: TimestampMs | None) -> bool:
        return end is not None and end <= watermark

    out_events: list[QualityEvent] = sorted(
        (replace(e, final=done(e.end)) for e in events if window.emits(e.start)),
        key=lambda e: e.key,
    )
    return PipelineResult(
        window=window,
        next_watermark=watermark,
        timelines=quality.timelines,
        quality_events=tuple(out_events),
        mode_segments=tuple(replace(m, final=done(m.end)) for m in modes if window.emits(m.start)),
        cycles=tuple(replace(c, final=done(c.end)) for c in cycles if window.emits(c.key)),
        metrics=tuple(
            sorted(
                (
                    replace(m, final=done(m.window.range.end))
                    for m in metrics
                    if window.emits(_metric_key_start(m))
                ),
                key=lambda m: (
                    m.window.range.start,
                    m.name.value,
                    "" if m.mode is None else m.mode.value,
                    m.window.kind.value,
                    -1 if m.window.cycle_start is None else m.window.cycle_start,
                ),
            )
        ),
        config_hash=config.config_hash,
    )
