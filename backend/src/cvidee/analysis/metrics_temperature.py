"""Stage 5b — temperature metrics (ADR-002 §3.5, FR-15). Pure: no I/O, no wall clock."""

from __future__ import annotations

from collections.abc import Sequence

from cvidee.analysis.types import (
    BurnerCycle,
    MetricValue,
    PipelineConfig,
    SignalTimeline,
    TimeRange,
)


def cycle_temperature_metrics(
    cycles: Sequence[BurnerCycle],
    timelines: Sequence[SignalTimeline],
    config: PipelineConfig,
) -> tuple[MetricValue, ...]:
    """Per-cycle metrics (``MetricWindowKind.CYCLE``) for CH cycles:

    * ``OVERSHOOT``: max(flow - flow_setpoint) during the burning part (K).
    * ``HEATING_RATE``: flow rise during ``STARTUP`` (K/min).
    * ``BOILER_DELTA_T_STABLE`` and ``FLOW_MEAN_STABLE``: only during the ``STABLE`` phase
      and only on samples where :func:`cvidee.analysis.quality.align_pair` is not
      ``MISALIGNED`` (time basis = aligned stable time).

    DHW cycles are skipped (FR-09: DHW heating is never reported as high CH flow).
    """
    raise NotImplementedError


def hourly_temperature_metrics(
    cycles: Sequence[BurnerCycle],
    timelines: Sequence[SignalTimeline],
    buckets: Sequence[TimeRange],
    config: PipelineConfig,
) -> tuple[MetricValue, ...]:
    """Per-bucket stable-phase means (``FLOW_MEAN_STABLE``, ``BOILER_DELTA_T_STABLE``) with
    their time basis, for before/after evaluation and HA export."""
    raise NotImplementedError
