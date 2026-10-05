"""Deterministic synthetic data generator for the MVP acceptance scenarios (issue #15).

The generator first *plans* the physical story (heat-demand blocks, burner periods, DHW draws,
special periods) with a seeded :class:`random.Random`, then *samples* it every
:data:`STEP_MS` into :class:`~cvidee.analysis.types.Observation` and
:class:`~cvidee.analysis.types.ConnectionEvent` streams the way the ingest layer would deliver
them: ``CHANGE`` on a new value, optional ``CONFIRM`` heartbeats, ``POLL`` for the first state and
after reconnects. The planned burner periods are returned as ground truth
(:attr:`GeneratedData.truth_cycles`) so tests can compare stage output against what really
happened.

Same spec (including ``seed``) gives identical output. Nothing here talks to a store or HA.

Synthetic status codes (the real Calenta Ace mapping is still provisional, see #5): ``"0"``
standby, ``"1"`` central heating, ``"2"`` DHW, ``"3"`` afterrun; see :data:`MODE_MAPPING`.
"""

from __future__ import annotations

import math
import random
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from cvidee.analysis.types import (
    HOUR_MS,
    AnalysisWindow,
    ConnectionEvent,
    ConnectionSource,
    EndReason,
    Mode,
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
    TimestampMs,
    ValueKind,
)

STEP_MS = 10_000
"""Sampling step of the simulation."""
START_MS: TimestampMs = int(datetime(2026, 1, 12, tzinfo=UTC).timestamp() * 1000)
"""Default start: Monday 2026-01-12 00:00 UTC (hour-aligned, so grid buckets are whole hours)."""
AFTERRUN_MS = 180_000
LOOKAHEAD_STEPS = 6
"""Steps covered by the 60 s end-reason look-ahead of the cycle stage."""

MODE_MAPPING: tuple[tuple[str, Mode], ...] = (
    ("0", Mode.STANDBY),
    ("1", Mode.CH),
    ("2", Mode.DHW),
    ("3", Mode.AFTERRUN),
)

LIVING_ROOM = SignalRef(Role.ROOM_TEMPERATURE, Scope(ScopeKind.ROOM, "woonkamer"))
BEDROOM = SignalRef(Role.ROOM_TEMPERATURE, Scope(ScopeKind.ROOM, "slaapkamer"))
FLAME = SignalRef(Role.FLAME)
OPERATING_MODE = SignalRef(Role.OPERATING_MODE)
HEAT_DEMAND = SignalRef(Role.HEAT_DEMAND)
FLOW_SETPOINT = SignalRef(Role.FLOW_SETPOINT)
FLOW = SignalRef(Role.FLOW_TEMPERATURE)
RETURN = SignalRef(Role.RETURN_TEMPERATURE)
MODULATION = SignalRef(Role.MODULATION)
OUTDOOR = SignalRef(Role.OUTDOOR_TEMPERATURE, Scope(ScopeKind.OUTDOOR))
PUMP = SignalRef(Role.PUMP_STATE)
GAS = SignalRef(Role.GAS_CUMULATIVE)

ALL_SIGNALS: tuple[SignalRef, ...] = (
    FLAME,
    OPERATING_MODE,
    HEAT_DEMAND,
    FLOW_SETPOINT,
    FLOW,
    RETURN,
    MODULATION,
    PUMP,
    GAS,
    LIVING_ROOM,
    BEDROOM,
    OUTDOOR,
)
GATEWAY_SIGNALS = frozenset(ALL_SIGNALS) - {LIVING_ROOM, BEDROOM, OUTDOOR}
"""Signals that reach HA through the CAN gateway (lost during a ``can`` data gap)."""
_SLOW_SIGNALS = frozenset({LIVING_ROOM, BEDROOM, OUTDOOR, GAS})
"""Reported once a minute instead of every step."""


def hours(h: float) -> int:
    """Hours (float) to milliseconds."""
    return round(h * HOUR_MS)


Range = tuple[float, float]
"""Inclusive ``(low, high)`` in seconds, drawn uniformly in whole seconds."""


@dataclass(frozen=True, slots=True)
class Behaviour:
    """One operating regime of the boiler and the house.

    A *demand block* is an uninterrupted stretch of heat demand. Inside it the burner runs
    ``burn_s`` and pauses ``pause_s`` alternately; a burn that reaches the end of the block
    ends *with* the demand (``demand_ended``), every earlier burn stops *during* demand.
    Between blocks the house is idle for ``idle_s``.
    """

    burn_s: Range = (900, 1800)
    pause_s: Range = (480, 720)
    block_s: Range = (2400, 5400)
    idle_s: Range = (1800, 5400)
    flow_setpoint_c: float = 45.0
    modulation_pct: float = 35.0
    room_c: float = 20.5
    """Living-room temperature the regime settles at (comfort)."""
    bedroom_offset_c: float = -2.0


@dataclass(frozen=True, slots=True)
class Period:
    """Regime ``behaviour`` from ``start_h`` to ``end_h`` (hours from the scenario start)."""

    start_h: float
    end_h: float
    behaviour: Behaviour
    special: str | None = None
    """Marks a special period (e.g. ``"opstookprotocol"``), reported in the output."""


@dataclass(frozen=True, slots=True)
class DhwDraw:
    start_h: float
    duration_s: int


@dataclass(frozen=True, slots=True)
class DataGap:
    """No data from ``start_h`` to ``end_h``. ``ws``: our HA connection is down (all signals);
    ``can``: HA lost the boiler (only gateway signals). ``reconnect_poll``: the first state
    afterwards arrives as a ``POLL`` (as after a real reconnect) instead of a ``CHANGE``."""

    start_h: float
    end_h: float
    kind: Literal["ws", "can"] = "can"
    reconnect_poll: bool = True


@dataclass(frozen=True, slots=True)
class StalePeriod:
    """Signal ``signal`` stops reporting (also no heartbeat) between the two instants."""

    signal: SignalRef
    start_h: float
    end_h: float


@dataclass(frozen=True, slots=True)
class WeatherShift:
    at_h: float
    delta_c: float


@dataclass(frozen=True, slots=True)
class ChangeMarker:
    """Metadata only: a settings change entered in the change log at ``at_h`` (FR-29)."""

    at_h: float
    parameter: str
    old: str
    new: str


@dataclass(frozen=True, slots=True)
class GeneratorSpec:
    seed: int = 1
    start_ms: TimestampMs = START_MS
    hours: float = 72
    periods: tuple[Period, ...] = ()
    """Regimes; empty means one default :class:`Behaviour` for the whole span."""
    dhw_per_day: int = 0
    dhw_duration_s: Range = (240, 600)
    dhw_draws: tuple[DhwDraw, ...] = ()
    """Explicit draws, added to the random ``dhw_per_day`` draws."""
    data_gaps: tuple[DataGap, ...] = ()
    stale: tuple[StalePeriod, ...] = ()
    counter_resets_h: tuple[float, ...] = ()
    duplicate_rate: float = 0.0
    """Probability that an observation is delivered twice (exact duplicate)."""
    heartbeat_s: int | None = None
    """Report unchanged values every ``heartbeat_s`` (``CONFIRM``) and configure staleness
    (``max_age`` = 3 x heartbeat)."""
    include: frozenset[SignalRef] | None = None
    """Restrict to these signals (``None`` = all, minus the gas counter unless ``gas_counter``)."""
    gas_counter: bool = False
    outdoor_base_c: float = 5.0
    weather_shift: WeatherShift | None = None
    changes: tuple[ChangeMarker, ...] = ()


@dataclass(frozen=True, slots=True)
class TruthCycle:
    """A burner period as it really happened (independent of what was observed)."""

    start: TimestampMs
    end: TimestampMs
    mode: Mode
    end_reason: EndReason
    touches_gap: bool


@dataclass(frozen=True, slots=True)
class GeneratedData:
    observations: tuple[Observation, ...]
    connection_events: tuple[ConnectionEvent, ...]
    config: PipelineConfig
    window: AnalysisWindow
    start_ms: TimestampMs
    end_ms: TimestampMs
    signals: tuple[SignalRef, ...]
    truth_cycles: tuple[TruthCycle, ...]
    gaps: tuple[tuple[TimestampMs, TimestampMs, str], ...]
    special_periods: tuple[tuple[TimestampMs, TimestampMs, str], ...]
    changes: tuple[tuple[TimestampMs, str, str, str], ...]

    def at(self, h: float) -> TimestampMs:
        return self.start_ms + hours(h)


# --------------------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------------------

_Span = tuple[int, int]


def _draw(rng: random.Random, r: Range) -> int:
    return rng.randint(round(r[0]), round(r[1])) * 1000


def _subtract(spans: list[_Span], cuts: list[_Span]) -> list[_Span]:
    out: list[_Span] = []
    for s, e in spans:
        pieces = [(s, e)]
        for cs, ce in cuts:
            nxt: list[_Span] = []
            for ps, pe in pieces:
                if ce <= ps or cs >= pe:
                    nxt.append((ps, pe))
                    continue
                if cs > ps:
                    nxt.append((ps, cs))
                if ce < pe:
                    nxt.append((ce, pe))
            pieces = nxt
        out.extend(p for p in pieces if p[1] > p[0])
    return out


@dataclass(frozen=True, slots=True)
class _Spans:
    """Sorted, disjoint spans with a fast membership test."""

    spans: tuple[_Span, ...]
    starts: tuple[int, ...]

    @classmethod
    def of(cls, spans: Sequence[_Span]) -> _Spans:
        ordered = tuple(sorted(spans))
        return cls(ordered, tuple(s for s, _ in ordered))

    def __contains__(self, off: int) -> bool:
        k = bisect_right(self.starts, off) - 1
        return k >= 0 and self.spans[k][0] <= off < self.spans[k][1]


@dataclass(frozen=True, slots=True)
class _Plan:
    burns: _Spans
    demand: _Spans
    dhw: _Spans


def _plan(spec: GeneratorSpec, rng: random.Random, periods: Sequence[Period]) -> _Plan:
    total_ms = hours(spec.hours)
    burns: list[_Span] = []
    demand: list[_Span] = []
    for period in periods:
        b = period.behaviour
        p_end = min(hours(period.end_h), total_ms)
        t = hours(period.start_h)
        if t == 0:
            t += _draw(rng, b.idle_s)  # start idle: no burner running when the data begins
        while t < p_end:
            block_end = min(t + _draw(rng, b.block_s), p_end)
            demand.append((t, block_end))
            c = t
            while c < block_end:
                end = min(c + _draw(rng, b.burn_s), block_end)
                burns.append((c, end))
                c = end + _draw(rng, b.pause_s)
            t = block_end + _draw(rng, b.idle_s)

    draws: list[_Span] = []
    for day in range(math.ceil(spec.hours / 24)):
        for _ in range(spec.dhw_per_day):
            start = hours(day * 24 + rng.uniform(6, 22)) // STEP_MS * STEP_MS
            draws.append((start, start + _draw(rng, spec.dhw_duration_s)))
    for draw in spec.dhw_draws:
        start = hours(draw.start_h) // STEP_MS * STEP_MS
        draws.append((start, start + draw.duration_s * 1000))
    kept: list[_Span] = []
    for s, e in sorted(draws):  # drop overlapping draws; leave room for the afterrun
        if e < total_ms and (not kept or s >= kept[-1][1] + AFTERRUN_MS + STEP_MS):
            kept.append((s, e))
    cuts = [(s - STEP_MS, e + AFTERRUN_MS) for s, e in kept]
    burns = [x for x in burns if all(x[1] <= c[0] or x[0] >= c[1] for c in cuts)]
    demand = _subtract(demand, cuts)
    return _Plan(_Spans.of(burns), _Spans.of(demand), _Spans.of(kept))


# --------------------------------------------------------------------------------------
# Sampling
# --------------------------------------------------------------------------------------


def _quantise(value: float, step: float) -> float:
    return round(round(value / step) * step, 3)


def generate(spec: GeneratorSpec) -> GeneratedData:
    """Build the observation and connection-event streams for ``spec`` (deterministic)."""
    rng = random.Random(spec.seed)
    total_ms = hours(spec.hours)
    start = spec.start_ms
    periods = spec.periods or (Period(0, spec.hours, Behaviour()),)
    plan = _plan(spec, rng, periods)
    period_starts = [hours(p.start_h) for p in periods]
    afterrun = _Spans.of([(e, e + AFTERRUN_MS) for _, e in plan.dhw.spans])

    gaps = [(hours(g.start_h), hours(g.end_h), g) for g in spec.data_gaps]
    stale = [(s.signal, hours(s.start_h), hours(s.end_h)) for s in spec.stale]
    resets = sorted(hours(h) for h in spec.counter_resets_h)
    signals = tuple(
        s
        for s in ALL_SIGNALS
        if (s in spec.include if spec.include is not None else (s != GAS or spec.gas_counter))
    )

    last_value: dict[SignalRef, ObservedValue] = {}
    last_emit: dict[SignalRef, int] = {}
    recovering: set[SignalRef] = set()
    obs: list[Observation] = []

    def emit(sig: SignalRef, ts: int, value: ObservedValue, kind: ObservationKind) -> None:
        obs.append(Observation(sig, ts, value, kind, last_reported=ts))
        last_value[sig] = value
        last_emit[sig] = ts

    first = periods[0].behaviour
    flow_t, return_t = 30.0, 27.0
    room_l, room_b = first.room_c, first.room_c + first.bedroom_offset_c
    heat, gas_total, gas_offset, reset_idx = 0.0, 0.0, 0.0, 0

    for i in range(total_ms // STEP_MS):
        off = i * STEP_MS
        ts = start + off
        flame_dhw = off in plan.dhw
        flame_ch = off in plan.burns
        flame = flame_ch or flame_dhw
        demand = off in plan.demand
        beh = periods[max(bisect_right(period_starts, off) - 1, 0)].behaviour

        if flame_dhw:
            mode_code, setpoint, target = "2", 70.0, 72.0
        elif demand:
            mode_code, setpoint, target = "1", beh.flow_setpoint_c, beh.flow_setpoint_c + 1.5
        else:
            mode_code, setpoint, target = ("3" if off in afterrun else "0"), 10.0, 30.0
        if not flame and not demand:
            target = 28.0 + 0.5 * (room_l - 20.0)
        flow_t += (target - flow_t) * (0.12 if flame else 0.02)
        return_t += ((flow_t - (10.0 if flame else 2.0)) - return_t) * 0.1
        modulation = 60.0 if flame_dhw else (beh.modulation_pct if flame_ch else 0.0)
        heat += ((1.0 if flame_ch else 0.0) - heat) * 0.01
        hod = (off / HOUR_MS) % 24
        wobble = 0.25 * math.sin(2 * math.pi * (hod - 16) / 24)
        room_l += ((beh.room_c + wobble + 0.4 * heat) - room_l) * 0.01
        room_b += ((beh.room_c + beh.bedroom_offset_c + wobble + 0.3 * heat) - room_b) * 0.01
        outdoor = spec.outdoor_base_c + 3.0 * math.sin(2 * math.pi * (hod - 16) / 24)
        if spec.weather_shift is not None and off >= hours(spec.weather_shift.at_h):
            outdoor += spec.weather_shift.delta_c
        if flame:
            gas_total += STEP_MS / 1000 * modulation / 100 * 0.0007
        while reset_idx < len(resets) and off >= resets[reset_idx]:
            gas_offset = gas_total
            reset_idx += 1

        values: dict[SignalRef, ObservedValue] = {
            FLAME: flame,
            OPERATING_MODE: mode_code,
            HEAT_DEMAND: demand,
            FLOW_SETPOINT: setpoint,
            FLOW: _quantise(flow_t, 0.5),
            RETURN: _quantise(return_t, 0.5),
            MODULATION: float(round(modulation)),
            PUMP: bool(flame or demand or off in afterrun),
            LIVING_ROOM: _quantise(room_l, 0.1),
            BEDROOM: _quantise(room_b, 0.1),
            OUTDOOR: _quantise(outdoor, 0.1),
            GAS: round(gas_total - gas_offset, 3),
        }
        for sig in signals:
            if sig in _SLOW_SIGNALS and i % 6 != 0:
                continue
            gap = next(
                (
                    g
                    for a, b, g in gaps
                    if a <= off < b and (g.kind == "ws" or sig in GATEWAY_SIGNALS)
                ),
                None,
            )
            if gap is not None:
                if gap.reconnect_poll:
                    recovering.add(sig)
                continue
            if any(s == sig and a <= off < b for s, a, b in stale):
                continue
            value = values[sig]
            if sig not in last_value or sig in recovering:
                recovering.discard(sig)
                emit(sig, ts, value, ObservationKind.POLL)
            elif value != last_value[sig]:
                emit(sig, ts, value, ObservationKind.CHANGE)
            elif spec.heartbeat_s and ts - last_emit[sig] >= spec.heartbeat_s * 1000:
                emit(sig, ts, value, ObservationKind.CONFIRM)

    duplicates = [o for o in obs if rng.random() < spec.duplicate_rate]
    obs = sorted([*obs, *duplicates], key=lambda o: o.sort_key)

    events = [
        ConnectionEvent(start, ConnectionSource.WS, True),
        ConnectionEvent(start, ConnectionSource.CAN_GATEWAY, True),
    ]
    for a, b, g in gaps:
        src = ConnectionSource.WS if g.kind == "ws" else ConnectionSource.CAN_GATEWAY
        events += [ConnectionEvent(start + a, src, False), ConnectionEvent(start + b, src, True)]
    events.sort(key=lambda e: (e.ts, e.source.value, e.up))

    end = start + total_ms
    return GeneratedData(
        observations=tuple(obs),
        connection_events=tuple(events),
        config=_config(spec, signals),
        window=AnalysisWindow(context_start=start, emit_from=start, end=end),
        start_ms=start,
        end_ms=end,
        signals=signals,
        truth_cycles=_truth(plan, gaps, total_ms, start),
        gaps=tuple((start + a, start + b, g.kind) for a, b, g in gaps),
        special_periods=tuple(
            (start + hours(p.start_h), start + hours(p.end_h), p.special)
            for p in periods
            if p.special is not None
        ),
        changes=tuple((start + hours(c.at_h), c.parameter, c.old, c.new) for c in spec.changes),
    )


def _truth(
    plan: _Plan,
    gaps: Sequence[tuple[int, int, DataGap]],
    total_ms: int,
    start: TimestampMs,
) -> tuple[TruthCycle, ...]:
    cycles: list[TruthCycle] = []
    dhw = set(plan.dhw.spans)
    for s, e in sorted([*plan.burns.spans, *plan.dhw.spans]):
        if e >= total_ms:
            continue  # still burning at the horizon: an open cycle, no truth
        if (s, e) in dhw:
            mode, reason = Mode.DHW, EndReason.DHW_ENDED
        else:
            mode = Mode.CH
            held = all((e + k * STEP_MS) in plan.demand for k in range(LOOKAHEAD_STEPS))
            reason = EndReason.STOP_DURING_DEMAND if held else EndReason.DEMAND_ENDED
        touches = any(s < g_end and e >= g_start for g_start, g_end, _ in gaps)
        cycles.append(TruthCycle(start + s, start + e, mode, reason, touches))
    return tuple(cycles)


def _config(spec: GeneratorSpec, signals: Sequence[SignalRef]) -> PipelineConfig:
    configs: list[SignalConfig] = []
    for sig in signals:
        heartbeat = spec.heartbeat_s is not None and sig != OPERATING_MODE
        configs.append(
            SignalConfig(
                sig,
                Provenance(ValueKind.MEASURED, f"sensor.synthetic_{sig.role}"),
                heartbeat_expected=heartbeat,
                max_age_ms=spec.heartbeat_s * 3000 if heartbeat and spec.heartbeat_s else None,
                via_can_gateway=sig in GATEWAY_SIGNALS,
                cumulative=sig == GAS,
            )
        )
    return PipelineConfig(signals=tuple(configs), mode_mapping=MODE_MAPPING)
