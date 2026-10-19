"""Pure per-room comfort metrics and boundaries (FR-17)."""

from datetime import UTC, datetime

from cvidee.analysis.change_evaluation import ComparisonPolicy, period_metrics
from cvidee.analysis.room_comfort import RoomComfortPeriod, analyze_room_comfort
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
    UnknownInterval,
    UnknownReason,
    ValueInterval,
    ValueKind,
)
from cvidee.api.schemas.installation import RoomComfort, RoomComfortWindow

HOUR = 3_600_000
START = int(datetime(2026, 10, 19, 5, tzinfo=UTC).timestamp() * 1000)  # Mon 07:00 CEST
RANGE = TimeRange(START, START + 2 * HOUR)
ROOM_TEMP = SignalRef(Role.ROOM_TEMPERATURE, Scope(ScopeKind.ROOM, "woonkamer"))
ROOM_SETPOINT = SignalRef(Role.ROOM_SETPOINT, Scope(ScopeKind.ROOM, "woonkamer"))
PROVENANCE = Provenance(ValueKind.MEASURED, "sensor.room")


def timeline(
    signal: SignalRef, pieces: tuple[tuple[int, int, float | None], ...]
) -> SignalTimeline:
    intervals = tuple(
        UnknownInterval(lo, hi, UnknownReason.NO_DATA)
        if value is None
        else ValueInterval(lo, hi, value, PROVENANCE, lo, ObservationKind.POLL)
        for lo, hi, value in pieces
    )
    return SignalTimeline(signal, RANGE, intervals)


def schedule() -> RoomComfort:
    return RoomComfort(
        status="scheduled",
        windows=[
            RoomComfortWindow(
                weekdays=[0], start_time="07:00", end_time="09:00", target_temperature_c=20
            )
        ],
    )


def ch_mode() -> tuple[ModeSegment, ...]:
    return (ModeSegment(START, START + 2 * HOUR, Mode.CH, ModeCertainty.DIRECT),)


def test_room_metrics_are_independent_for_target_and_actual_setpoint() -> None:
    actual = timeline(
        ROOM_TEMP,
        ((START, START + HOUR, 19), (START + HOUR, START + 2 * HOUR, 21)),
    )
    setpoint = timeline(ROOM_SETPOINT, ((START, START + 2 * HOUR, 19),))
    result = analyze_room_comfort(
        "woonkamer", schedule(), actual, setpoint, ch_mode(), START, START + 2 * HOUR, 0.5
    )
    assert result.availability == "available"
    assert result.coverage == 1
    assert result.target_comfort_loss_ms == HOUR
    assert result.setpoint_comfort_loss_ms == 0
    assert result.target_overshoot_ms == HOUR
    assert result.target_max_overshoot_c == 1
    assert result.warmup_mean_ms == HOUR
    assert result.warmup_samples == 1


def test_sensor_gap_and_dhw_remain_unobserved_instead_of_zero_loss() -> None:
    actual = timeline(
        ROOM_TEMP,
        ((START, START + HOUR, None), (START + HOUR, START + 2 * HOUR, 18)),
    )
    modes = (
        ModeSegment(START, START + HOUR, Mode.CH, ModeCertainty.DIRECT),
        ModeSegment(START + HOUR, START + 2 * HOUR, Mode.DHW, ModeCertainty.DIRECT),
    )
    result = analyze_room_comfort(
        "woonkamer", schedule(), actual, None, modes, START, START + 2 * HOUR, 0.5
    )
    assert result.availability == "limited"
    assert result.observed_ms == 0
    assert result.coverage == 0
    assert result.target_comfort_loss_ms is None
    assert result.warmup_mean_ms is None
    assert result.warmup_incomplete


def test_special_period_target_and_exclusion_are_applied() -> None:
    actual = timeline(ROOM_TEMP, ((START, START + 2 * HOUR, 19),))
    temporary = RoomComfortPeriod(START, START + HOUR, False, "temporary_target", 18)
    excluded = RoomComfortPeriod(START + HOUR, START + 2 * HOUR, True)
    result = analyze_room_comfort(
        "woonkamer",
        schedule(),
        actual,
        None,
        ch_mode(),
        START,
        START + 2 * HOUR,
        0.5,
        (temporary, excluded),
    )
    assert result.target_source == "special_period"
    assert result.expected_ms == HOUR
    assert result.target_comfort_loss_ms == 0


def test_unconfigured_room_has_no_invented_zero_metrics() -> None:
    result = analyze_room_comfort(
        "woonkamer",
        RoomComfort(status="not_configured"),
        None,
        None,
        ch_mode(),
        START,
        START + HOUR,
        0.5,
    )
    assert result.availability == "not_available"
    assert result.coverage is None
    assert result.target_comfort_loss_ms is None


def test_before_after_evaluation_uses_profile_target_and_marks_mixed_profiles_unknown() -> None:
    actual = timeline(ROOM_TEMP, ((START, START + 2 * HOUR, 19),))
    setpoint = timeline(ROOM_SETPOINT, ((START, START + 2 * HOUR, 18),))
    metrics = period_metrics(
        RANGE,
        (actual, setpoint),
        (),
        ch_mode(),
        (),
        ComparisonPolicy(),
        {"woonkamer": schedule()},
    )
    assert dict(metrics.cold_hours)["woonkamer"] == 168
    mixed = period_metrics(
        RANGE,
        (actual, setpoint),
        (),
        ch_mode(),
        (),
        ComparisonPolicy(),
        {"woonkamer": schedule()},
        comfort_profile_mixed=True,
    )
    assert mixed.comfort_profile_mixed
    assert dict(mixed.cold_hours)["woonkamer"] is None
