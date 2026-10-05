"""Special periods (FR-10): repository, exclusion helper and the rule-facing view.

Marked periods stay visible but do not count for normal behaviour, before/after comparisons
or optimisation advice, depending on what the user chose to exclude them from.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from cvidee.analysis.types import TimeRange
from cvidee.rules.base import SpecialPeriod as RuleSpecialPeriod
from cvidee.store.models import SpecialPeriod

__all__ = [
    "ExclusionPurpose",
    "SqlSpecialPeriodRepository",
    "excluded_intervals",
    "rule_periods",
]


class ExclusionPurpose(StrEnum):
    NORMAL_BEHAVIOUR = "normal_behaviour"
    """Baseline / normal behaviour."""
    COMPARISONS = "comparisons"
    """Before/after (reference and observation periods)."""
    OPTIMISATION = "optimisation"
    """Central-heating conclusions and advice."""


def _excludes(period: SpecialPeriod, purpose: ExclusionPurpose) -> bool:
    if purpose is ExclusionPurpose.NORMAL_BEHAVIOUR:
        return period.exclude_from_baseline
    if purpose is ExclusionPurpose.COMPARISONS:
        return period.exclude_from_comparisons
    return period.exclude_from_ch_conclusions


def _range_of(period: SpecialPeriod, rng: TimeRange) -> TimeRange | None:
    """The period clipped to ``rng``; a period still running ends at ``rng.end``."""
    end = rng.end if period.end_ts is None else period.end_ts
    return TimeRange(period.start_ts, end).intersect(rng) if end > period.start_ts else None


def excluded_intervals(
    periods: Iterable[SpecialPeriod], rng: TimeRange, purpose: ExclusionPurpose
) -> tuple[TimeRange, ...]:
    """Sorted, merged intervals of ``rng`` that are excluded for ``purpose``.

    Only periods that are excluded for that purpose count; half-open semantics, so periods
    that merely touch are merged and a period ending exactly at ``rng.start`` is not included.
    """
    clipped = sorted(
        (
            r
            for p in periods
            if _excludes(p, purpose) and (r := _range_of(p, rng)) is not None
        ),
        key=lambda r: (r.start, r.end),
    )
    merged: list[TimeRange] = []
    for r in clipped:
        if merged and r.start <= merged[-1].end:
            merged[-1] = TimeRange(merged[-1].start, max(merged[-1].end, r.end))
        else:
            merged.append(r)
    return tuple(merged)


class SqlSpecialPeriodRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def in_range(self, start_ts: int | None = None, end_ts: int | None = None) -> list[SpecialPeriod]:
        """Periods overlapping ``[start_ts, end_ts)`` (open-ended periods included)."""
        stmt = select(SpecialPeriod).order_by(SpecialPeriod.start_ts, SpecialPeriod.id)
        if end_ts is not None:
            stmt = stmt.where(SpecialPeriod.start_ts < end_ts)
        if start_ts is not None:
            stmt = stmt.where(
                (SpecialPeriod.end_ts.is_(None)) | (SpecialPeriod.end_ts > start_ts)
            )
        return list(self._session.scalars(stmt))

    def get(self, period_id: int) -> SpecialPeriod | None:
        return self._session.get(SpecialPeriod, period_id)

    def add(self, period: SpecialPeriod) -> SpecialPeriod:
        self._session.add(period)
        self._session.flush()
        return period

    def update(self, period: SpecialPeriod, now_ts: int) -> SpecialPeriod:
        period.updated_at_ts = now_ts
        self._session.flush()
        return period

    def delete(self, period_id: int) -> None:
        period = self._session.get(SpecialPeriod, period_id)
        if period is not None:
            self._session.delete(period)
            self._session.flush()

    def excluded_intervals(
        self, rng: TimeRange, purpose: ExclusionPurpose
    ) -> tuple[TimeRange, ...]:
        return excluded_intervals(self.in_range(rng.start, rng.end), rng, purpose)


def rule_periods(session: Session, rng: TimeRange) -> tuple[RuleSpecialPeriod, ...]:
    """Periods overlapping ``rng`` as rules see them. A period excluded from anything is
    ``excluded`` for the rules (conservative: it is not normal behaviour)."""
    out: list[RuleSpecialPeriod] = []
    for p in SqlSpecialPeriodRepository(session).in_range(rng.start, rng.end):
        end = rng.end if p.end_ts is None else p.end_ts
        if end <= p.start_ts:
            continue
        out.append(
            RuleSpecialPeriod(
                range=TimeRange(p.start_ts, end),
                kind=p.kind,
                excluded=p.exclude_from_baseline
                or p.exclude_from_comparisons
                or p.exclude_from_ch_conclusions,
            )
        )
    return tuple(out)
