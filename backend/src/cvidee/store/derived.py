"""SQL implementations of the runner's repositories (#27): derived data and analysis runs.

Row mapping between the analysis result types (:mod:`cvidee.analysis.types`) and the
derived tables of ADR-001 §5.3. ``replace_from`` implements ADR-002 §4.2: delete every
derived row with key ``>= emit_from`` and insert the run's output. Nothing here commits;
the runner wraps one run in one transaction.
"""

from collections.abc import Iterable
from typing import Any, cast

from sqlalchemy import Table, delete, insert, select, update
from sqlalchemy.orm import Session

from cvidee.analysis.types import (
    BOILER,
    OUTDOOR,
    BurnerCycle,
    ConnectionSource,
    CycleAggregates,
    CyclePhase,
    EndReason,
    MetricName,
    MetricValue,
    MetricWindow,
    MetricWindowKind,
    Mode,
    ModeCertainty,
    ModeSegment,
    PhaseSpan,
    PipelineResult,
    QualityEvent,
    QualityEventKind,
    Role,
    Scope,
    ScopeKind,
    SignalRef,
    TimeRange,
    ValueKind,
)
from cvidee.store.enums import MetricStatus, RunStatus, TriState
from cvidee.store.models import AnalysisRun
from cvidee.store.models import BurnerCycle as CycleRow
from cvidee.store.models import MetricValue as MetricRow
from cvidee.store.models import ModeSegment as ModeRow
from cvidee.store.models import QualityEvent as QualityRow

__all__ = [
    "SqlAnalysisRunRepository",
    "SqlDerivedDataRepository",
    "parse_signal_ref",
]

_CYCLES = cast(Table, CycleRow.__table__)
_MODES = cast(Table, ModeRow.__table__)
_QUALITY = cast(Table, QualityRow.__table__)
_METRICS = cast(Table, MetricRow.__table__)
_RUNS = cast(Table, AnalysisRun.__table__)


def parse_signal_ref(text: str) -> SignalRef:
    """Inverse of ``str(SignalRef)``, e.g. ``'room_temperature@room:slaapkamer'``."""
    role, _, scope = text.partition("@")
    kind, _, key = scope.partition(":")
    scope_kind = ScopeKind(kind)
    if scope_kind is ScopeKind.BOILER and not key:
        return SignalRef(Role(role), BOILER)
    if scope_kind is ScopeKind.OUTDOOR and not key:
        return SignalRef(Role(role), OUTDOOR)
    return SignalRef(Role(role), Scope(scope_kind, key))


def _tri(value: bool | None) -> TriState:
    return TriState.UNKNOWN if value is None else (TriState.YES if value else TriState.NO)


def _from_tri(value: TriState) -> bool | None:
    return None if value is TriState.UNKNOWN else value is TriState.YES


# ------------------------------------------------------------------------- row mapping


def mode_row(segment: ModeSegment, run_id: int | None) -> dict[str, Any]:
    return {
        "start_ts": segment.start,
        "end_ts": segment.end,
        "mode": segment.mode,
        "certainty": segment.certainty,
        "sources": [str(s) for s in segment.sources],
        "device_code": segment.device_code,
        "final": segment.final,
        "run_id": run_id,
    }


def cycle_row(cycle: BurnerCycle, run_id: int | None) -> dict[str, Any]:
    agg = cycle.aggregates
    return {
        "start_ts": cycle.start,
        "end_ts": cycle.end,
        "duration_ms": cycle.duration_ms,
        "complete": cycle.complete,
        "start_observed": cycle.start_observed,
        "mode": cycle.mode,
        "end_reason": cycle.end_reason,
        "phases": [{"phase": p.phase.value, "start": p.start, "end": p.end} for p in cycle.phases],
        "flow_setpoint_c": agg.flow_setpoint_c,
        "flow_max_c": agg.flow_max_c,
        "flow_mean_c": agg.flow_mean_c,
        "return_mean_c": agg.return_mean_c,
        "modulation_mean_pct": agg.modulation_mean_pct,
        "modulation_min_pct": agg.modulation_min_pct,
        "heat_demand_during": _tri(agg.heat_demand_during),
        "heat_demand_after_stop": _tri(agg.heat_demand_after_stop),
        "signal_coverage": agg.signal_coverage,
        "pause_before_ms": cycle.pause_before_ms,
        "final": cycle.final,
        "run_id": run_id,
    }


def quality_row(event: QualityEvent, run_id: int | None) -> dict[str, Any]:
    return {
        "kind": event.kind,
        "signal": "" if event.signal is None else str(event.signal),
        "source": event.source,
        "other_signal": "" if event.other_signal is None else str(event.other_signal),
        "start_ts": event.start,
        "end_ts": event.end,
        "count": event.count,
        "detail": event.detail,
        "final": event.final,
        "run_id": run_id,
    }


def metric_row(metric: MetricValue, run_id: int | None) -> dict[str, Any]:
    window = metric.window
    return {
        "name": metric.name.value,
        "mode": "" if metric.mode is None else metric.mode.value,
        "window_kind": window.kind,
        "window_start_ts": window.range.start,
        "cycle_start_ts": -1 if window.cycle_start is None else window.cycle_start,
        "window_end_ts": window.range.end,
        "status": MetricStatus.INSUFFICIENT_DATA if metric.value is None else MetricStatus.OK,
        "value_num": metric.value,
        "unit": metric.unit,
        "time_basis_seconds": metric.time_basis_seconds,
        "coverage": metric.coverage,
        "provenance_kind": metric.provenance_kind,
        "final": metric.final,
        "run_id": run_id,
    }


def _mode_from(m: Any) -> ModeSegment:
    return ModeSegment(
        start=m["start_ts"],
        end=m["end_ts"],
        mode=Mode(m["mode"]),
        certainty=ModeCertainty(m["certainty"]),
        sources=tuple(parse_signal_ref(s) for s in m["sources"]),
        final=m["final"],
        device_code=m["device_code"],
    )


def _cycle_from(m: Any) -> BurnerCycle:
    return BurnerCycle(
        start=m["start_ts"],
        end=m["end_ts"],
        duration_ms=m["duration_ms"],
        complete=m["complete"],
        start_observed=m["start_observed"],
        mode=Mode(m["mode"]),
        end_reason=None if m["end_reason"] is None else EndReason(m["end_reason"]),
        phases=tuple(PhaseSpan(CyclePhase(p["phase"]), p["start"], p["end"]) for p in m["phases"]),
        aggregates=CycleAggregates(
            flow_setpoint_c=m["flow_setpoint_c"],
            flow_max_c=m["flow_max_c"],
            flow_mean_c=m["flow_mean_c"],
            return_mean_c=m["return_mean_c"],
            modulation_mean_pct=m["modulation_mean_pct"],
            modulation_min_pct=m["modulation_min_pct"],
            heat_demand_during=_from_tri(TriState(m["heat_demand_during"])),
            heat_demand_after_stop=_from_tri(TriState(m["heat_demand_after_stop"])),
            signal_coverage=m["signal_coverage"],
        ),
        pause_before_ms=m["pause_before_ms"],
        final=m["final"],
    )


def _quality_from(m: Any) -> QualityEvent:
    return QualityEvent(
        kind=QualityEventKind(m["kind"]),
        signal=parse_signal_ref(m["signal"]) if m["signal"] else None,
        start=m["start_ts"],
        end=m["end_ts"],
        detail=m["detail"],
        final=m["final"],
        source=None if m["source"] is None else ConnectionSource(m["source"]),
        other_signal=parse_signal_ref(m["other_signal"]) if m["other_signal"] else None,
        count=m["count"],
    )


def _metric_from(m: Any) -> MetricValue:
    kind = MetricWindowKind(m["window_kind"])
    return MetricValue(
        name=MetricName(m["name"]),
        window=MetricWindow(
            kind,
            TimeRange(m["window_start_ts"], m["window_end_ts"]),
            None if m["cycle_start_ts"] < 0 else m["cycle_start_ts"],
        ),
        value=m["value_num"],
        unit=m["unit"],
        time_basis_seconds=m["time_basis_seconds"],
        coverage=m["coverage"],
        mode=Mode(m["mode"]) if m["mode"] else None,
        provenance_kind=ValueKind(m["provenance_kind"]),
        final=m["final"],
    )


# ------------------------------------------------------------------------- repositories


class SqlDerivedDataRepository:
    """SQLAlchemy implementation of :class:`~cvidee.store.repositories.DerivedDataRepository`."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def replace_from(self, emit_from_ts: int, result: PipelineResult, run_id: int) -> None:
        """ADR-002 §4.2: delete derived rows keyed ``>= emit_from_ts``, insert ``result``.

        Runs in the caller's transaction; a failure after the deletes leaves nothing behind
        once the caller rolls back.
        """
        s = self._session
        s.execute(delete(_CYCLES).where(_CYCLES.c.start_ts >= emit_from_ts))
        s.execute(delete(_MODES).where(_MODES.c.start_ts >= emit_from_ts))
        s.execute(delete(_QUALITY).where(_QUALITY.c.start_ts >= emit_from_ts))
        s.execute(delete(_METRICS).where(_METRICS.c.window_start_ts >= emit_from_ts))
        self._insert(_CYCLES, (cycle_row(c, run_id) for c in result.cycles))
        self._insert(_MODES, (mode_row(m, run_id) for m in result.mode_segments))
        self._insert(_QUALITY, (quality_row(q, run_id) for q in result.quality_events))
        self._insert(_METRICS, (metric_row(v, run_id) for v in result.metrics))

    def _insert(self, table: Table, rows: Iterable[dict[str, Any]]) -> None:
        batch = list(rows)
        if batch:
            self._session.execute(insert(table), batch)

    def mode_segments(self, start_ts: int, end_ts: int) -> list[ModeSegment]:
        rows = self._session.execute(
            select(_MODES)
            .where(_MODES.c.start_ts < end_ts, _MODES.c.end_ts > start_ts)
            .order_by(_MODES.c.start_ts)
        )
        return [_mode_from(r._mapping) for r in rows]

    def burner_cycles(self, start_ts: int, end_ts: int) -> list[BurnerCycle]:
        """Cycles starting in ``[start_ts, end_ts)``."""
        rows = self._session.execute(
            select(_CYCLES)
            .where(_CYCLES.c.start_ts >= start_ts, _CYCLES.c.start_ts < end_ts)
            .order_by(_CYCLES.c.start_ts)
        )
        return [_cycle_from(r._mapping) for r in rows]

    def quality_events(self, start_ts: int, end_ts: int) -> list[QualityEvent]:
        """Events overlapping ``[start_ts, end_ts)`` (ongoing events included)."""
        c = _QUALITY.c
        rows = self._session.execute(
            select(_QUALITY)
            .where(c.start_ts < end_ts, (c.end_ts.is_(None)) | (c.end_ts >= start_ts))
            .order_by(c.start_ts, c.kind, c.signal, c.other_signal, c.source)
        )
        return [_quality_from(r._mapping) for r in rows]

    def metric_values(
        self, window_kind: MetricWindowKind, start_ts: int, end_ts: int
    ) -> list[MetricValue]:
        c = _METRICS.c
        rows = self._session.execute(
            select(_METRICS)
            .where(c.window_kind == window_kind, c.window_start_ts >= start_ts)
            .where(c.window_start_ts < end_ts)
            .order_by(c.window_start_ts, c.name, c.mode, c.cycle_start_ts)
        )
        return [_metric_from(r._mapping) for r in rows]


class SqlAnalysisRunRepository:
    """SQLAlchemy implementation of :class:`~cvidee.store.repositories.AnalysisRunRepository`."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def enqueue(self, run: AnalysisRun) -> AnalysisRun:
        run.status = RunStatus.QUEUED
        self._session.add(run)
        self._session.flush()
        return run

    def start(self, run: AnalysisRun) -> AnalysisRun:
        run.status = RunStatus.RUNNING
        self._session.add(run)
        self._session.flush()
        return run

    def finish(self, run: AnalysisRun) -> None:
        self._session.add(run)
        self._session.flush()

    def get(self, run_id: int) -> AnalysisRun | None:
        return self._session.get(AnalysisRun, run_id)

    def queued(self) -> list[AnalysisRun]:
        stmt = (
            select(AnalysisRun)
            .where(AnalysisRun.status == RunStatus.QUEUED)
            .order_by(AnalysisRun.emit_from_ts, AnalysisRun.id)
        )
        return list(self._session.scalars(stmt))

    def last_succeeded(self) -> AnalysisRun | None:
        stmt = (
            select(AnalysisRun)
            .where(AnalysisRun.status == RunStatus.SUCCEEDED)
            .order_by(AnalysisRun.id.desc())
            .limit(1)
        )
        return self._session.scalars(stmt).first()

    def effective_watermark(self) -> int | None:
        """``min(last successful watermark, emit_from of queued requests)``; None if empty."""
        candidates: list[int] = []
        last = self.last_succeeded()
        if last is not None and last.watermark_ts is not None:
            candidates.append(last.watermark_ts)
        candidates.extend(r.emit_from_ts for r in self.queued())
        return min(candidates) if candidates else None

    def supersede(self, run_ids: Iterable[int], *, by_run: int, now_ts: int) -> None:
        """Mark queued requests as handled by run ``by_run``."""
        ids = list(run_ids)
        if not ids:
            return
        self._session.execute(
            update(_RUNS)
            .where(_RUNS.c.id.in_(ids), _RUNS.c.status == RunStatus.QUEUED)
            .values(status=RunStatus.SUPERSEDED, finished_at_ts=now_ts, stats={"by_run": by_run})
        )

    def fail_stale_running(self, now_ts: int) -> int:
        """Runs left ``running`` by a crashed process become ``failed``."""
        result = self._session.execute(
            update(_RUNS)
            .where(_RUNS.c.status == RunStatus.RUNNING)
            .values(status=RunStatus.FAILED, finished_at_ts=now_ts, errors=["interrupted"])
        )
        return int(getattr(result, "rowcount", 0) or 0)
