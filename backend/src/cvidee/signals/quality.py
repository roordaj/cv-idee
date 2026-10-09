"""Observed coverage and resolution shared by the API and findings runner."""

import statistics
from collections.abc import Sequence
from itertools import pairwise

from sqlalchemy.orm import Session

from cvidee.analysis.types import SignalRef, SignalTimeline, TimeRange, UnknownReason
from cvidee.rules.base import SignalStatus
from cvidee.runner.sources import MappedSignal
from cvidee.store.observations import SqlObservationRepository


def observed_resolution_ms(
    session: Session, mapping: MappedSignal, rng: TimeRange, timeline: SignalTimeline
) -> int | None:
    """Median positive report interval; unknown spans never count as slow reporting.

    Declared expected resolution is deliberately not substituted for observations.
    Deduplicate evidence times so multiple reads of an unchanged HA report do not
    manufacture a fine measurement resolution.
    """
    rows = SqlObservationRepository(session).observations(
        mapping.entity_id,
        max(rng.start, mapping.valid_from),
        min(rng.end, mapping.valid_to or rng.end),
    )
    times = sorted(
        {
            row.last_reported_ts if row.last_reported_ts is not None else row.ts
            for row in rows
            if row.state not in ("unknown", "unavailable")
        }
    )
    intervals = [
        right - left
        for left, right in pairwise(times)
        if rng.start <= left < right <= rng.end
        and not any(gap.start < right and left < gap.end for gap in timeline.unknowns)
    ]
    return max(1, round(statistics.median(intervals))) if intervals else None


def signal_statuses(
    session: Session,
    mappings: Sequence[MappedSignal],
    timelines: dict[SignalRef, SignalTimeline],
    rng: TimeRange,
) -> tuple[SignalStatus, ...]:
    """Statuses of mappings valid at the assessment horizon, including silent ones."""
    result: list[SignalStatus] = []
    for mapping in mappings:
        if not mapping.valid_at(rng.end):
            continue
        timeline = timelines.get(mapping.signal)
        coverage = 0.0
        stale = False
        resolution = None
        if timeline is not None:
            known_ms = sum(
                max(0, min(value.end, rng.end) - max(value.start, rng.start))
                for value in timeline.values
            )
            coverage = min(1.0, known_ms / rng.duration_ms)
            current = timeline.at(rng.end - 1)
            stale = getattr(current, "reason", None) is UnknownReason.STALE
            resolution = observed_resolution_ms(session, mapping, rng, timeline)
        result.append(SignalStatus(mapping.signal, coverage, stale, resolution))
    return tuple(sorted(result, key=lambda status: status.signal))
