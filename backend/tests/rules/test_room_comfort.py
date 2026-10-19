"""Room comfort findings stay scoped to the room with measured loss (FR-17)."""

from datetime import UTC, datetime

from cvidee.analysis.room_comfort import RoomComfortMetrics, analyze_room_comfort
from cvidee.analysis.types import (
    Mode,
    ModeCertainty,
    ModeSegment,
    ObservationKind,
    Provenance,
    Role,
    Scope,
    ScopeKind,
    SignalRef,
    SignalTimeline,
    TimeRange,
    ValueInterval,
    ValueKind,
)
from cvidee.api.schemas.installation import RoomComfort, RoomComfortWindow
from cvidee.rules.base import InstallationFacts, NoParams, RuleContext
from cvidee.rules.room_comfort import RoomComfortRule

HOUR = 3_600_000
START = int(datetime(2026, 10, 19, 5, tzinfo=UTC).timestamp() * 1000)
END = START + 2 * HOUR
PERIOD = TimeRange(START, END)
PROVENANCE = Provenance(ValueKind.MEASURED, "sensor.room")
COMFORT = RoomComfort(
    status="scheduled",
    windows=[
        RoomComfortWindow(
            weekdays=[0], start_time="07:00", end_time="09:00", target_temperature_c=20
        )
    ],
)
MODES = (ModeSegment(START, END, Mode.CH, ModeCertainty.DIRECT),)


def room_metric(room_key: str, value: float) -> RoomComfortMetrics:
    signal = SignalRef(Role.ROOM_TEMPERATURE, Scope(ScopeKind.ROOM, room_key))
    timeline = SignalTimeline(
        signal,
        PERIOD,
        (ValueInterval(START, END, value, PROVENANCE, START, ObservationKind.POLL),),
    )
    return analyze_room_comfort(room_key, COMFORT, timeline, None, MODES, START, END, 0.5)


def test_cold_and_warm_rooms_make_independent_findings() -> None:
    context = RuleContext(
        now=END,
        period=PERIOD,
        profile=InstallationFacts(rooms=("koud", "warm")),
        room_comfort=(("koud", room_metric("koud", 18)), ("warm", room_metric("warm", 21))),
        allowed_room_comfort_loss_h_week=4,
        minimum_room_comfort_coverage=0.8,
        minimum_room_comfort_observed_hours=1,
    )
    (candidate,) = RoomComfortRule().evaluate(context, NoParams())
    assert candidate.scope_key == "room:koud"
    assert candidate.category.value == "comfort"
    assert candidate.certainty.value == "high_measured"
    assert "warm" not in candidate.scope_key


def test_incomplete_or_unconfigured_comfort_never_emits_zero_loss_finding() -> None:
    result = analyze_room_comfort(
        "woonkamer",
        RoomComfort(status="not_configured"),
        None,
        None,
        MODES,
        START,
        END,
        0.5,
    )
    context = RuleContext(
        now=END,
        period=PERIOD,
        profile=InstallationFacts(rooms=("woonkamer",)),
        room_comfort=(("woonkamer", result),),
    )
    assert RoomComfortRule().evaluate(context, NoParams()) == ()
