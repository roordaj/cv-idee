"""Stage 5a — cycle metrics (ADR-002 §3.5, FR-13). Pure: no I/O, no wall clock.

Two tiers: additive grid-bucket metrics inside the pipeline run, and period summaries
(day, rolling 6 h, before/after) computed from stored cycles with :func:`summarize_cycles`.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence

from cvidee.analysis.types import (
    AnalysisWindow,
    BurnerCycle,
    DurationMs,
    EndReason,
    MetricName,
    MetricValue,
    MetricWindow,
    MetricWindowKind,
    Mode,
    ModeSegment,
    ObservedValue,
    PipelineConfig,
    SignalTimeline,
    TimeRange,
    TimestampMs,
    floor_to_grid,
)

type Mask = list[tuple[TimestampMs, TimestampMs]]

_TRUE = frozenset({"on", "true", "1"})


def grid_buckets(window: AnalysisWindow, grid_ms: DurationMs) -> tuple[TimeRange, ...]:
    """Grid buckets intersecting ``[window.emit_from, window.end)``. The last one may be
    partial (clipped to ``window.end``) and is then provisional."""
    buckets: list[TimeRange] = []
    cursor = floor_to_grid(window.emit_from, grid_ms)
    while cursor < window.end:
        end = min(cursor + grid_ms, window.end)
        buckets.append(TimeRange(max(cursor, window.emit_from), end))
        cursor += grid_ms
    return tuple(buckets)


def _clip(mask: Mask, rng: TimeRange) -> Mask:
    out: Mask = []
    for a, b in mask:
        start, end = max(a, rng.start), min(b, rng.end)
        if start < end:
            out.append((start, end))
    return out


def _total(mask: Mask) -> DurationMs:
    return sum(b - a for a, b in mask)


def _intersect(a: Mask, b: Mask) -> Mask:
    out: Mask = []
    i = j = 0
    while i < len(a) and j < len(b):
        start, end = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if start < end:
            out.append((start, end))
        if a[i][1] <= b[j][1]:
            i += 1
        else:
            j += 1
    return out


def _truthy(value: ObservedValue) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in _TRUE
    return bool(value)


def _known_mask(timeline: SignalTimeline | None, *, only_true: bool = False) -> Mask:
    if timeline is None:
        return []
    return [(v.start, v.end) for v in timeline.values if not only_true or _truthy(v.value)]


def _cycle_range(cycle: BurnerCycle) -> TimeRange | None:
    end = cycle.end if cycle.end is not None else cycle.start + cycle.duration_ms
    return TimeRange(cycle.start, end) if end > cycle.start else None


def _metric(
    name: MetricName,
    rng: TimeRange,
    value: float | None,
    unit: str,
    basis_ms: DurationMs,
    mode: Mode | None,
    kind: MetricWindowKind = MetricWindowKind.HOUR,
) -> MetricValue:
    basis_ms = min(basis_ms, rng.duration_ms)
    return MetricValue(
        name=name,
        window=MetricWindow(kind, rng),
        value=value,
        unit=unit,
        time_basis_seconds=basis_ms / 1000,
        coverage=min(1.0, basis_ms / rng.duration_ms),
        mode=mode,
    )


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
    del config
    observed_mask = _intersect(
        _known_mask(flame),
        [(m.start, m.end) for m in modes if m.mode is not Mode.UNKNOWN],
    )
    demand_known = _known_mask(heat_demand)
    demand_true = _known_mask(heat_demand, only_true=True)
    out: list[MetricValue] = []
    for bucket in buckets:
        observed = _total(_clip(observed_mask, bucket))
        out.append(_metric(MetricName.OBSERVED_TIME, bucket, observed / 1000, "s", observed, None))
        if heat_demand is not None:
            known = _total(_clip(demand_known, bucket))
            out.append(
                _metric(
                    MetricName.HEAT_DEMAND_TIME,
                    bucket,
                    _total(_clip(demand_true, bucket)) / 1000 if known else None,
                    "s",
                    known,
                    None,
                )
            )
        for mode in (Mode.CH, Mode.DHW):
            starts = 0
            burn = 0
            for cycle in cycles:
                if cycle.mode is not mode:
                    continue
                rng = _cycle_range(cycle)
                if rng is None:
                    continue
                if cycle.counts_as_start and bucket.contains(cycle.start):
                    starts += 1
                overlap = rng.intersect(bucket)
                if overlap is not None:
                    burn += overlap.duration_ms
            out.append(
                _metric(
                    MetricName.STARTS,
                    bucket,
                    float(starts) if observed else None,
                    "count",
                    observed,
                    mode,
                )
            )
            out.append(
                _metric(
                    MetricName.BURN_TIME,
                    bucket,
                    burn / 1000 if observed else None,
                    "s",
                    observed,
                    mode,
                )
            )
    return tuple(out)


def summarize_cycles(
    cycles: Sequence[BurnerCycle],
    hourly: Sequence[MetricValue],
    period: TimeRange,
    config: PipelineConfig,
    *,
    short_cycle_ms: DurationMs,
    kind: MetricWindowKind = MetricWindowKind.PERIOD,
) -> tuple[MetricValue, ...]:
    """Period metrics (FR-13) from stored cycles and hourly time bases.

    * ``STARTS_PER_HOUR`` = CH starts / observed hours (time basis exposed, FR-13). The
      design's simulation: 6 h window, 30 min unknown → basis 5,5 h.
    * ``BURN_DURATION_MEAN``/``MEDIAN`` over complete CH cycles only.
    * ``SHORT_CYCLES``/``SHORT_CYCLE_SHARE``: complete CH cycles with
      ``end_reason == STOP_DURING_DEMAND`` and duration ``< short_cycle_ms``; the share is
      relative to all complete CH cycles.
    * ``PAUSE_DURATION_MEDIAN``: ``pause_before_ms`` of CH cycles whose predecessor ended
      with ``STOP_DURING_DEMAND`` (standby is never a pause).
    * DHW and incomplete cycles are excluded from CH statistics (still counted separately:
      ``STARTS``/``BURN_TIME`` with ``mode=DHW`` and ``INCOMPLETE_CYCLES``).
    * Day periods are Europe/Amsterdam days converted to UTC by the caller (23/25 h on DST
      days); the time basis makes that explicit.

    The time basis is the sum of the hourly ``OBSERVED_TIME`` buckets lying entirely inside
    ``period`` (a partial bucket at an unaligned edge is not prorated).
    """
    del config
    basis_s = sum(
        m.value or 0.0
        for m in hourly
        if m.name is MetricName.OBSERVED_TIME
        and m.window.kind is MetricWindowKind.HOUR
        and period.start <= m.window.range.start
        and m.window.range.end <= period.end
    )
    basis_ms = round(basis_s * 1000)

    ordered = sorted(cycles, key=lambda c: c.start)
    ch = [c for c in ordered if c.mode is Mode.CH and period.contains(c.start)]
    dhw = [c for c in ordered if c.mode is Mode.DHW and period.contains(c.start)]
    ch_complete = [c for c in ch if c.complete]
    short = [
        c
        for c in ch_complete
        if c.end_reason is EndReason.STOP_DURING_DEMAND and c.duration_ms < short_cycle_ms
    ]
    pauses: list[float] = []
    previous: BurnerCycle | None = None
    for cycle in ordered:
        if (
            period.contains(cycle.start)
            and cycle.mode is Mode.CH
            and previous is not None
            and previous.mode is Mode.CH
            and previous.end_reason is EndReason.STOP_DURING_DEMAND
            and cycle.pause_before_ms is not None
        ):
            pauses.append(cycle.pause_before_ms / 1000)
        previous = cycle

    def burn(selected: Sequence[BurnerCycle]) -> float:
        total = 0
        for c in selected:
            rng = _cycle_range(c)
            overlap = None if rng is None else rng.intersect(period)
            total += 0 if overlap is None else overlap.duration_ms
        return total / 1000

    def m(
        name: MetricName, value: float | None, unit: str, mode: Mode | None = Mode.CH
    ) -> MetricValue:
        return _metric(name, period, value, unit, basis_ms, mode, kind)

    durations = [c.duration_ms / 1000 for c in ch_complete]
    starts = [c for c in ch if c.counts_as_start]
    has_basis = basis_ms > 0
    return (
        m(MetricName.STARTS, float(len(starts)) if has_basis else None, "count"),
        m(
            MetricName.STARTS_PER_HOUR,
            len(starts) / (basis_ms / 3_600_000) if has_basis else None,
            "1/h",
        ),
        m(MetricName.BURN_TIME, burn(ch), "s"),
        m(MetricName.BURN_DURATION_MEAN, statistics.fmean(durations) if durations else None, "s"),
        m(
            MetricName.BURN_DURATION_MEDIAN,
            statistics.median(durations) if durations else None,
            "s",
        ),
        m(MetricName.SHORT_CYCLES, float(len(short)) if ch_complete else None, "count"),
        m(
            MetricName.SHORT_CYCLE_SHARE,
            len(short) / len(ch_complete) if ch_complete else None,
            "ratio",
        ),
        m(MetricName.PAUSE_DURATION_MEDIAN, statistics.median(pauses) if pauses else None, "s"),
        m(MetricName.INCOMPLETE_CYCLES, float(len([c for c in ch if not c.complete])), "count"),
        m(MetricName.STARTS, float(len([c for c in dhw if c.counts_as_start])), "count", Mode.DHW),
        m(MetricName.BURN_TIME, burn(dhw), "s", Mode.DHW),
    )
