"""Stage 1 — timeline: observations → per-signal validity intervals (ADR-002 §3.1).

Pure: no I/O, no wall clock. Input is filtered to the window by the caller *and* defensively
here (observations at or after ``window.end`` are ignored).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import pairwise

from cvidee.analysis.types import (
    AnalysisWindow,
    ConnectionEvent,
    ConnectionSource,
    Observation,
    ObservationKind,
    ObservedValue,
    PipelineConfig,
    SignalConfig,
    SignalRef,
    SignalTimeline,
    TimeRange,
    TimestampMs,
    UnknownInterval,
    UnknownReason,
    ValueInterval,
)

type _Span = tuple[TimestampMs, TimestampMs]

_KIND_RANK = {
    ObservationKind.CHANGE: 0,
    ObservationKind.CONFIRM: 1,
    ObservationKind.POLL: 2,
}


# --------------------------------------------------------------------------------------
# Range helpers
# --------------------------------------------------------------------------------------


def _merge(spans: Iterable[_Span]) -> list[_Span]:
    """Sort, drop empty spans and merge overlapping or touching ones."""
    out: list[_Span] = []
    for start, end in sorted(s for s in spans if s[0] < s[1]):
        if out and start <= out[-1][1]:
            if end > out[-1][1]:
                out[-1] = (out[-1][0], end)
        else:
            out.append((start, end))
    return out


def _subtract(spans: Sequence[_Span], cuts: Sequence[_Span]) -> list[_Span]:
    """``spans`` minus ``cuts`` (both merged and sorted)."""
    out: list[_Span] = []
    for start, end in spans:
        cursor = start
        for c_start, c_end in cuts:
            if c_end <= cursor or c_start >= end:
                continue
            if c_start > cursor:
                out.append((cursor, c_start))
            cursor = max(cursor, c_end)
        if cursor < end:
            out.append((cursor, end))
    return out


def _clip(spans: Iterable[_Span], ctx: TimeRange) -> list[_Span]:
    return _merge((max(s, ctx.start), min(e, ctx.end)) for s, e in spans)


def _ranges(spans: Iterable[_Span]) -> tuple[TimeRange, ...]:
    return tuple(TimeRange(s, e) for s, e in spans)


def _spans(ranges: Iterable[TimeRange]) -> list[_Span]:
    return _merge((r.start, r.end) for r in ranges)


# --------------------------------------------------------------------------------------
# Connections
# --------------------------------------------------------------------------------------


def connection_outages(
    connection_events: Sequence[ConnectionEvent],
    window: AnalysisWindow,
) -> dict[ConnectionSource, tuple[TimeRange, ...]]:
    """Reconstruct down-periods per connection source within ``window.context``.

    The state at ``window.context_start`` comes from the carry-in event (latest event before
    the context start, supplied by the runner). An outage still open at ``window.end`` is
    clipped to ``window.end``. Events are sorted by ``(ts, source, up)`` first; repeated
    "down" events are idempotent.

    ADR-003 §5 and §6: a WS outage is reduced by ``HISTORY`` coverage ranges (backfilled from
    the HA recorder); the returned ``WS`` ranges are the *effective* gaps. ``HISTORY`` is
    returned as coverage ranges ("up" periods) under its own key, not as outages. Without
    any WS event (carry-in included) the WS is considered up.

    Returns:
        Sorted, non-overlapping outage ranges per source (empty tuple if none).
    """
    result: dict[ConnectionSource, tuple[TimeRange, ...]] = {s: () for s in ConnectionSource}
    ctx = window.context
    if ctx is None:
        return result
    ordered = sorted(
        (e for e in connection_events if e.ts < window.end),
        key=lambda e: (e.ts, e.source.value, e.up),
    )
    raw: dict[ConnectionSource, list[_Span]] = {}
    for source in ConnectionSource:
        # The "active" state is *down* for WS and the gateway, *up* for history coverage.
        active_when_up = source is ConnectionSource.HISTORY
        started: TimestampMs | None = None
        spans: list[_Span] = []
        for event in ordered:
            if event.source is not source:
                continue
            active = event.up == active_when_up
            if active and started is None:
                started = event.ts
            elif not active and started is not None:
                spans.append((started, event.ts))
                started = None
        if started is not None:
            spans.append((started, window.end))
        raw[source] = _clip(spans, ctx)
    raw[ConnectionSource.WS] = _subtract(raw[ConnectionSource.WS], raw[ConnectionSource.HISTORY])
    for source, spans in raw.items():
        result[source] = _ranges(spans)
    return result


@dataclass(frozen=True, slots=True)
class ConnectionOutages:
    """Effective outages of one run (ADR-003 §5, §6), all clipped to ``window.context``."""

    ws: tuple[TimeRange, ...] = ()
    """WebSocket gaps, after removing ``HISTORY`` coverage."""
    gateway: tuple[TimeRange, ...] = ()
    """Explicit CAN-gateway outages (connectivity entity)."""
    derived_gateway: tuple[TimeRange, ...] = ()
    """Gateway outages derived from stale heartbeat signals (§5.3), excluding ``gateway``."""
    history: tuple[TimeRange, ...] = ()
    """``HISTORY`` coverage ranges."""


@dataclass(frozen=True, slots=True)
class Stage1Result:
    timelines: tuple[SignalTimeline, ...]
    outages: ConnectionOutages


def derive_gateway_outages(
    timelines: Sequence[SignalTimeline], history: Sequence[TimeRange], rng: TimeRange
) -> tuple[TimeRange, ...]:
    """Gateway outage derived from the stage-1 timelines of the heartbeat signals that are
    ``via_can_gateway`` (ADR-003 §5.3): all of them unknown as ``STALE`` or ``UNAVAILABLE``,
    at least one ``STALE``, outside ``HISTORY`` coverage."""
    if not timelines:
        return ()
    bound_set = {rng.start, rng.end}
    for tl in timelines:
        for interval in tl.intervals:
            for b in (interval.start, interval.end):
                if rng.start < b < rng.end:
                    bound_set.add(b)
    bounds = sorted(bound_set)
    spans: list[_Span] = []
    for start, end in pairwise(bounds):
        reasons: list[UnknownReason] = []
        for tl in timelines:
            found = tl.at(start)
            if not isinstance(found, UnknownInterval):
                break
            reasons.append(found.reason)
        else:
            if all(r in (UnknownReason.STALE, UnknownReason.UNAVAILABLE) for r in reasons) and (
                UnknownReason.STALE in reasons
            ):
                spans.append((start, end))
    return _ranges(_subtract(_merge(spans), _spans(history)))


# --------------------------------------------------------------------------------------
# Single signal
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Obs:
    ts: TimestampMs
    value: ObservedValue | None
    kind: ObservationKind
    evidence: TimestampMs


def _prepare(
    signal: SignalRef, observations: Iterable[Observation], end: TimestampMs
) -> list[_Obs]:
    """Filter, order, de-duplicate and normalise the observations of one signal."""
    best: dict[tuple[TimestampMs, str], Observation] = {}
    for obs in observations:
        if obs.signal != signal or obs.ts >= end:
            continue
        key = (obs.ts, repr(obs.value))
        current = best.get(key)
        if current is None or _KIND_RANK[obs.kind] < _KIND_RANK[current.kind]:
            best[key] = obs
    ordered = sorted(best.values(), key=lambda o: o.sort_key)
    out: list[_Obs] = []
    previous: Observation | None = None
    for obs in ordered:
        kind = obs.kind
        if (
            kind is ObservationKind.CONFIRM
            and previous is not None
            and (type(previous.value) is not type(obs.value) or previous.value != obs.value)
        ):
            kind = ObservationKind.POLL  # a confirmation never changes the value (T14)
        out.append(_Obs(obs.ts, obs.value, kind, obs.evidence_ts))
        previous = obs
    return out


def build_timeline(
    signal: SignalConfig,
    observations: Sequence[Observation],
    outages: Sequence[TimeRange],
    window: AnalysisWindow,
    *,
    history: Sequence[TimeRange] = (),
    prior_outage_end: TimestampMs | None = None,
) -> SignalTimeline:
    """Build the timeline of one signal over ``window.context``.

    Rules (ADR-002 §3.1, §7, §8; decision rules and test cases T1-T22 in ADR-003):

    * Each accepted observation starts a :class:`ValueInterval` that lasts until the next
      observation of the signal, an outage, staleness, or ``window.end``.
    * The carry-in observation (latest before ``context_start``) yields an interval clipped
      to start at ``context_start``; it keeps its ``observed_at`` and ``origin``.
    * ``value is None`` (HA ``unavailable``/``unknown``) → ``UnknownReason.UNAVAILABLE``.
    * Outages → ``DISCONNECTED``: our WebSocket affects every signal, the CAN gateway only
      signals with ``via_can_gateway``. A value from before an outage never carries over:
      after the outage the signal stays ``DISCONNECTED`` until its next observation.
    * Staleness only for ``heartbeat_expected`` signals and only outside ``HISTORY``
      coverage (``history``): the value is valid until ``evidence_ts + max_age_ms`` and
      ``STALE`` after that (prospective, never retroactive). A poll whose evidence is
      already too old is ``STALE`` from its ``ts``.
    * Before the first observation: ``NO_DATA``.
    * Identical ``(ts, value)`` duplicates are dropped (the strongest kind survives:
      change > confirm > poll); ordering uses :attr:`Observation.sort_key` so input order
      never matters. A ``CONFIRM`` whose value differs from the preceding observation is
      treated as a ``POLL`` (never a transition).
    * Plausibility is *not* checked here (stage 2).

    ``outages`` are the ranges during which this signal is disconnected (the caller selects
    WS, gateway and derived outages per signal). Observations inside an outage are masked.

    ``prior_outage_end`` is the end (``<= window.context_start``) of the latest outage
    affecting this signal that lies before the context. A carry-in observation from before
    it does not carry over: the signal is ``DISCONNECTED`` from ``context_start`` until its
    next observation, exactly as in a run whose context contains that outage (#27).

    Returns:
        A timeline whose intervals exactly cover ``window.context``.
    """
    ctx = window.context
    if ctx is None:
        raise ValueError("build_timeline: the window has an empty context")
    outs = _clip(((r.start, r.end) for r in outages), ctx)
    hist = _clip(((r.start, r.end) for r in history), ctx)
    everything = _prepare(signal.signal, observations, window.end)
    accepted = [
        o
        for o in everything
        if not any(s <= o.ts < e for s, e in outs)
        and not (prior_outage_end is not None and o.ts < prior_outage_end)
    ]
    first_ts = everything[0].ts if everything else None
    prior_gap = (
        prior_outage_end is not None and first_ts is not None and first_ts < prior_outage_end
    )

    pieces: list[ValueInterval | UnknownInterval] = []
    for index, obs in enumerate(accepted):
        next_start = accepted[index + 1].ts if index + 1 < len(accepted) else ctx.end
        cut = next((s for s, e in outs if e > obs.ts), ctx.end)
        hard_end = min(next_start, cut, ctx.end)
        start = max(obs.ts, ctx.start)
        if hard_end <= start:
            continue
        if obs.value is None:
            pieces.append(UnknownInterval(start, hard_end, UnknownReason.UNAVAILABLE))
            continue
        stale_at: TimestampMs | None = None
        if signal.heartbeat_expected and signal.max_age_ms is not None:
            stale_at = obs.evidence + signal.max_age_ms
            for h_start, h_end in hist:
                if h_start <= stale_at < h_end:
                    stale_at = h_end  # no staleness inside history coverage (§6.3)
        value_end = hard_end if stale_at is None else min(max(stale_at, start), hard_end)
        if start < value_end:
            pieces.append(
                ValueInterval(
                    start=start,
                    end=value_end,
                    value=obs.value,
                    provenance=signal.provenance,
                    observed_at=min(obs.evidence, value_end - 1),
                    origin=obs.kind,
                )
            )
        if value_end < hard_end:
            pieces.append(UnknownInterval(value_end, hard_end, UnknownReason.STALE))

    intervals: list[ValueInterval | UnknownInterval] = []

    def fill(g_start: TimestampMs, g_end: TimestampMs) -> None:
        cursor = g_start
        boundaries = sorted({b for span in outs for b in span if g_start < b < g_end})
        for boundary in [*boundaries, g_end]:
            if cursor < boundary:
                inside = any(s <= cursor < e for s, e in outs)
                after_gap = prior_gap or (
                    first_ts is not None and any(e <= cursor and first_ts < e for _, e in outs)
                )
                reason = (
                    UnknownReason.DISCONNECTED if inside or after_gap else UnknownReason.NO_DATA
                )
                intervals.append(UnknownInterval(cursor, boundary, reason))
            cursor = boundary

    cursor = ctx.start
    for piece in pieces:
        if piece.start > cursor:
            fill(cursor, piece.start)
        intervals.append(piece)
        cursor = piece.end
    if cursor < ctx.end:
        fill(cursor, ctx.end)
    return SignalTimeline(signal.signal, ctx, _merge_unknown(intervals))


def _merge_unknown(
    intervals: Sequence[ValueInterval | UnknownInterval],
) -> tuple[ValueInterval | UnknownInterval, ...]:
    """Merge adjacent unknown intervals with the same reason; value intervals stay as is."""
    out: list[ValueInterval | UnknownInterval] = []
    for interval in intervals:
        last = out[-1] if out else None
        if (
            isinstance(interval, UnknownInterval)
            and isinstance(last, UnknownInterval)
            and last.reason is interval.reason
        ):
            out[-1] = UnknownInterval(last.start, interval.end, last.reason)
        else:
            out.append(interval)
    return tuple(out)


def _prior_outage_ends(
    connection_events: Sequence[ConnectionEvent], window: AnalysisWindow
) -> tuple[TimestampMs | None, TimestampMs | None]:
    """End of the latest effective WS and explicit CAN-gateway outage before
    ``window.context_start`` (an outage still open there ends at ``context_start``).

    Needs the events from the latest "down" before the context start onwards (the runner
    supplies them); with only a carry-in per source an outage that ended before the context
    is invisible. Derived gateway outages before the context are not reconstructed.
    """
    first = min((e.ts for e in connection_events), default=None)
    if first is None or first >= window.context_start:
        return None, None
    before = AnalysisWindow(first, first, window.context_start)
    outs = connection_outages(connection_events, before)
    ws, gateway = outs[ConnectionSource.WS], outs[ConnectionSource.CAN_GATEWAY]
    return (ws[-1].end if ws else None), (gateway[-1].end if gateway else None)


def build_stage1(
    observations: Sequence[Observation],
    connection_events: Sequence[ConnectionEvent],
    config: PipelineConfig,
    window: AnalysisWindow,
) -> Stage1Result:
    """Stage 1 including the effective connection outages (needed by stage 2 for the
    ``CONNECTION_LOST`` events). :func:`build_timelines` returns only the timelines."""
    ctx = window.context
    if ctx is None:
        return Stage1Result((), ConnectionOutages())
    outs = connection_outages(connection_events, window)
    ws = outs[ConnectionSource.WS]
    gateway = outs[ConnectionSource.CAN_GATEWAY]
    history = outs[ConnectionSource.HISTORY]
    by_signal: dict[SignalRef, list[Observation]] = defaultdict(list)
    for obs in observations:
        if obs.ts < window.end:
            by_signal[obs.signal].append(obs)

    configs = sorted({c.signal: c for c in config.signals}.values(), key=lambda c: c.signal)
    explicit = _merge([*_spans(ws), *_spans(gateway)])
    prior_ws, prior_gateway = _prior_outage_ends(connection_events, window)
    prior_any = max((t for t in (prior_ws, prior_gateway) if t is not None), default=None)
    built: dict[SignalRef, SignalTimeline] = {}
    heartbeat_gateway = [c for c in configs if c.heartbeat_expected and c.via_can_gateway]
    for cfg in heartbeat_gateway:
        built[cfg.signal] = build_timeline(
            cfg,
            by_signal[cfg.signal],
            _ranges(explicit),
            window,
            history=history,
            prior_outage_end=prior_any,
        )
    derived: tuple[TimeRange, ...] = ()
    if config.derive_gateway_outage and heartbeat_gateway:
        found = derive_gateway_outages([built[c.signal] for c in heartbeat_gateway], history, ctx)
        derived = _ranges(_subtract(_spans(found), _spans(gateway)))
    with_derived = _merge([*explicit, *_spans(derived)])
    for cfg in configs:
        if cfg.signal in built:
            continue
        spans = with_derived if cfg.via_can_gateway else _spans(ws)
        built[cfg.signal] = build_timeline(
            cfg,
            by_signal[cfg.signal],
            _ranges(spans),
            window,
            history=history,
            prior_outage_end=prior_any if cfg.via_can_gateway else prior_ws,
        )
    timelines = tuple(built[c.signal] for c in configs)
    return Stage1Result(timelines, ConnectionOutages(ws, gateway, derived, history))


def build_timelines(
    observations: Sequence[Observation],
    connection_events: Sequence[ConnectionEvent],
    config: PipelineConfig,
    window: AnalysisWindow,
) -> tuple[SignalTimeline, ...]:
    """Build one timeline per configured signal, sorted by ``SignalRef``.

    Configured signals without observations get a single ``NO_DATA`` interval; observations
    of unconfigured signals are ignored.

    Derived gateway outage (ADR-003 §5.3) takes two passes: first the heartbeat signals
    ``via_can_gateway`` (they show their own ``STALE``), then the other gateway signals,
    which are ``DISCONNECTED`` during the derived outage.
    """
    return build_stage1(observations, connection_events, config, window).timelines


_PRECEDENCE = {
    UnknownReason.DISCONNECTED: 0,
    UnknownReason.UNAVAILABLE: 1,
    UnknownReason.STALE: 2,
    UnknownReason.INVALID: 3,
    UnknownReason.IMPLAUSIBLE: 4,
    UnknownReason.NO_DATA: 5,
}


def unknown_union(
    timelines: Sequence[SignalTimeline], rng: TimeRange
) -> tuple[UnknownInterval, ...]:
    """Ranges within ``rng`` where *any* of ``timelines`` is unknown (for combined values).

    Overlapping reasons are resolved by a fixed precedence (disconnected > unavailable >
    stale > invalid > implausible > no_data) so the result is deterministic. Time outside a
    timeline's span counts as ``NO_DATA``.
    """
    bound_set = {rng.start, rng.end}
    for tl in timelines:
        for interval in tl.intervals:
            for b in (interval.start, interval.end):
                if rng.start < b < rng.end:
                    bound_set.add(b)
        for b in (tl.span.start, tl.span.end):
            if rng.start < b < rng.end:
                bound_set.add(b)
    ordered = sorted(bound_set)
    out: list[UnknownInterval] = []
    for start, end in pairwise(ordered):
        reasons: list[UnknownReason] = []
        for tl in timelines:
            found = tl.at(start)
            if found is None:
                reasons.append(UnknownReason.NO_DATA)
            elif isinstance(found, UnknownInterval):
                reasons.append(found.reason)
        if not reasons:
            continue
        reason = min(reasons, key=_PRECEDENCE.__getitem__)
        if out and out[-1].end == start and out[-1].reason is reason:
            out[-1] = UnknownInterval(out[-1].start, end, reason)
        else:
            out.append(UnknownInterval(start, end, reason))
    return tuple(out)
