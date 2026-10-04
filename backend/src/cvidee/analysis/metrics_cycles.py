"""Stage 5a — cycle metrics (ADR-002 §3.5, FR-13). Pure: no I/O, no wall clock.

Two tiers: additive grid-bucket metrics inside the pipeline run, and period summaries
(day, rolling 6 h, before/after) computed from stored cycles with :func:`summarize_cycles`.
"""

from __future__ import annotations

from collections.abc import Sequence

from cvidee.analysis.types import (
    AnalysisWindow,
    BurnerCycle,
    DurationMs,
    MetricValue,
    ModeSegment,
    PipelineConfig,
    SignalTimeline,
    TimeRange,
)


def grid_buckets(window: AnalysisWindow, grid_ms: DurationMs) -> tuple[TimeRange, ...]:
    """Grid buckets intersecting ``[window.emit_from, window.end)``. The last one may be
    partial (clipped to ``window.end``) and is then provisional."""
    raise NotImplementedError


def hourly_cycle_metrics(
    cycles: Sequence[BurnerCycle],
    modes: Sequence[ModeSegment],
    flame: SignalTimeline,
    heat_demand: SignalTimeline | None,
    buckets: Sequence[TimeRange],
    config: PipelineConfig,
) -> tuple[MetricValue, ...]:
    """Additive per-bucket metrics: ``STARTS`` (only ``start_observed``, counted in the
    bucket of the start), ``BURN_TIME``, ``OBSERVED_TIME`` (flame and mode known) and
    ``HEAT_DEMAND_TIME``, per mode (``CH``/``DHW``) where relevant.

    Unknown time is never counted as off time: it is excluded from every time basis.
    """
    raise NotImplementedError


def summarize_cycles(
    cycles: Sequence[BurnerCycle],
    hourly: Sequence[MetricValue],
    period: TimeRange,
    config: PipelineConfig,
    *,
    short_cycle_ms: DurationMs,
) -> tuple[MetricValue, ...]:
    """Period metrics (FR-13) from stored cycles and hourly time bases.

    * ``STARTS_PER_HOUR`` = CH starts / observed hours (time basis exposed, FR-13). The
      design's simulation: 6 h window, 30 min unknown → basis 5,5 h.
    * ``BURN_DURATION_MEAN``/``MEDIAN`` over complete CH cycles only.
    * ``SHORT_CYCLES``/``SHORT_CYCLE_SHARE``: complete CH cycles with
      ``end_reason == STOP_DURING_DEMAND`` and duration ``< short_cycle_ms``.
    * ``PAUSE_DURATION_MEDIAN``: ``pause_before_ms`` of CH cycles whose predecessor ended
      with ``STOP_DURING_DEMAND`` (standby is never a pause).
    * DHW and incomplete cycles are excluded from CH statistics (still counted separately).
    * Day periods are Europe/Amsterdam days converted to UTC by the caller (23/25 h on DST
      days); the time basis makes that explicit.
    """
    raise NotImplementedError
