"""Pure interpretation of local recurring room-comfort schedules."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from cvidee.api.schemas.installation import RoomComfort


def comfort_target_at(comfort: RoomComfort, instant: datetime) -> float | None:
    """Return the target active at an aware instant, preserving real DST chronology.

    Converting each UTC instant to the configured local zone naturally skips wall-clock
    minutes that do not exist in spring and keeps both occurrences of a repeated autumn
    hour in UTC order.
    """
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("The instant must include a timezone.")
    if comfort.status != "scheduled":
        return None
    local = instant.astimezone(ZoneInfo(comfort.timezone))
    minute = local.hour * 60 + local.minute
    for window in comfort.windows:
        start = _minutes(window.start_time)
        end = _minutes(window.end_time)
        if end > start:
            active = local.weekday() in window.weekdays and start <= minute < end
        else:
            active = (local.weekday() in window.weekdays and minute >= start) or (
                (local.weekday() - 1) % 7 in window.weekdays and minute < end
            )
        if active:
            return window.target_temperature_c
    return None


def _minutes(value: str) -> int:
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)
