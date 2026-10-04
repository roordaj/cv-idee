"""Stage 2 — data quality: plausibility, counter resets, alignment, coverage (ADR-002 §3.2).

FR-07, FR-08, FR-11. Pure: no I/O, no wall clock.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from cvidee.analysis.types import (
    AnalysisWindow,
    DurationMs,
    PairSample,
    PipelineConfig,
    QualityEvent,
    SignalRef,
    SignalTimeline,
    TimestampMs,
)


@dataclass(frozen=True, slots=True)
class QualityResult:
    """Timelines after quality checks plus the detected events."""

    timelines: tuple[SignalTimeline, ...]
    events: tuple[QualityEvent, ...]


def apply_quality(
    timelines: Sequence[SignalTimeline],
    config: PipelineConfig,
    window: AnalysisWindow,
) -> QualityResult:
    """Apply quality rules to the stage-1 timelines.

    * Values outside ``[plausible_min, plausible_max]`` become
      ``UnknownInterval(IMPLAUSIBLE)``; values of the wrong type become ``INVALID``.
    * Every unknown interval yields a :class:`QualityEvent` (kind from its reason;
      consecutive intervals with the same reason form one event), split on the canonical
      grid (``config.grid_ms``) with key ``(kind, signal, start)``. An event still open at
      ``window.end`` has ``end=None``.
    * Counter resets (:func:`detect_counter_resets`) are reported, never turned into
      negative consumption.
    * Misaligned combinations are detected by consumers via :func:`align_pair` (they know
      which combinations they need) and reported as ``QualityEvent(MISALIGNED)``.

    ``final`` flags are left ``False``; the pipeline sets them from the next watermark.
    """
    raise NotImplementedError


def detect_counter_resets(timeline: SignalTimeline) -> tuple[QualityEvent, ...]:
    """Detect resets of a cumulative counter (e.g. gas): a decrease starts a new segment.

    Consumption across a reset is computed per segment (FR-08: never negative).
    """
    raise NotImplementedError


def pair_tolerance(config: PipelineConfig, a: SignalRef, b: SignalRef) -> DurationMs:
    """Sampling tolerance for combining ``a`` and ``b`` (order-insensitive); falls back to
    ``config.default_pair_tolerance_ms``."""
    raise NotImplementedError


def align_pair(
    a: SignalTimeline,
    b: SignalTimeline,
    ts: TimestampMs,
    tolerance_ms: DurationMs,
    *,
    a_heartbeat: bool,
    b_heartbeat: bool,
) -> PairSample:
    """Sample two signals at ``ts`` and judge whether they may be combined (FR-07).

    * Either value unknown → ``alignment=None`` (the pair is unknown, not misaligned).
    * Both heartbeat signals and ``|observed_at_a - observed_at_b| <= tolerance_ms`` →
      ``ALIGNED``.
    * Both heartbeat signals beyond tolerance → ``MISALIGNED``: callers must not combine
      the values and report a ``QualityEvent(MISALIGNED)``.
    * At least one change-only signal → ``ASSUMED_UNCHANGED`` (combined, weaker certainty),
      unless the change-only value is older than the other signal's last *change* by more
      than the tolerance while the other one changed (then ``MISALIGNED``) — see ADR-002 §7.
    """
    raise NotImplementedError


def coverage_by_signal(
    timelines: Sequence[SignalTimeline], window: AnalysisWindow
) -> dict[SignalRef, float]:
    """Known fraction per signal over ``[window.emit_from, window.end)`` (FR-11)."""
    raise NotImplementedError
