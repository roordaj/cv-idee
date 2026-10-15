"""Timeline over stored observations, derived cycles and human change markers."""

import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from cvidee.analysis.quality import apply_quality
from cvidee.analysis.types import AnalysisWindow, Role, SignalRef
from cvidee.analysis.types import TimeRange as AnalysisRange
from cvidee.api.problems import ProblemError
from cvidee.api.schemas.common import TimeRange
from cvidee.api.schemas.data import (
    Cycle,
    CycleClass,
    DemandSegment,
    ModeSegment,
    PeriodBand,
    SampledSeries,
    TimelineResponse,
)
from cvidee.changes.log import ChangeLog
from cvidee.findings.stage import StoreTimelines
from cvidee.runner.sources import SourceSettings, build_pipeline_config, load_mapped_signals
from cvidee.settings.repository import current_revision, effective_values, pipeline_settings
from cvidee.store.enums import EndReason, Mode, TriState
from cvidee.store.models import BurnerCycle, SpecialPeriod
from cvidee.store.models import ModeSegment as ModeRow


def _dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts / 1000, UTC)


class TimelineReadModel:
    def __init__(self, session: Session, clock: Callable[[], int]) -> None:
        self.session = session
        self.clock = clock

    def timeline(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> TimelineResponse:
        end = end or _dt(self.clock())
        start = start or end - timedelta(hours=24)
        if start >= end or end - start > timedelta(days=31):
            raise ProblemError(
                422,
                "Ongeldig tijdvak",
                "Kies een tijdvak van maximaal 31 dagen met begin vóór einde.",
            )
        lo, hi = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
        window = AnalysisRange(lo, hi)
        values = effective_values(current_revision(self.session))
        sources = SourceSettings()
        mapped = load_mapped_signals(self.session)
        config = build_pipeline_config(
            self.session, mapped, sources, base=pipeline_settings(None, values)
        )
        timelines = StoreTimelines(self.session, mapped, sources, config, hi).build(window)
        checked = apply_quality(tuple(timelines.values()), config, AnalysisWindow(lo, lo, hi))
        timelines = {t.signal: t for t in checked.timelines}
        step = max(1000, math.ceil((hi - lo) / 1200 / 1000) * 1000)

        def samples(role: Role) -> list[float | None]:
            timeline = timelines.get(SignalRef(role))
            intervals = iter(() if timeline is None else timeline.values)
            current = next(intervals, None)
            result: list[float | None] = []
            for ts in range(lo, hi, step):
                while current is not None and current.end <= ts:
                    current = next(intervals, None)
                value = (
                    current.value
                    if current is not None and current.start <= ts < current.end
                    else None
                )
                result.append(
                    float(value)
                    if isinstance(value, int | float) and not isinstance(value, bool)
                    else None
                )
            return result

        flame = timelines.get(SignalRef(Role.FLAME))
        gaps = (
            [TimeRange(start=_dt(i.start), end=_dt(i.end)) for i in flame.unknowns]
            if flame
            else [TimeRange(start=start, end=end)]
        )
        demand = timelines.get(SignalRef(Role.HEAT_DEMAND))
        heat_demand = (
            [DemandSegment(start=start, end=end, heat_demand=TriState.UNKNOWN)]
            if demand is None
            else [
                DemandSegment(
                    start=_dt(i.start),
                    end=_dt(i.end),
                    heat_demand=TriState.YES
                    if i.value is True
                    else TriState.NO
                    if i.value is False
                    else TriState.UNKNOWN,
                )
                for i in demand.values
            ]
            + [
                DemandSegment(start=_dt(i.start), end=_dt(i.end), heat_demand=TriState.UNKNOWN)
                for i in demand.unknowns
            ]
        )
        periods = list(
            self.session.scalars(
                select(SpecialPeriod)
                .where(
                    SpecialPeriod.start_ts < hi,
                    (SpecialPeriod.end_ts.is_(None)) | (SpecialPeriod.end_ts > lo),
                )
                .order_by(SpecialPeriod.start_ts, SpecialPeriod.id)
            )
        )
        modes = []
        cursor = lo
        for mode_row in self.session.scalars(
            select(ModeRow)
            .where(ModeRow.start_ts < hi, ModeRow.end_ts > lo)
            .order_by(ModeRow.start_ts)
        ):
            if mode_row.start_ts > cursor:
                modes.append(
                    ModeSegment(start=_dt(cursor), end=_dt(mode_row.start_ts), mode=Mode.UNKNOWN)
                )
            modes.append(
                ModeSegment(
                    start=_dt(max(lo, mode_row.start_ts)),
                    end=_dt(min(hi, mode_row.end_ts)),
                    mode=mode_row.mode,
                )
            )
            cursor = max(cursor, min(hi, mode_row.end_ts))
        if cursor < hi:
            modes.append(ModeSegment(start=_dt(cursor), end=end, mode=Mode.UNKNOWN))
        cycles = []
        rows = self.session.scalars(
            select(BurnerCycle)
            .where(
                BurnerCycle.start_ts < hi,
                (BurnerCycle.end_ts.is_(None)) | (BurnerCycle.end_ts > lo),
            )
            .order_by(BurnerCycle.start_ts)
        )
        for number, row in enumerate(rows, 1):
            excluded = row.mode is Mode.DHW or any(
                p.exclude_from_ch_conclusions
                and p.start_ts < (row.end_ts or hi)
                and (p.end_ts is None or p.end_ts > row.start_ts)
                for p in periods
            )
            short = (
                row.complete
                and row.mode is Mode.CH
                and row.end_reason is EndReason.STOP_DURING_DEMAND
                and row.duration_ms < values.short_cycle_min * 60_000
            )
            cycles.append(
                Cycle(
                    number=number,
                    start=_dt(row.start_ts),
                    end=None if row.end_ts is None else _dt(row.end_ts),
                    duration_s=row.duration_ms / 1000,
                    duration_is_lower_bound=not row.complete,
                    mode=row.mode,
                    end_reason=row.end_reason or EndReason.UNDETERMINED,
                    max_flow_temperature=row.flow_max_c,
                    flow_setpoint=row.flow_setpoint_c,
                    mean_modulation_pct=row.modulation_mean_pct,
                    short_during_demand=short and not excluded,
                    classification=CycleClass.EXCLUDED
                    if excluded
                    else CycleClass.INCOMPLETE
                    if not row.complete
                    else CycleClass.SHORT
                    if short
                    else CycleClass.NORMAL,
                )
            )
        changes, before = ChangeLog(self.session, self.clock).markers(start, end)
        return TimelineResponse(
            range=TimeRange(start=start, end=end),
            series=SampledSeries(
                start=start,
                step_s=step / 1000,
                flow_temperature=samples(Role.FLOW_TEMPERATURE),
                return_temperature=samples(Role.RETURN_TEMPERATURE),
                flow_setpoint=samples(Role.FLOW_SETPOINT),
                modulation_pct=samples(Role.MODULATION),
            ),
            modes=modes,
            heat_demand=sorted(heat_demand, key=lambda i: i.start),
            cycles=cycles,
            gaps=gaps,
            changes=changes,
            last_change_before=before,
            periods=[
                PeriodBand(
                    id=str(p.id),
                    kind=p.kind,
                    start=_dt(p.start_ts),
                    end=None if p.end_ts is None else _dt(p.end_ts),
                )
                for p in periods
            ],
        )
