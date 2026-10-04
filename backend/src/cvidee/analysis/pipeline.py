"""Composition of the pure analysis stages (ADR-002 §3, §4).

:func:`run_pipeline` is the only entry point used by the runner, both live and for
historical import. Stage 6 (rules) lives in :mod:`cvidee.rules` and runs on the persisted
result.
"""

from __future__ import annotations

from collections.abc import Sequence

from cvidee.analysis.types import (
    AnalysisWindow,
    BurnerCycle,
    ConnectionEvent,
    Observation,
    PipelineConfig,
    PipelineResult,
    TimestampMs,
)


def next_watermark(
    cycles: Sequence[BurnerCycle], window: AnalysisWindow, config: PipelineConfig
) -> TimestampMs:
    """``min(window.end - config.end_reason_lookahead_ms, start of the earliest non-final
    cycle)``, clamped to ``[window.emit_from, window.end]``.

    A cycle is non-final if it is open (``end is None``) or ends after
    ``window.end - end_reason_lookahead_ms`` (its end reason may still change).
    """
    raise NotImplementedError


def run_pipeline(
    observations: Sequence[Observation],
    connection_events: Sequence[ConnectionEvent],
    config: PipelineConfig,
    window: AnalysisWindow,
    now: TimestampMs,
) -> PipelineResult:
    """Run stages 1 to 5 over ``window.context`` and return only emitted items.

    Steps: :func:`~cvidee.analysis.timeline.build_timelines` →
    :func:`~cvidee.analysis.quality.apply_quality` →
    :func:`~cvidee.analysis.modes.classify_modes` →
    :func:`~cvidee.analysis.cycles.detect_cycles` →
    :func:`~cvidee.analysis.metrics_cycles.hourly_cycle_metrics`,
    :func:`~cvidee.analysis.metrics_temperature.cycle_temperature_metrics` and
    :func:`~cvidee.analysis.metrics_temperature.hourly_temperature_metrics`.

    Contract (ADR-002):

    * Pure and deterministic: no I/O, no wall clock. ``now`` is a parameter and is only used
      to check ``window.end <= now - config.settle_ms`` (``ValueError`` otherwise).
    * ``observations``/``connection_events`` contain everything in
      ``[window.context_start, window.end)`` plus, per signal/source, the latest item before
      ``context_start`` (carry-in). Items at or after ``window.end`` are ignored; input order
      is irrelevant.
    * Only items whose key lies in ``[window.emit_from, window.end)`` are returned. Items
      ending at or before the returned ``next_watermark`` are ``final``; the rest
      (open cycles, the partial last bucket/segment, ongoing quality events) are
      provisional and will be replaced by a later run.
    """
    raise NotImplementedError
