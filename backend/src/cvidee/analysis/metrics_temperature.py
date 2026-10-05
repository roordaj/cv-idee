"""Stage 5b — temperature metrics (ADR-002 §3.5, FR-15). Pure: no I/O, no wall clock."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from cvidee.analysis.quality import align_pair, pair_tolerance
from cvidee.analysis.types import (
    MINUTE_MS,
    Alignment,
    BurnerCycle,
    CyclePhase,
    DurationMs,
    MetricName,
    MetricValue,
    MetricWindow,
    MetricWindowKind,
    Mode,
    PairSample,
    PipelineConfig,
    Role,
    SignalRef,
    SignalTimeline,
    TimeRange,
)

FLOW = SignalRef(Role.FLOW_TEMPERATURE)
RETURN = SignalRef(Role.RETURN_TEMPERATURE)
FLOW_SETPOINT = SignalRef(Role.FLOW_SETPOINT)


@dataclass(frozen=True, slots=True)
class _Piece:
    start: int
    end: int
    a: float
    b: float


@dataclass(frozen=True, slots=True)
class _Pairs:
    """Aligned samples of two signals within a range, plus time not combinable."""

    pieces: tuple[_Piece, ...]
    misaligned_ms: DurationMs

    @property
    def aligned_ms(self) -> DurationMs:
        return sum(p.end - p.start for p in self.pieces)

    def mean(self, fn: str) -> float | None:
        """Time-weighted mean of ``a`` (``"a"``) or ``a - b`` (``"diff"``)."""
        total = self.aligned_ms
        if total == 0:
            return None
        parts = [((p.a if fn == "a" else p.a - p.b) * (p.end - p.start)) for p in self.pieces]
        return math.fsum(parts) / total


def _find(timelines: Sequence[SignalTimeline], signal: SignalRef) -> SignalTimeline | None:
    return next((t for t in timelines if t.signal == signal), None)


def _heartbeat(config: PipelineConfig, signal: SignalRef) -> bool:
    return any(s.heartbeat_expected for s in config.signals if s.signal == signal)


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _pairs(
    a: SignalTimeline | None,
    b: SignalTimeline | None,
    rng: TimeRange,
    config: PipelineConfig,
    *,
    check_alignment: bool = True,
) -> _Pairs:
    """Sample ``a`` and ``b`` over ``rng`` piecewise-constantly.

    Pieces where either is unknown are dropped. Pieces with ``Alignment.MISALIGNED`` are not
    combined and counted as ``misaligned_ms`` (FR-07). ``check_alignment=False`` skips the
    verdict; used for flow vs. setpoint, where the setpoint is a command, not a measurement.
    """
    if a is None or b is None:
        return _Pairs((), 0)
    cuts = {rng.start, rng.end}
    for timeline in (a, b):
        for interval in timeline.overlapping(rng):
            cuts.update(c for c in (interval.start, interval.end) if rng.start < c < rng.end)
    points = sorted(cuts)
    tolerance = pair_tolerance(config, a.signal, b.signal)
    a_hb, b_hb = _heartbeat(config, a.signal), _heartbeat(config, b.signal)
    pieces: list[_Piece] = []
    misaligned = 0
    for start, end in pairwise(points):
        if check_alignment:
            sample = align_pair(a, b, start, tolerance, a_heartbeat=a_hb, b_heartbeat=b_hb)
        else:
            sample = PairSample(start, a.value_at(start), b.value_at(start), Alignment.ALIGNED)
        if sample.alignment is None:
            continue
        if sample.alignment is Alignment.MISALIGNED:
            misaligned += end - start
            continue
        va, vb = _number(sample.a), _number(sample.b)
        if va is None or vb is None:
            continue
        pieces.append(_Piece(start, end, va, vb))
    return _Pairs(tuple(pieces), misaligned)


def _cycle_range(cycle: BurnerCycle) -> TimeRange | None:
    end = cycle.end if cycle.end is not None else cycle.start + cycle.duration_ms
    return TimeRange(cycle.start, end) if end > cycle.start else None


def _mv(
    name: MetricName,
    window: MetricWindow,
    value: float | None,
    unit: str,
    basis_ms: DurationMs,
    mode: Mode | None = Mode.CH,
) -> MetricValue:
    length = window.range.duration_ms
    basis_ms = min(basis_ms, length)
    return MetricValue(
        name=name,
        window=window,
        value=value,
        unit=unit,
        time_basis_seconds=basis_ms / 1000,
        coverage=min(1.0, basis_ms / length),
        mode=mode,
    )


def _phase_ranges(cycle: BurnerCycle, phase: CyclePhase) -> list[TimeRange]:
    return [TimeRange(p.start, p.end) for p in cycle.phases if p.phase is phase]


def cycle_temperature_metrics(
    cycles: Sequence[BurnerCycle],
    timelines: Sequence[SignalTimeline],
    config: PipelineConfig,
) -> tuple[MetricValue, ...]:
    """Per-cycle metrics (``MetricWindowKind.CYCLE``) for CH cycles:

    * ``OVERSHOOT``: max(flow - flow_setpoint) during the burning part (K).
    * ``OVERSHOOT_AT_STOP``: flow - setpoint over the last minute before flame-off (K).
    * ``HEATING_RATE``: flow rise during ``STARTUP`` (K/min).
    * ``BOILER_DELTA_T_STABLE`` and ``FLOW_MEAN_STABLE``: only during the ``STABLE`` phase
      and only on samples where :func:`cvidee.analysis.quality.align_pair` is not
      ``MISALIGNED`` (time basis = aligned stable time). Startup and afterrun get their own
      ``BOILER_DELTA_T_STARTUP`` / ``BOILER_DELTA_T_AFTERRUN`` and never count as stable.
    * ``PAIR_MISALIGNED_TIME``: quality flag, only emitted when flow/return were misaligned.

    DHW cycles are skipped (FR-09: DHW heating is never reported as high CH flow).
    """
    flow = _find(timelines, FLOW)
    ret = _find(timelines, RETURN)
    setpoint = _find(timelines, FLOW_SETPOINT)
    out: list[MetricValue] = []
    for cycle in cycles:
        rng = _cycle_range(cycle)
        if cycle.mode is not Mode.CH or rng is None:
            continue
        window = MetricWindow(MetricWindowKind.CYCLE, rng, cycle.start)

        burning = [
            TimeRange(p.start, p.end)
            for p in cycle.phases
            if p.phase in (CyclePhase.STARTUP, CyclePhase.STABLE)
        ] or [rng]
        diffs: list[_Piece] = []
        for part in burning:
            diffs.extend(_pairs(flow, setpoint, part, config, check_alignment=False).pieces)
        if diffs:
            peak = max(p.a - p.b for p in diffs)
            out.append(
                _mv(
                    MetricName.OVERSHOOT,
                    window,
                    peak,
                    "K",
                    sum(p.end - p.start for p in diffs),
                )
            )
        if cycle.complete and cycle.end is not None:
            last = TimeRange(max(cycle.start, cycle.end - MINUTE_MS), cycle.end)
            tail = _pairs(flow, setpoint, last, config, check_alignment=False)
            value = tail.mean("diff")
            if value is not None:
                out.append(_mv(MetricName.OVERSHOOT_AT_STOP, window, value, "K", tail.aligned_ms))

        for startup in _phase_ranges(cycle, CyclePhase.STARTUP):
            rate = _heating_rate(flow, startup)
            out.append(_mv(MetricName.HEATING_RATE, window, rate, "K/min", startup.duration_ms))
            pairs = _pairs(flow, ret, startup, config)
            out.append(
                _mv(
                    MetricName.BOILER_DELTA_T_STARTUP,
                    window,
                    pairs.mean("diff"),
                    "K",
                    pairs.aligned_ms,
                )
            )
        for afterrun in _phase_ranges(cycle, CyclePhase.AFTERRUN):
            pairs = _pairs(flow, ret, afterrun, config)
            out.append(
                _mv(
                    MetricName.BOILER_DELTA_T_AFTERRUN,
                    window,
                    pairs.mean("diff"),
                    "K",
                    pairs.aligned_ms,
                )
            )

        aligned_ms = 0
        misaligned_ms = 0
        weighted_flow: list[float] = []
        weighted_dt: list[float] = []
        for stable in _phase_ranges(cycle, CyclePhase.STABLE):
            pairs = _pairs(flow, ret, stable, config)
            aligned_ms += pairs.aligned_ms
            misaligned_ms += pairs.misaligned_ms
            weighted_flow.extend(p.a * (p.end - p.start) for p in pairs.pieces)
            weighted_dt.extend((p.a - p.b) * (p.end - p.start) for p in pairs.pieces)
        if aligned_ms or misaligned_ms:
            out.append(
                _mv(
                    MetricName.FLOW_MEAN_STABLE,
                    window,
                    math.fsum(weighted_flow) / aligned_ms if aligned_ms else None,
                    "°C",
                    aligned_ms,
                )
            )
            out.append(
                _mv(
                    MetricName.BOILER_DELTA_T_STABLE,
                    window,
                    math.fsum(weighted_dt) / aligned_ms if aligned_ms else None,
                    "K",
                    aligned_ms,
                )
            )
        if misaligned_ms:
            out.append(
                _mv(
                    MetricName.PAIR_MISALIGNED_TIME,
                    window,
                    misaligned_ms / 1000,
                    "s",
                    misaligned_ms,
                )
            )
    return tuple(out)


def _heating_rate(flow: SignalTimeline | None, startup: TimeRange) -> float | None:
    if flow is None:
        return None
    first = _number(flow.value_at(startup.start))
    # Startup ends when flow reaches its threshold, so the value at the end instant is the
    # first one of the next phase; fall back to the last startup instant.
    last = _number(flow.value_at(startup.end))
    if last is None:
        last = _number(flow.value_at(startup.end - 1))
    if first is None or last is None:
        return None
    return (last - first) / (startup.duration_ms / MINUTE_MS)


def hourly_temperature_metrics(
    cycles: Sequence[BurnerCycle],
    timelines: Sequence[SignalTimeline],
    buckets: Sequence[TimeRange],
    config: PipelineConfig,
) -> tuple[MetricValue, ...]:
    """Per-bucket stable-phase means (``FLOW_MEAN_STABLE``, ``BOILER_DELTA_T_STABLE``) with
    their time basis, for before/after evaluation and HA export. CH cycles only; a bucket
    without aligned stable time yields no value."""
    flow = _find(timelines, FLOW)
    ret = _find(timelines, RETURN)
    out: list[MetricValue] = []
    for bucket in buckets:
        window = MetricWindow(MetricWindowKind.HOUR, bucket)
        weighted_flow: list[float] = []
        weighted_dt: list[float] = []
        aligned_ms = 0
        for cycle in cycles:
            if cycle.mode is not Mode.CH:
                continue
            for stable in _phase_ranges(cycle, CyclePhase.STABLE):
                part = stable.intersect(bucket)
                if part is None:
                    continue
                pairs = _pairs(flow, ret, part, config)
                aligned_ms += pairs.aligned_ms
                weighted_flow.extend(p.a * (p.end - p.start) for p in pairs.pieces)
                weighted_dt.extend((p.a - p.b) * (p.end - p.start) for p in pairs.pieces)
        if aligned_ms:
            out.append(
                _mv(
                    MetricName.FLOW_MEAN_STABLE,
                    window,
                    math.fsum(weighted_flow) / aligned_ms,
                    "°C",
                    aligned_ms,
                )
            )
            out.append(
                _mv(
                    MetricName.BOILER_DELTA_T_STABLE,
                    window,
                    math.fsum(weighted_dt) / aligned_ms,
                    "K",
                    aligned_ms,
                )
            )
    return tuple(out)
