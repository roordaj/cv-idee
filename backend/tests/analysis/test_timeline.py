"""Stage 1 — timelines (ADR-003 §10.2 T1-T22) plus properties (ADR-002 §6, FR-11)."""

from __future__ import annotations

import random
from collections.abc import Sequence

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from cvidee.analysis.quality import apply_quality, duplicate_events
from cvidee.analysis.timeline import (
    Stage1Result,
    build_stage1,
    build_timeline,
    build_timelines,
    connection_outages,
    unknown_union,
)
from cvidee.analysis.types import (
    ConnectionEvent,
    Observation,
    PipelineConfig,
    QualityEvent,
    SignalRef,
    SignalTimeline,
    TimeRange,
    TimestampMs,
    UnknownInterval,
    ValueInterval,
)
from cvidee.analysis.types import (
    UnknownReason as R,
)

from .scenario import (
    CHANGE,
    CONFIRM,
    FLAME,
    FLOW,
    GW,
    HIST,
    OFF,
    ON,
    POLL,
    RETURN,
    ROOM,
    T0,
    WS,
    C,
    F,
    P,
    S,
    U,
    V,
    assert_timeline,
    cfg,
    config,
    conn,
    run,
    summarize,
    t,
    window,
)

flame = cfg(FLAME)
flow = cfg(FLOW, heartbeat=True)

type EventRow = tuple[str, str, float, float | None, str, int | None]


def events_of(
    cfg_: PipelineConfig,
    observations: Sequence[Observation],
    events: Sequence[ConnectionEvent],
    end_s: float,
) -> list[EventRow]:
    """Quality events as ``(kind, signal-or-source, start_s, end_s, detail, count)``."""
    win = window(end_s)
    stage1 = build_stage1(observations, events, cfg_, win)
    quality = apply_quality(stage1.timelines, cfg_, win, stage1.outages)
    found: list[QualityEvent] = [*quality.events, *duplicate_events(observations, cfg_, win)]
    return sorted(
        (
            e.kind.value,
            e.source.value if e.source is not None else str(e.signal),
            (e.start - T0) / S,
            None if e.end is None else (e.end - T0) / S,
            e.detail,
            e.count,
        )
        for e in found
    )


def ev(
    kind: str, who: str, start: float, end: float | None, detail: str = "", count: int | None = None
) -> EventRow:
    return (kind, who, start, end, detail, count)


def tl_of(result: Stage1Result, signal: SignalRef) -> SignalTimeline:
    return next(x for x in result.timelines if x.signal == signal)


# --------------------------------------------------------------------------------------
# T1-T22
# --------------------------------------------------------------------------------------


def test_t1_long_silence_change_only_is_never_stale() -> None:
    res = run(config(flame), [C(FLAME, 0, OFF)], [], 7200)
    assert_timeline(tl_of(res, FLAME), [V(0, 7200, OFF, 0, CHANGE)])
    assert events_of(config(flame), [C(FLAME, 0, OFF)], [], 7200) == []


def test_t2_heartbeat_with_confirmations() -> None:
    res = run(config(flow), [C(FLOW, 0, 50.0), F(FLOW, 20, 50.0), F(FLOW, 40, 50.0)], [], 60)
    assert_timeline(
        tl_of(res, FLOW),
        [V(0, 20, 50.0, 0, CHANGE), V(20, 40, 50.0, 20, CONFIRM), V(40, 60, 50.0, 40, CONFIRM)],
    )


def test_t3_heartbeat_stale() -> None:
    obs = [C(FLOW, 0, 50.0)]
    assert_timeline(
        tl_of(run(config(flow), obs, [], 100), FLOW),
        [V(0, 30, 50.0, 0, CHANGE), U(30, 100, R.STALE)],
    )
    assert events_of(config(flow), obs, [], 100) == [
        ev("stale", str(FLOW), 30, None, "max_age_s=30")
    ]


def test_t4_recovery_after_stale() -> None:
    obs = [C(FLOW, 0, 50.0), F(FLOW, 50, 50.0)]
    assert_timeline(
        tl_of(run(config(flow), obs, [], 70), FLOW),
        [V(0, 30, 50.0, 0, CHANGE), U(30, 50, R.STALE), V(50, 70, 50.0, 50, CONFIRM)],
    )
    assert events_of(config(flow), obs, [], 70) == [ev("stale", str(FLOW), 30, 50, "max_age_s=30")]


def test_t5_prospective_late_confirmation() -> None:
    base = [C(FLOW, 0, 50.0)]
    run1 = tl_of(run(config(flow), base, [], 20), FLOW)
    assert_timeline(run1, [V(0, 20, 50.0, 0, CHANGE)])
    run2 = tl_of(run(config(flow), base, [], 100), FLOW)
    assert_timeline(run2, [V(0, 30, 50.0, 0, CHANGE), U(30, 100, R.STALE)])
    late = [*base, F(FLOW, 25, 50.0)]
    run3 = tl_of(run(config(flow), late, [], 100), FLOW)
    assert_timeline(
        run3,
        [V(0, 25, 50.0, 0, CHANGE), V(25, 55, 50.0, 25, CONFIRM), U(55, 100, R.STALE)],
    )
    assert events_of(config(flow), late, [], 100) == [
        ev("stale", str(FLOW), 55, None, "max_age_s=30")
    ]


def test_t6_unavailable() -> None:
    obs = [C(FLAME, 0, OFF), C(FLAME, 600, None), C(FLAME, 900, ON), C(FLAME, 1200, OFF)]
    assert_timeline(
        tl_of(run(config(flame), obs, [], 1800), FLAME),
        [
            V(0, 600, OFF),
            U(600, 900, R.UNAVAILABLE),
            V(900, 1200, ON, 900, CHANGE),
            V(1200, 1800, OFF),
        ],
    )
    assert events_of(config(flame), obs, [], 1800) == [ev("unavailable", str(FLAME), 600, 900)]


def test_t7_scenario5_gap_poll_off_then_start() -> None:
    obs = [C(FLAME, 0, OFF), P(FLAME, 2400, OFF), C(FLAME, 2700, ON), C(FLAME, 3000, OFF)]
    evs = [conn(WS, 600, False), conn(WS, 2400, True)]
    assert_timeline(
        tl_of(run(config(flame), obs, evs, 3600), FLAME),
        [
            V(0, 600, OFF),
            U(600, 2400, R.DISCONNECTED),
            V(2400, 2700, OFF, 2400, POLL),
            V(2700, 3000, ON, 2700, CHANGE),
            V(3000, 3600, OFF),
        ],
    )
    assert events_of(config(flame), obs, evs, 3600) == [ev("connection_lost", "ws", 600, 2400)]


def test_t8_reconnect_while_burning() -> None:
    obs = [C(FLAME, 0, OFF), C(FLAME, 300, ON), P(FLAME, 2400, ON), C(FLAME, 2880, OFF)]
    evs = [conn(WS, 600, False), conn(WS, 2400, True)]
    assert_timeline(
        tl_of(run(config(flame), obs, evs, 3600), FLAME),
        [
            V(0, 300, OFF),
            V(300, 600, ON, 300, CHANGE),
            U(600, 2400, R.DISCONNECTED),
            V(2400, 2880, ON, 2400, POLL),
            V(2880, 3600, OFF),
        ],
    )


def test_t9_change_just_before_up_event_is_masked() -> None:
    obs = [C(FLAME, 0, OFF), C(FLAME, 2399, ON), P(FLAME, 2400, ON)]
    evs = [conn(WS, 600, False), conn(WS, 2400, True)]
    assert_timeline(
        tl_of(run(config(flame), obs, evs, 3000), FLAME),
        [V(0, 600, OFF), U(600, 2400, R.DISCONNECTED), V(2400, 3000, ON, 2400, POLL)],
    )


def test_t10_ha_restart() -> None:
    obs = [
        C(FLAME, 0, OFF),
        P(FLAME, 660, None),
        C(FLAME, 690, OFF),
        C(FLAME, 1200, ON),
        C(FLAME, 1500, OFF),
    ]
    evs = [conn(WS, 600, False), conn(WS, 660, True)]
    assert_timeline(
        tl_of(run(config(flame), obs, evs, 1800), FLAME),
        [
            V(0, 600, OFF),
            U(600, 660, R.DISCONNECTED),
            U(660, 690, R.UNAVAILABLE),
            V(690, 1200, OFF, 690, CHANGE),
            V(1200, 1500, ON),
            V(1500, 1800, OFF),
        ],
    )


def test_t11_poll_with_old_last_reported_is_stale_at_once() -> None:
    obs = [C(FLOW, 0, 50.0), F(FLOW, 20, 50.0), P(FLOW, 600, 50.0, lr=300)]
    evs = [conn(WS, 30, False), conn(WS, 600, True)]
    assert_timeline(
        tl_of(run(config(flow), obs, evs, 700), FLOW),
        [
            V(0, 20, 50.0),
            V(20, 30, 50.0, 20, CONFIRM),
            U(30, 600, R.DISCONNECTED),
            U(600, 700, R.STALE),
        ],
    )
    assert events_of(config(flow), obs, evs, 700) == [
        ev("connection_lost", "ws", 30, 600),
        ev("stale", str(FLOW), 600, None, "max_age_s=30"),
    ]


def test_t12_poll_with_fresh_last_reported() -> None:
    obs = [C(FLOW, 0, 50.0), F(FLOW, 20, 50.0), P(FLOW, 600, 50.0, lr=590)]
    evs = [conn(WS, 30, False), conn(WS, 600, True)]
    assert_timeline(
        tl_of(run(config(flow), obs, evs, 700), FLOW),
        [
            V(0, 20, 50.0),
            V(20, 30, 50.0, 20, CONFIRM),
            U(30, 600, R.DISCONNECTED),
            V(600, 620, 50.0, 590, POLL),
            U(620, 700, R.STALE),
        ],
    )
    assert ev("stale", str(FLOW), 620, None, "max_age_s=30") in events_of(
        config(flow), obs, evs, 700
    )


def test_t13_duplicates() -> None:
    obs = [C(FLAME, 0, OFF), C(FLAME, 0, OFF), P(FLAME, 0, OFF)]
    assert_timeline(tl_of(run(config(flame), obs, [], 3600), FLAME), [V(0, 3600, OFF, 0, CHANGE)])
    assert events_of(config(flame), obs, [], 3600) == [ev("duplicate", str(FLAME), 0, 3600, "", 2)]


def test_t14_deviating_confirmation_is_a_poll() -> None:
    obs = [C(FLAME, 0, OFF), F(FLAME, 100, ON)]
    assert_timeline(
        tl_of(run(config(flame), obs, [], 200), FLAME),
        [V(0, 100, OFF), V(100, 200, ON, 100, POLL)],
    )


def test_t15_gateway_entity() -> None:
    fg = cfg(FLAME, gateway=True)
    obs = [C(FLAME, 0, OFF), P(FLAME, 1230, OFF), C(FLAME, 1500, ON)]
    evs = [conn(GW, 600, False), conn(GW, 1200, True)]
    assert_timeline(
        tl_of(run(config(fg), obs, evs, 1800), FLAME),
        [
            V(0, 600, OFF),
            U(600, 1230, R.DISCONNECTED),
            V(1230, 1500, OFF, 1230, POLL),
            V(1500, 1800, ON, 1500, CHANGE),
        ],
    )
    assert events_of(config(fg), obs, evs, 1800) == [
        ev("connection_lost", "can_gateway", 600, 1200)
    ]


def test_t16_gateway_does_not_touch_other_signals() -> None:
    fg, room = cfg(FLAME, gateway=True), cfg(ROOM)
    obs = [C(FLAME, 0, OFF), C(ROOM, 0, 20.5)]
    evs = [conn(GW, 600, False), conn(GW, 1200, True)]
    res = run(config(fg, room), obs, evs, 1800)
    assert_timeline(tl_of(res, ROOM), [V(0, 1800, 20.5, 0, CHANGE)])


T17_OBS = [
    C(FLOW, 0, 50.0),
    F(FLOW, 10, 50.0),
    F(FLOW, 20, 50.0),
    F(FLOW, 30, 50.0),
    F(FLOW, 200, 50.0),
    C(FLAME, 0, OFF),
    P(FLAME, 201, OFF),
]
# ADR-003 T17 uses end=300, but with max_age=30 the F(200) evidence runs out at 230 (the ADR
# table overlooks that); the cases run to end=230 so the table's other values hold.
T17_FLOW = [
    V(0, 10, 50.0),
    V(10, 20, 50.0),
    V(20, 30, 50.0),
    V(30, 60, 50.0, 30, CONFIRM),
    U(60, 200, R.STALE),
    V(200, 230, 50.0, 200, CONFIRM),
]


def test_t17_derived_gateway_outage() -> None:
    cfgs = config(cfg(FLOW, heartbeat=True, gateway=True), cfg(FLAME, gateway=True))
    res = run(cfgs, T17_OBS, [], 230)
    assert_timeline(tl_of(res, FLOW), T17_FLOW)
    assert_timeline(
        tl_of(res, FLAME),
        [V(0, 60, OFF, 0, CHANGE), U(60, 201, R.DISCONNECTED), V(201, 230, OFF, 201, POLL)],
    )
    assert events_of(cfgs, T17_OBS, [], 230) == [
        ev("connection_lost", "can_gateway", 60, 200, "derived"),
        ev("stale", str(FLOW), 60, 200, "max_age_s=30"),
    ]


def test_t17_derivation_can_be_switched_off() -> None:
    cfgs = config(
        cfg(FLOW, heartbeat=True, gateway=True),
        cfg(FLAME, gateway=True),
        derive_gateway_outage=False,
    )
    res = run(cfgs, T17_OBS, [], 230)
    assert_timeline(tl_of(res, FLAME), [V(0, 201, OFF, 0, CHANGE), V(201, 230, OFF, 201, POLL)])


def test_t18_partially_stale_does_not_derive() -> None:
    cfgs = config(
        cfg(FLOW, heartbeat=True, gateway=True),
        cfg(RETURN, heartbeat=True, gateway=True),
        cfg(FLAME, gateway=True),
    )
    obs = [*T17_OBS, C(RETURN, 0, 40.0), *(F(RETURN, s, 40.0) for s in range(10, 230, 10))]
    res = run(cfgs, obs, [], 230)
    assert_timeline(tl_of(res, FLOW), T17_FLOW)
    assert_timeline(tl_of(res, FLAME), [V(0, 201, OFF, 0, CHANGE), V(201, 230, OFF, 201, POLL)])
    assert {e[0] for e in events_of(cfgs, obs, [], 230)} == {"stale"}


def test_t19_gap_filled_from_history() -> None:
    obs = [C(FLAME, 0, OFF), C(FLAME, 1200, ON), C(FLAME, 1500, OFF), P(FLAME, 2400, OFF)]
    evs = [
        conn(WS, 600, False),
        conn(HIST, 600, True),
        conn(HIST, 2400, False),
        conn(WS, 2400, True),
    ]
    assert_timeline(
        tl_of(run(config(flame), obs, evs, 3000), FLAME),
        [
            V(0, 1200, OFF, 0, CHANGE),
            V(1200, 1500, ON, 1200, CHANGE),
            V(1500, 2400, OFF, 1500, CHANGE),
            V(2400, 3000, OFF, 2400, POLL),
        ],
    )
    assert events_of(config(flame), obs, evs, 3000) == []  # Q8


def test_t20_no_staleness_inside_history() -> None:
    obs = [C(FLOW, 0, 50.0), C(FLOW, 600, 52.0), P(FLOW, 1200, 52.0, lr=1195)]
    evs = [conn(WS, 0, False), conn(HIST, 0, True), conn(HIST, 1200, False), conn(WS, 1200, True)]
    assert_timeline(
        tl_of(run(config(flow), obs, evs, 1300), FLOW),
        [
            V(0, 600, 50.0, 0, CHANGE),
            V(600, 1200, 52.0, 600, CHANGE),
            V(1200, 1225, 52.0, 1195, POLL),
            U(1225, 1300, R.STALE),
        ],
    )
    assert events_of(config(flow), obs, evs, 1300) == [
        ev("stale", str(FLOW), 1225, None, "max_age_s=30")
    ]


def test_t21_initial_import_first_state_is_a_poll() -> None:
    obs = [P(FLAME, 0, OFF), C(FLAME, 300, ON), C(FLAME, 600, OFF)]
    evs = [conn(HIST, 0, True)]
    assert_timeline(
        tl_of(run(config(flame), obs, evs, 900), FLAME),
        [V(0, 300, OFF, 0, POLL), V(300, 600, ON, 300, CHANGE), V(600, 900, OFF)],
    )


def test_t22_carry_in_after_gap() -> None:
    obs = [C(FLAME, -100, ON), P(FLAME, 120, ON)]
    evs = [conn(WS, -50, False), conn(WS, 120, True)]
    assert_timeline(
        tl_of(run(config(flame), obs, evs, 300), FLAME),
        [U(0, 120, R.DISCONNECTED), V(120, 300, ON, 120, POLL)],
    )


# --------------------------------------------------------------------------------------
# Further unit tests
# --------------------------------------------------------------------------------------


def test_carry_in_is_clipped_but_keeps_evidence() -> None:
    win = window(300, start_s=100)
    tl = build_timeline(flame, [C(FLAME, 20, ON), C(FLAME, 200, OFF)], [], win)
    assert_timeline(tl, [V(100, 200, ON, 20, CHANGE), V(200, 300, OFF, 200, CHANGE)])


def test_no_data_before_first_observation_and_unconfigured_ignored() -> None:
    res = run(config(flame, flow), [C(FLAME, 100, ON), C(ROOM, 0, 20.0)], [], 300)
    assert [x.signal for x in res.timelines] == sorted([FLAME, FLOW])
    assert_timeline(tl_of(res, FLAME), [U(0, 100, R.NO_DATA), V(100, 300, ON, 100, CHANGE)])
    assert_timeline(tl_of(res, FLOW), [U(0, 300, R.NO_DATA)])


def test_observations_at_or_after_the_horizon_are_ignored() -> None:
    tl = build_timeline(flame, [C(FLAME, 0, OFF), C(FLAME, 300, ON)], [], window(300))
    assert_timeline(tl, [V(0, 300, OFF, 0, CHANGE)])


def test_input_order_is_irrelevant() -> None:
    obs = [C(FLAME, 0, OFF), C(FLAME, 100, ON), F(FLAME, 150, ON), C(FLAME, 200, OFF)]
    shuffled = obs[:]
    random.Random(1).shuffle(shuffled)
    assert build_timeline(flame, obs, [], window(300)) == build_timeline(
        flame, shuffled, [], window(300)
    )


def test_build_timelines_with_empty_context_is_empty() -> None:
    assert build_timelines([], [], config(flame), window(0)) == ()


def test_connection_outages_open_idempotent_and_default_up() -> None:
    win = window(1000)
    assert connection_outages([], win)[WS] == ()
    evs = [conn(WS, 100, False), conn(WS, 150, False), conn(WS, 300, True), conn(WS, 800, False)]
    out = connection_outages(evs, win)
    assert out[WS] == (TimeRange(t(100), t(300)), TimeRange(t(800), t(1000)))
    assert out[GW] == ()


def test_connection_outages_carry_in_and_history_reduction() -> None:
    win = window(1000, start_s=500)
    evs = [conn(WS, 100, False), conn(HIST, 400, True), conn(HIST, 700, False), conn(WS, 900, True)]
    out = connection_outages(evs, win)
    assert out[HIST] == (TimeRange(t(500), t(700)),)
    assert out[WS] == (TimeRange(t(700), t(900)),)


def test_unknown_union_precedence() -> None:
    win = window(100)
    a = build_timeline(flame, [C(FLAME, 50, ON)], [], win)
    b = build_timeline(
        cfg(FLOW), [C(FLOW, 0, 1.0), C(FLOW, 20, None)], [TimeRange(t(60), t(80))], win
    )
    union = unknown_union([a, b], TimeRange(t(0), t(100)))
    assert [(u.start - T0, u.end - T0, u.reason) for u in union] == [
        (0, 20 * S, R.NO_DATA),
        (20 * S, 60 * S, R.UNAVAILABLE),  # unavailable outranks flame's no_data
        (60 * S, 100 * S, R.DISCONNECTED),  # after an outage: until the next observation
    ]


def test_helper_summarize() -> None:
    tl = build_timeline(flame, [C(FLAME, 0, OFF)], [], window(10))
    assert summarize(tl) == [("V", t(0), t(10), OFF, t(0), CHANGE)]


# --------------------------------------------------------------------------------------
# Properties
# --------------------------------------------------------------------------------------

HORIZON = 1200
LOOKBACK = 600

PROP_CFG = config(
    cfg(FLAME, gateway=True),
    cfg(FLOW, heartbeat=True, gateway=True),
    cfg(ROOM, heartbeat=True, max_age_s=60),
    derive_gateway_outage=False,
)
GATEWAY_SIGNALS = (FLAME, FLOW)

type Scenario = tuple[list[Observation], list[ConnectionEvent]]


@st.composite
def scenarios(draw: st.DrawFn) -> Scenario:
    """Random but ingest-consistent input: confirmations repeat the previous value and every
    reconnect is followed by polls (ADR-003 §5.1, §5.4)."""
    ws_times = sorted(draw(st.sets(st.integers(1, HORIZON // 10 - 1), max_size=6)))
    gw_times = sorted(draw(st.sets(st.integers(1, HORIZON // 10 - 1), max_size=6)))
    events = [ConnectionEvent(t(10 * x), WS, up=i % 2 == 1) for i, x in enumerate(ws_times)]
    events += [ConnectionEvent(t(10 * x), GW, up=i % 2 == 1) for i, x in enumerate(gw_times)]
    forced: set[tuple[object, int]] = set()
    for e in events:
        if not e.up:
            continue
        if e.source is WS:
            forced.update((s, e.ts) for s in (FLAME, FLOW, ROOM))
        else:
            forced.update((s, e.ts + 30 * S) for s in GATEWAY_SIGNALS)
    observations: list[Observation] = []
    for signal in (FLAME, FLOW, ROOM):
        stamps = draw(st.sets(st.integers(0, HORIZON // 5 - 1), max_size=25))
        poll_ts = {ts for (s, ts) in forced if s == signal and ts < t(HORIZON)}
        previous: bool | float | str | None = None
        have_previous = False
        for ts in sorted({t(5 * x) for x in stamps} | poll_ts):
            kind = POLL if ts in poll_ts else draw(st.sampled_from([CHANGE, CHANGE, CONFIRM, POLL]))
            if kind is CONFIRM and not have_previous:
                kind = CHANGE
            if kind is CONFIRM:
                value = previous
            elif signal == FLAME:
                value = draw(st.sampled_from([True, False, None]))
            else:
                value = draw(st.sampled_from([20.0, 21.0, 55.0, None]))
            last_reported = None
            if kind is POLL and draw(st.booleans()):
                last_reported = ts - draw(st.integers(0, 90)) * S
            observations.append(Observation(signal, ts, value, kind, last_reported))
            previous, have_previous = value, True
    return observations, events


@settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(scenarios())
def test_unknown_time_is_never_valid_or_off(scenario: Scenario) -> None:
    observations, events = scenario
    res = build_stage1(observations, events, PROP_CFG, window(HORIZON))
    for timeline in res.timelines:
        cfg_ = next(c for c in PROP_CFG.signals if c.signal == timeline.signal)
        outs = [*res.outages.ws, *(res.outages.gateway if cfg_.via_can_gateway else ())]
        own = sorted(
            (o for o in observations if o.signal == timeline.signal), key=lambda o: o.sort_key
        )
        for step in range(0, HORIZON * 2):
            ts = t(step / 2)
            interval = timeline.at(ts)
            assert interval is not None
            if any(r.contains(ts) for r in outs):
                assert isinstance(interval, UnknownInterval)
                assert interval.reason is R.DISCONNECTED
            if not isinstance(interval, ValueInterval):
                continue
            # A known value is backed by an observation of exactly that value, with no outage
            # since, and (heartbeat) within max_age of its evidence.
            earlier = [o for o in own if o.ts <= ts]
            backing = [o for o in earlier if o.value == interval.value]
            assert backing
            last = backing[-1]
            assert not any(r.start <= ts and r.end > last.ts for r in outs)
            if cfg_.heartbeat_expected:
                assert cfg_.max_age_ms is not None
                assert ts < last.evidence_ts + cfg_.max_age_ms
            # The newest non-masked observation must not be "unavailable".
            visible = [o for o in earlier if not any(r.contains(o.ts) for r in outs)]
            assert visible[-1].value is not None


def _norm(timeline: SignalTimeline, lo: TimestampMs, hi: TimestampMs) -> list[tuple[object, ...]]:
    out: list[tuple[object, ...]] = []
    for i in timeline.intervals:
        start, end = max(i.start, lo), min(i.end, hi)
        if start >= end:
            continue
        if isinstance(i, ValueInterval):
            out.append(("V", start, end, i.value, i.observed_at, i.origin))
        elif out and out[-1][0] == "U" and out[-1][3] == i.reason and out[-1][2] == start:
            out[-1] = ("U", out[-1][1], end, i.reason)
        else:
            out.append(("U", start, end, i.reason))
    return out


def _carry_in(
    observations: Sequence[Observation],
    events: Sequence[ConnectionEvent],
    start: TimestampMs,
    end: TimestampMs,
) -> Scenario:
    keep_o = [o for o in observations if start <= o.ts < end]
    for signal in {o.signal for o in observations}:
        before = sorted(
            (o for o in observations if o.signal == signal and o.ts < start),
            key=lambda o: o.sort_key,
        )
        keep_o.extend(before[-1:])
    keep_e = [e for e in events if start <= e.ts < end]
    for source in {e.source for e in events}:
        before_e = sorted(
            (e for e in events if e.source is source and e.ts < start),
            key=lambda e: (e.ts, e.up),
        )
        keep_e.extend(before_e[-1:])
    return keep_o, keep_e


def _clipped(ranges: Sequence[TimeRange], clip: TimeRange) -> list[TimeRange]:
    return [r for x in ranges if (r := x.intersect(clip)) is not None]


@settings(max_examples=120, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(scenarios(), st.integers(LOOKBACK // 10, HORIZON // 10 - 2), st.data())
def test_chunked_equals_whole_for_stages_1_and_2(
    scenario: Scenario, emit_x: int, data: st.DataObject
) -> None:
    observations, events = scenario
    end_x = data.draw(st.integers(emit_x + 1, HORIZON // 10))
    whole_win = window(HORIZON)
    whole = build_stage1(observations, events, PROP_CFG, whole_win)
    whole_q = apply_quality(whole.timelines, PROP_CFG, whole_win, whole.outages)

    emit, end = t(10 * emit_x), t(10 * end_x)
    chunk_win = window(10 * end_x, start_s=10 * emit_x - LOOKBACK, emit_s=10 * emit_x)
    obs_c, ev_c = _carry_in(observations, events, chunk_win.context_start, end)
    chunk = build_stage1(obs_c, ev_c, PROP_CFG, chunk_win)
    chunk_q = apply_quality(chunk.timelines, PROP_CFG, chunk_win, chunk.outages)

    for a, b in zip(whole.timelines, chunk.timelines, strict=True):
        assert _norm(a, emit, end) == _norm(b, emit, end), a.signal
    for a, b in zip(whole_q.timelines, chunk_q.timelines, strict=True):
        assert _norm(a, emit, end) == _norm(b, emit, end), a.signal
    clip = TimeRange(emit, end)
    assert _clipped(whole.outages.ws, clip) == _clipped(chunk.outages.ws, clip)


DERIVE_CFG = config(
    cfg(FLAME),
    cfg(FLOW, heartbeat=True, gateway=True),
    cfg(RETURN, heartbeat=True, gateway=True),
    derive_gateway_outage=True,
)


@settings(max_examples=80, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(scenarios(), st.integers(LOOKBACK // 10, HORIZON // 10 - 2))
def test_derived_gateway_outage_is_chunk_invariant(scenario: Scenario, emit_x: int) -> None:
    observations, events = scenario
    # reuse the ROOM stream as a second heartbeat gateway signal
    observations = [
        Observation(RETURN, o.ts, o.value, o.kind, o.last_reported) if o.signal == ROOM else o
        for o in observations
    ]
    whole = build_stage1(observations, events, DERIVE_CFG, window(HORIZON))
    emit, end = t(10 * emit_x), t(HORIZON)
    chunk_win = window(HORIZON, start_s=10 * emit_x - LOOKBACK, emit_s=10 * emit_x)
    obs_c, ev_c = _carry_in(observations, events, chunk_win.context_start, end)
    chunk = build_stage1(obs_c, ev_c, DERIVE_CFG, chunk_win)
    clip = TimeRange(emit, end)
    assert _clipped(whole.outages.derived_gateway, clip) == _clipped(
        chunk.outages.derived_gateway, clip
    )
    for a, b in zip(whole.timelines, chunk.timelines, strict=True):
        assert _norm(a, emit, end) == _norm(b, emit, end), a.signal
