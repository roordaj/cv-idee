"""Stage 2 — data quality (ADR-003 §10.4 A1-A8, §10.5 Q1-Q8) and helpers."""

from __future__ import annotations

from itertools import pairwise

from hypothesis import given
from hypothesis import strategies as st

from cvidee.analysis.quality import (
    DEFAULT_PLAUSIBILITY,
    align_pair,
    apply_quality,
    counter_consumption,
    counter_segments,
    coverage_by_signal,
    detect_counter_resets,
    misaligned_events,
    pair_tolerance,
    update_interval_median_ms,
)
from cvidee.analysis.types import (
    HOUR_MS,
    Alignment,
    ConnectionSource,
    ObservationKind,
    PairTolerance,
    Provenance,
    QualityEventKind,
    Role,
    Scope,
    ScopeKind,
    SignalRef,
    SignalTimeline,
    TimeRange,
    UnknownInterval,
    ValueInterval,
    ValueKind,
)
from cvidee.analysis.types import (
    UnknownReason as R,
)

from .scenario import (
    CHANGE,
    CONFIRM,
    FLAME,
    FLOW,
    GAS,
    GW,
    OFF,
    ON,
    RETURN,
    ROOM,
    T0,
    WS,
    C,
    F,
    P,
    S,
    cfg,
    config,
    conn,
    run,
    t,
    window,
)
from .test_timeline import ev, events_of

TOL = 30 * S
PROV = Provenance(ValueKind.MEASURED, "sensor.x")
SETPOINT = SignalRef(Role.FLOW_SETPOINT)

type Piece = tuple[float, float, float, ObservationKind]


def hand(
    signal: SignalRef, pieces: list[Piece], span: tuple[float, float] = (0, 400)
) -> SignalTimeline:
    """Timeline with value intervals ``(start, end, observed_at, origin)`` (values 1.0)."""
    intervals: list[ValueInterval | UnknownInterval] = []
    cursor = span[0]
    for start, end, observed, origin in pieces:
        if start > cursor:
            intervals.append(UnknownInterval(t(cursor), t(start), R.NO_DATA))
        intervals.append(ValueInterval(t(start), t(end), 1.0, PROV, t(observed), origin))
        cursor = end
    if cursor < span[1]:
        intervals.append(UnknownInterval(t(cursor), t(span[1]), R.STALE))
    return SignalTimeline(signal, TimeRange(t(span[0]), t(span[1])), tuple(intervals))


def sample(a: SignalTimeline, b: SignalTimeline, ts: float, *, a_hb: bool, b_hb: bool):  # type: ignore[no-untyped-def]
    return align_pair(a, b, t(ts), TOL, a_heartbeat=a_hb, b_heartbeat=b_hb).alignment


# --------------------------------------------------------------------------------------
# A1-A8
# --------------------------------------------------------------------------------------


def test_a1_heartbeat_pair_within_tolerance() -> None:
    a = hand(FLOW, [(100, 200, 100, CHANGE)])
    b = hand(RETURN, [(110, 200, 110, CHANGE)])
    assert sample(a, b, 115, a_hb=True, b_hb=True) is Alignment.ALIGNED


def test_a2_heartbeat_pair_beyond_tolerance() -> None:
    a = hand(FLOW, [(100, 200, 100, CHANGE)])
    b = hand(RETURN, [(140, 200, 140, CHANGE)])
    assert sample(a, b, 145, a_hb=True, b_hb=True) is Alignment.MISALIGNED


def test_a3_change_only_partner_assumed_unchanged() -> None:
    a = hand(FLOW, [(10, 20, 10, CHANGE), (20, 100, 20, CONFIRM)])
    b = hand(RETURN, [(0, 400, 0, CHANGE)])
    assert sample(a, b, 25, a_hb=True, b_hb=False) is Alignment.ASSUMED_UNCHANGED


def test_a4_other_side_changed_long_after_the_silent_one() -> None:
    a = hand(FLOW, [(50, 200, 50, CHANGE)])
    b = hand(RETURN, [(0, 400, 0, CHANGE)])
    assert sample(a, b, 55, a_hb=True, b_hb=False) is Alignment.MISALIGNED


def test_a5_confirmed_but_unchanged_is_assumed_unchanged() -> None:
    a = hand(
        FLOW,
        [
            (0, 100, 0, CHANGE),
            (100, 200, 100, CONFIRM),
            (200, 300, 200, CONFIRM),
            (300, 400, 300, CONFIRM),
        ],
    )
    b = hand(RETURN, [(0, 400, 0, CHANGE)])
    assert sample(a, b, 305, a_hb=True, b_hb=False) is Alignment.ASSUMED_UNCHANGED


def test_a6_both_change_only() -> None:
    a = hand(FLOW, [(0, 400, 0, CHANGE)])
    b = hand(RETURN, [(40, 400, 40, CHANGE)])
    assert sample(a, b, 45, a_hb=False, b_hb=False) is Alignment.MISALIGNED


def test_a7_unknown_side_is_not_misaligned() -> None:
    a = hand(FLOW, [(100, 200, 100, CHANGE)])
    b = hand(RETURN, [])  # stale/unknown everywhere
    result = align_pair(a, b, t(150), TOL, a_heartbeat=True, b_heartbeat=True)
    assert result.alignment is None
    assert result.b is None
    assert result.a == 1.0


def test_a8_history_pair_uses_change_only_rule() -> None:
    a = hand(FLOW, [(100, 400, 100, CHANGE)])
    b = hand(RETURN, [(140, 400, 140, CHANGE)])
    assert sample(a, b, 145, a_hb=False, b_hb=False) is Alignment.MISALIGNED


def test_pair_tolerance_is_order_insensitive_with_default() -> None:
    c = config(
        cfg(FLOW),
        pair_tolerances=(PairTolerance(FLOW, RETURN, 5 * S),),
        default_pair_tolerance_ms=30 * S,
    )
    assert pair_tolerance(c, FLOW, RETURN) == 5 * S
    assert pair_tolerance(c, RETURN, FLOW) == 5 * S
    assert pair_tolerance(c, FLOW, ROOM) == 30 * S


# --------------------------------------------------------------------------------------
# Q1-Q8
# --------------------------------------------------------------------------------------

ALL_SIGNALS = [SignalRef(Role.ROOM_TEMPERATURE, Scope(ScopeKind.ROOM, f"r{i}")) for i in range(15)]


def test_q1_one_connection_event_per_source_not_per_signal() -> None:
    cfgs = config(*(cfg(sig) for sig in ALL_SIGNALS))
    evs = [conn(WS, 600, False), conn(WS, 2400, True)]
    lost = [e for e in events_of(cfgs, [], evs, 3600) if e[0] == "connection_lost"]
    assert lost == [ev("connection_lost", "ws", 600, 2400)]


def test_q2_outage_over_an_hour_boundary_is_split_on_the_grid() -> None:
    evs = [conn(WS, 3000, False), conn(WS, 4200, True)]
    lost = [e for e in events_of(config(cfg(FLAME)), [], evs, 4800) if e[0] == "connection_lost"]
    assert lost == [
        ev("connection_lost", "ws", 3000, 3600),
        ev("connection_lost", "ws", 3600, 4200),
    ]


def test_q3_simultaneous_ws_and_gateway_outage_have_distinct_keys() -> None:
    cfgs = config(cfg(FLAME, gateway=True))
    evs = [conn(WS, 600, False), conn(GW, 600, False), conn(WS, 900, True), conn(GW, 900, True)]
    win = window(1800)
    from cvidee.analysis.timeline import build_stage1

    s1 = build_stage1([C(FLAME, 0, OFF)], evs, cfgs, win)
    lost = [
        e
        for e in apply_quality(s1.timelines, cfgs, win, s1.outages).events
        if e.kind is QualityEventKind.CONNECTION_LOST
    ]
    assert len(lost) == 2
    assert len({e.key for e in lost}) == 2
    assert {e.source for e in lost} == {ConnectionSource.WS, ConnectionSource.CAN_GATEWAY}


def test_q4_counter_reset_is_reported_and_consumption_never_negative() -> None:
    cfgs = config(cfg(GAS, cumulative=True))
    obs = [C(GAS, 0, 1234.5), C(GAS, 100, 0.4), C(GAS, 200, 5.4)]
    assert events_of(cfgs, obs, [], 300) == [ev("counter_reset", str(GAS), 100, 100, "1234.5->0.4")]
    res = run(cfgs, obs, [], 300)
    timeline = res.timelines[0]
    assert [round(s.consumption, 6) for s in counter_segments(timeline)] == [0.0, 5.0]
    assert counter_consumption(timeline) == 5.0
    assert len(detect_counter_resets(timeline)) == 1


@given(st.lists(st.floats(0, 1e6, allow_nan=False), min_size=1, max_size=30))
def test_counter_consumption_is_never_negative(values: list[float]) -> None:
    intervals = tuple(
        ValueInterval(t(i), t(i + 1), v, PROV, t(i), CHANGE) for i, v in enumerate(values)
    )
    timeline = SignalTimeline(GAS, TimeRange(t(0), t(len(values))), intervals)
    segments = counter_segments(timeline)
    resets = sum(1 for a, b in pairwise(values) if b < a)
    assert len(segments) == resets + 1
    assert all(s.consumption >= 0 for s in segments)
    assert len(detect_counter_resets(timeline)) == resets


def test_q5_duplicates_per_hour_bucket() -> None:
    obs = [C(FLAME, 10, OFF)] * 4 + [C(FLAME, 3700, ON)] * 2
    dups = [e for e in events_of(config(cfg(FLAME)), obs, [], 7200) if e[0] == "duplicate"]
    assert dups == [
        ev("duplicate", str(FLAME), 0, 3600, "", 3),
        ev("duplicate", str(FLAME), 3600, 7200, "", 1),
    ]


def test_q6_two_partners_give_two_misaligned_events() -> None:
    flow = hand(FLOW, [(100, 400, 100, CHANGE)])
    ret = hand(RETURN, [(140, 400, 140, CHANGE)])
    setpoint = hand(SETPOINT, [(0, 400, 0, CHANGE)])
    win = window(400)
    first = misaligned_events(
        flow, ret, TimeRange(t(0), t(400)), TOL, win, HOUR_MS, a_heartbeat=True, b_heartbeat=True
    )
    second = misaligned_events(
        flow,
        setpoint,
        TimeRange(t(0), t(400)),
        TOL,
        win,
        HOUR_MS,
        a_heartbeat=True,
        b_heartbeat=False,
    )
    events = [*first, *second]
    assert len(events) == 2
    assert len({e.key for e in events}) == 2
    assert {e.other_signal for e in events} == {RETURN, FLOW}  # ordered by SignalRef: a < b
    assert first[0].kind is QualityEventKind.MISALIGNED
    assert first[0].detail == "max_skew_ms=40000"
    assert (first[0].start, first[0].end) == (t(140), None)


def test_misaligned_event_stops_when_aligned_again() -> None:
    flow = hand(FLOW, [(100, 400, 100, CHANGE)])
    ret = hand(RETURN, [(140, 160, 140, CHANGE), (160, 400, 125, CHANGE)])
    events = misaligned_events(
        flow,
        ret,
        TimeRange(t(0), t(400)),
        TOL,
        window(400),
        HOUR_MS,
        a_heartbeat=True,
        b_heartbeat=True,
    )
    assert [(e.start - T0, e.end - T0 if e.end else None) for e in events] == [(140 * S, 160 * S)]


def test_q7_ongoing_stale_has_no_end_and_is_not_final() -> None:
    res = run(config(cfg(FLOW, heartbeat=True)), [C(FLOW, 0, 50.0)], [], 100)
    win = window(100)
    q = apply_quality(res.timelines, config(cfg(FLOW, heartbeat=True)), win, res.outages)
    assert [(e.kind, e.end, e.final) for e in q.events] == [(QualityEventKind.STALE, None, False)]


# --------------------------------------------------------------------------------------
# Plausibility, validity, coverage, resolution
# --------------------------------------------------------------------------------------


def test_implausible_value_becomes_unknown_with_event() -> None:
    cfgs = config(cfg(FLOW))
    obs = [C(FLOW, 0, 50.0), C(FLOW, 100, 500.0), C(FLOW, 200, 60.0)]
    res = run(cfgs, obs, [], 300)
    q = apply_quality(res.timelines, cfgs, window(300))
    tl = q.timelines[0]
    assert [type(i).__name__ for i in tl.intervals] == [
        "ValueInterval",
        "UnknownInterval",
        "ValueInterval",
    ]
    assert tl.intervals[1] == UnknownInterval(t(100), t(200), R.IMPLAUSIBLE)
    assert [(e.kind, e.detail) for e in q.events] == [(QualityEventKind.IMPLAUSIBLE, "-10..120")]


def test_configured_bounds_override_role_defaults() -> None:
    cfgs = config(cfg(ROOM, lo=15.0, hi=25.0))
    res = run(cfgs, [C(ROOM, 0, 30.0)], [], 100)
    q = apply_quality(res.timelines, cfgs, window(100))
    assert q.events[0].detail == "15..25"
    assert Role.ROOM_TEMPERATURE in DEFAULT_PLAUSIBILITY


def test_wrong_type_and_non_finite_values_are_invalid() -> None:
    cfgs = config(cfg(FLAME), cfg(FLOW))
    obs = [C(FLAME, 0, "x" * 60), C(FLOW, 0, float("nan")), C(FLOW, 50, True)]
    res = run(cfgs, obs, [], 100)
    q = apply_quality(res.timelines, cfgs, window(100))
    kinds = {(e.kind, e.signal): e for e in q.events}
    assert kinds[(QualityEventKind.INVALID, FLAME)].detail == "x" * 40
    assert (QualityEventKind.INVALID, FLOW) in kinds
    assert all(
        isinstance(i, UnknownInterval) and i.reason is R.INVALID
        for tl in q.timelines
        for i in tl.intervals
    )


def test_unknown_event_split_on_grid_and_open_at_horizon() -> None:
    cfgs = config(cfg(FLAME))
    res = run(cfgs, [C(FLAME, 0, OFF), C(FLAME, 3000, None)], [], 5000)
    q = apply_quality(res.timelines, cfgs, window(5000))
    assert [
        (e.kind.value, (e.start - T0) // S, None if e.end is None else (e.end - T0) // S)
        for e in q.events
    ] == [("unavailable", 3000, 3600), ("unavailable", 3600, None)]


def test_no_data_and_unavailable_events() -> None:
    cfgs = config(cfg(FLAME))
    assert events_of(cfgs, [C(FLAME, 100, ON)], [], 300) == [ev("data_gap", str(FLAME), 0, 100)]


def test_coverage_by_signal_over_emit_range() -> None:
    cfgs = config(cfg(FLAME), cfg(FLOW))
    res = run(cfgs, [C(FLAME, 150, ON), C(FLOW, 0, 1.0)], [], 200)
    win = window(200, start_s=0, emit_s=100)
    cov = coverage_by_signal(res.timelines, win)
    assert cov == {FLAME: 0.5, FLOW: 1.0}
    assert coverage_by_signal(res.timelines, window(200, emit_s=200)) == {FLAME: 0.0, FLOW: 0.0}


def test_update_interval_median_ignores_polls_and_old_data() -> None:
    obs = [
        C(FLOW, 0, 1.0),
        C(FLOW, 10, 2.0),
        F(FLOW, 20, 2.0),
        C(FLOW, 40, 3.0),
        P(FLOW, 41, 3.0),
        C(ROOM, 0, 3.0),
    ]
    win = window(100)
    assert update_interval_median_ms(obs, FLOW, win) == 10 * S
    assert update_interval_median_ms(obs, ROOM, win) is None
    assert update_interval_median_ms(obs, SETPOINT, win) is None
    far = window(100 + 24 * 3600)
    assert update_interval_median_ms(obs, FLOW, far) is None
