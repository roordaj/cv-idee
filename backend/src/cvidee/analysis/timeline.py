"""Stage 1 — timeline: observations → per-signal validity intervals (ADR-002 §3.1).

Pure: no I/O, no wall clock. Input is filtered to the window by the caller *and* defensively
here (observations at or after ``window.end`` are ignored).
"""

from __future__ import annotations

from collections.abc import Sequence

from cvidee.analysis.types import (
    AnalysisWindow,
    ConnectionEvent,
    ConnectionSource,
    Observation,
    PipelineConfig,
    SignalConfig,
    SignalTimeline,
    TimeRange,
    UnknownInterval,
)


def connection_outages(
    connection_events: Sequence[ConnectionEvent],
    window: AnalysisWindow,
) -> dict[ConnectionSource, tuple[TimeRange, ...]]:
    """Reconstruct down-periods per connection source within ``window.context``.

    The state at ``window.context_start`` comes from the carry-in event (latest event before
    the context start, supplied by the runner). An outage still open at ``window.end`` is
    clipped to ``window.end``. Events are sorted by ``(ts, source, up)`` first; repeated
    "down" events are idempotent.

    Returns:
        Sorted, non-overlapping outage ranges per source (empty tuple if none).
    """
    raise NotImplementedError


def build_timeline(
    signal: SignalConfig,
    observations: Sequence[Observation],
    outages: Sequence[TimeRange],
    window: AnalysisWindow,
) -> SignalTimeline:
    """Build the timeline of one signal over ``window.context``.

    Rules (ADR-002 §3.1, §7, §8):

    * Each accepted observation starts a :class:`ValueInterval` that lasts until the next
      observation of the signal, an outage, staleness, or ``window.end``.
    * The carry-in observation (latest before ``context_start``) yields an interval clipped
      to start at ``context_start``; it keeps its ``observed_at`` and ``origin``.
    * ``value is None`` (HA ``unavailable``/``unknown``) → ``UnknownReason.UNAVAILABLE``.
    * Outages → ``DISCONNECTED``: our WebSocket affects every signal, the CAN gateway only
      signals with ``via_can_gateway``.
    * Staleness only for ``heartbeat_expected`` signals: the value is valid until
      ``evidence_ts + max_age_ms`` and ``STALE`` after that (prospective, never retroactive).
    * Before the first observation: ``NO_DATA``.
    * Identical ``(ts, value)`` duplicates are dropped; ordering uses
      :attr:`Observation.sort_key` so input order never matters.
    * Plausibility is *not* checked here (stage 2).

    Returns:
        A timeline whose intervals exactly cover ``window.context``.
    """
    raise NotImplementedError


def build_timelines(
    observations: Sequence[Observation],
    connection_events: Sequence[ConnectionEvent],
    config: PipelineConfig,
    window: AnalysisWindow,
) -> tuple[SignalTimeline, ...]:
    """Build one timeline per configured signal, sorted by ``SignalRef``.

    Configured signals without observations get a single ``NO_DATA`` interval; observations
    of unconfigured signals are ignored.
    """
    raise NotImplementedError


def unknown_union(
    timelines: Sequence[SignalTimeline], rng: TimeRange
) -> tuple[UnknownInterval, ...]:
    """Ranges within ``rng`` where *any* of ``timelines`` is unknown (for combined values).

    Overlapping reasons are resolved by a fixed precedence (disconnected > unavailable >
    stale > invalid > implausible > no_data) so the result is deterministic.
    """
    raise NotImplementedError
