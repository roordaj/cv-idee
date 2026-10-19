"""Recurring room-comfort schedules use local civil time and immutable values."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from cvidee.api.schemas.installation import RoomComfort, RoomComfortWindow
from cvidee.installation.comfort import comfort_target_at


def _comfort(start: str, end: str, target: float = 20.5) -> RoomComfort:
    return RoomComfort(
        status="scheduled",
        windows=[
            RoomComfortWindow(
                weekdays=[6], start_time=start, end_time=end, target_temperature_c=target
            )
        ],
    )


def test_room_comfort_statuses_keep_unconfigured_separate_from_no_expectation() -> None:
    assert RoomComfort().status == "not_configured"
    assert RoomComfort(status="no_expectation").status == "no_expectation"


def test_schedule_supports_local_midnight_crossing() -> None:
    comfort = RoomComfort(
        status="scheduled",
        windows=[
            RoomComfortWindow(
                weekdays=[0], start_time="22:30", end_time="07:00", target_temperature_c=17
            )
        ],
    )

    assert comfort_target_at(comfort, datetime.fromisoformat("2026-10-19T21:45:00+00:00")) == 17
    assert comfort_target_at(comfort, datetime.fromisoformat("2026-10-20T04:30:00+00:00")) == 17
    assert comfort_target_at(comfort, datetime.fromisoformat("2026-10-20T05:00:00+00:00")) is None


def test_schedule_skips_nonexistent_spring_dst_minutes() -> None:
    comfort = _comfort("02:00", "04:00")

    assert comfort_target_at(comfort, datetime(2026, 3, 29, 0, 59, tzinfo=UTC)) is None
    assert comfort_target_at(comfort, datetime(2026, 3, 29, 1, 0, tzinfo=UTC)) == 20.5
    assert comfort_target_at(comfort, datetime(2026, 3, 29, 2, 0, tzinfo=UTC)) is None


def test_schedule_keeps_both_autumn_dst_occurrences_in_utc_order() -> None:
    comfort = _comfort("02:00", "03:00")

    assert comfort_target_at(comfort, datetime(2026, 10, 25, 0, 30, tzinfo=UTC)) == 20.5
    assert comfort_target_at(comfort, datetime(2026, 10, 25, 1, 30, tzinfo=UTC)) == 20.5
    assert comfort_target_at(comfort, datetime(2026, 10, 25, 2, 0, tzinfo=UTC)) is None


def test_overlapping_windows_across_midnight_are_rejected() -> None:
    with pytest.raises(ValidationError, match="niet overlappen"):
        RoomComfort(
            status="scheduled",
            windows=[
                RoomComfortWindow(
                    weekdays=[0], start_time="22:00", end_time="07:00", target_temperature_c=17
                ),
                RoomComfortWindow(
                    weekdays=[1], start_time="06:00", end_time="08:00", target_temperature_c=20
                ),
            ],
        )


def test_schedule_lookup_requires_an_aware_instant() -> None:
    with pytest.raises(ValueError, match="timezone"):
        comfort_target_at(_comfort("07:00", "08:00"), datetime(2026, 10, 25, 6, 30))
