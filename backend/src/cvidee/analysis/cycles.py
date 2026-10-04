"""Stage 4 — burner cycles (ADR-002 §3.4, FR-12, FR-15, FR-16).

Pure: no I/O, no wall clock.
"""

from __future__ import annotations

from collections.abc import Sequence

from cvidee.analysis.types import (
    AnalysisWindow,
    BurnerCycle,
    CycleAggregates,
    EndReason,
    Mode,
    ModeSegment,
    PhaseSpan,
    PipelineConfig,
    SignalTimeline,
    TimeRange,
    TimestampMs,
)


def detect_cycles(
    timelines: Sequence[SignalTimeline],
    modes: Sequence[ModeSegment],
    config: PipelineConfig,
    window: AnalysisWindow,
) -> tuple[BurnerCycle, ...]:
    """Reconstruct burner cycles from the flame timeline.

    * Start: a flame-on ``ValueInterval`` with ``origin == CHANGE`` directly preceded by a
      known flame-off interval → ``start_observed=True``. Flame on after unknown time, at the
      window start, or from a ``POLL``/``CONFIRM`` → a cycle with ``start_observed=False``
      (no artificial start after reconnect, FR-08).
    * End: first known flame-off → ``end`` with an :class:`EndReason` from
      :func:`classify_end_reason`. Flame becomes unknown while on → ``end`` = start of the
      unknown interval, ``end_reason=DATA_GAP``, ``complete=False`` and the duration is a
      lower bound. Still on at ``window.end`` → ``end=None`` (open, provisional) with
      duration ``window.end - start`` as lower bound.
    * Mode: ``DHW`` if any DHW segment overlaps the burning part, else ``CH`` if CH
      overlaps, else ``UNKNOWN``.
    * ``pause_before_ms``: only if the previous cycle ended at most ``config.max_pause_ms``
      earlier and the flame was known-off in between; otherwise ``None``.
    * Phases via :func:`cycle_phases`, aggregates via :func:`cycle_aggregates`.

    Returns:
        Cycles sorted by ``start``; ``final`` flags are set by the pipeline.
    """
    raise NotImplementedError


def classify_end_reason(
    stop: TimestampMs,
    mode: Mode,
    heat_demand: SignalTimeline | None,
    config: PipelineConfig,
) -> EndReason:
    """Why the burner stopped at the observed flame-off transition ``stop``.

    * ``DHW`` cycle → ``DHW_ENDED``.
    * Heat demand known and present throughout
      ``[stop, stop + config.end_reason_lookahead_ms)`` → ``STOP_DURING_DEMAND``.
    * Heat demand known and absent at some point in that range (ended at or before the stop
      within the lookahead) → ``DEMAND_ENDED``.
    * Heat demand unknown around the stop or not mapped → ``UNDETERMINED``: rules never
      claim a stop during demand without evidence (ADR-002 §3.4).

    ``DATA_GAP`` is never returned here; it is assigned when the flame itself is unknown.
    """
    raise NotImplementedError


def cycle_phases(
    cycle_range: TimeRange,
    flow: SignalTimeline | None,
    flow_setpoint: SignalTimeline | None,
    modes: Sequence[ModeSegment],
    config: PipelineConfig,
) -> tuple[PhaseSpan, ...]:
    """Split a cycle into phases (FR-15).

    * ``STARTUP``: from start until flow reaches ``setpoint - startup_flow_margin_k`` or
      ``startup_max_ms`` has elapsed, whichever comes first.
    * ``STABLE``: rest of the burning part (absent for very short cycles).
    * ``AFTERRUN``: from flame-off while the mode is ``AFTERRUN`` (may extend past the cycle
      end, at most ``afterrun_max_ms``).
    """
    raise NotImplementedError


def cycle_aggregates(
    cycle_range: TimeRange,
    timelines: Sequence[SignalTimeline],
    config: PipelineConfig,
) -> CycleAggregates:
    """Per-cycle aggregates over the burning part using only known time. Time-weighted means
    are summed in time order with ``math.fsum`` (determinism)."""
    raise NotImplementedError
