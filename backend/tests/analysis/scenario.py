"""Compact notation for ADR-003 §10 test cases (times in seconds from ``T0``)."""

from __future__ import annotations

from collections.abc import Sequence

from cvidee.analysis.timeline import Stage1Result, build_stage1
from cvidee.analysis.types import (
    HOUR_MS,
    AnalysisWindow,
    ConnectionEvent,
    ConnectionSource,
    Observation,
    ObservationKind,
    ObservedValue,
    PipelineConfig,
    Provenance,
    Role,
    Scope,
    ScopeKind,
    SignalConfig,
    SignalRef,
    SignalTimeline,
    TimestampMs,
    UnknownInterval,
    UnknownReason,
    ValueInterval,
    ValueKind,
)

T0: TimestampMs = 1_790_000_000_000 - (1_790_000_000_000 % HOUR_MS)
S = 1_000

FLAME = SignalRef(Role.FLAME)
FLOW = SignalRef(Role.FLOW_TEMPERATURE)
RETURN = SignalRef(Role.RETURN_TEMPERATURE)
ROOM = SignalRef(Role.ROOM_TEMPERATURE, Scope(ScopeKind.ROOM, "woonkamer"))
GAS = SignalRef(Role.GAS_CUMULATIVE)

CHANGE, CONFIRM, POLL = ObservationKind.CHANGE, ObservationKind.CONFIRM, ObservationKind.POLL
WS, GW, HIST = ConnectionSource.WS, ConnectionSource.CAN_GATEWAY, ConnectionSource.HISTORY
OFF, ON = False, True


def t(seconds: float) -> TimestampMs:
    return T0 + round(seconds * S)


def cfg(
    signal: SignalRef,
    *,
    heartbeat: bool = False,
    max_age_s: int = 30,
    gateway: bool = False,
    cumulative: bool = False,
    lo: float | None = None,
    hi: float | None = None,
) -> SignalConfig:
    return SignalConfig(
        signal,
        Provenance(ValueKind.MEASURED, f"sensor.{signal.role}"),
        heartbeat_expected=heartbeat,
        max_age_ms=max_age_s * S if heartbeat else None,
        via_can_gateway=gateway,
        cumulative=cumulative,
        plausible_min=lo,
        plausible_max=hi,
    )


def config(*signals: SignalConfig, **kw: object) -> PipelineConfig:
    return PipelineConfig(signals=tuple(signals), **kw)  # type: ignore[arg-type]


def window(end_s: float, start_s: float = 0, emit_s: float | None = None) -> AnalysisWindow:
    return AnalysisWindow(t(start_s), t(start_s if emit_s is None else emit_s), t(end_s))


def obs(
    signal: SignalRef,
    kind: ObservationKind,
    ts_s: float,
    value: ObservedValue | None,
    lr: float | None = None,
) -> Observation:
    return Observation(signal, t(ts_s), value, kind, None if lr is None else t(lr))


def C(signal: SignalRef, ts: float, v: ObservedValue | None) -> Observation:  # noqa: N802
    return obs(signal, CHANGE, ts, v)


def F(signal: SignalRef, ts: float, v: ObservedValue | None) -> Observation:  # noqa: N802
    return obs(signal, CONFIRM, ts, v)


def P(  # noqa: N802
    signal: SignalRef, ts: float, v: ObservedValue | None, lr: float | None = None
) -> Observation:
    return obs(signal, POLL, ts, v, lr)


def conn(source: ConnectionSource, ts: float, up: bool) -> ConnectionEvent:
    return ConnectionEvent(t(ts), source, up)


def run(
    config_: PipelineConfig,
    observations: Sequence[Observation],
    events: Sequence[ConnectionEvent],
    end_s: float,
    start_s: float = 0,
) -> Stage1Result:
    return build_stage1(observations, events, config_, window(end_s, start_s))


def V(  # noqa: N802
    start: float,
    end: float,
    value: ObservedValue,
    observed_at: float | None = None,
    origin: ObservationKind | None = None,
) -> tuple[object, ...]:
    return ("V", t(start), t(end), value, None if observed_at is None else t(observed_at), origin)


def U(start: float, end: float, reason: UnknownReason) -> tuple[object, ...]:  # noqa: N802
    return ("U", t(start), t(end), reason)


def summarize(timeline: SignalTimeline, *, detail: bool = True) -> list[tuple[object, ...]]:
    """Comparable form; ``detail=False`` drops ``observed_at``/``origin`` of value intervals."""
    out: list[tuple[object, ...]] = []
    for i in timeline.intervals:
        if isinstance(i, ValueInterval):
            out.append(("V", i.start, i.end, i.value, i.observed_at, i.origin))
        else:
            assert isinstance(i, UnknownInterval)
            out.append(("U", i.start, i.end, i.reason))
    return out


def assert_timeline(timeline: SignalTimeline, expected: Sequence[tuple[object, ...]]) -> None:
    """Assert the intervals; a ``None`` in an expected ``V`` means 'do not care'."""
    actual = summarize(timeline)
    relaxed: list[tuple[object, ...]] = []
    for index, e in enumerate(expected):
        a = actual[index] if index < len(actual) else ()
        if len(a) == len(e):
            relaxed.append(tuple(y if x is None else x for x, y in zip(e, a, strict=True)))
        else:
            relaxed.append(e)
    assert actual == relaxed, f"{timeline.signal}"
