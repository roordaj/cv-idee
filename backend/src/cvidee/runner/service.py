"""The analysis runner (ADR-002 §4, FR-06): window, watermark, persistence, recompute.

One code path for live and import: every run goes through :meth:`AnalysisRunner._run_chunks`,
which steps horizons forward in chunks; per horizon it builds the window from the stored
effective watermark, reads the input, runs the pure pipeline and, in **one transaction**,
replaces the derived rows from ``emit_from`` and records the run as ``succeeded`` with its
``next_watermark``. A failure rolls the transaction back (no partial derived data) and the
run is recorded as ``failed`` in a separate transaction; the next run starts from the last
successful watermark again.

* Live: :meth:`AnalysisRunner.tick` (scheduled every ``interval_s`` by :meth:`run_forever`)
  runs up to ``now - settle``.
* Recompute: :meth:`AnalysisRunner.request_recompute` queues a request (``status='queued'``,
  ``emit_from_ts``); the next tick lowers the effective watermark to it.
* Import: :meth:`AnalysisRunner.run_range` processes ``[start, end)`` in chunks with
  ``now := chunk_end + settle`` (ADR-002 §4.7).

Live runs and import share one lock (single writer).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from sqlalchemy.orm import Session, sessionmaker

from cvidee.analysis.pipeline import run_pipeline
from cvidee.analysis.types import (
    HOUR_MS,
    AnalysisWindow,
    PipelineConfig,
    PipelineResult,
    TimestampMs,
    floor_to_grid,
)
from cvidee.runner.sources import (
    MappedSignal,
    SourceSettings,
    build_pipeline_config,
    earliest_data_ts,
    load_mapped_signals,
    load_window_input,
)
from cvidee.store.derived import SqlAnalysisRunRepository, SqlDerivedDataRepository
from cvidee.store.enums import RunStatus, RunTrigger
from cvidee.store.models import AnalysisRun

__all__ = ["AfterRunHook", "AnalysisRunner", "RunnerSettings"]

logger = logging.getLogger(__name__)

AfterRunHook = Callable[[Session, PipelineResult, AnalysisRun], None]
"""Called inside the run's transaction after the derived rows were replaced (stage 6, rules,
registers here). An exception rolls the whole run back."""


def _wall_clock_ms() -> TimestampMs:
    return int(time.time() * 1000)


@dataclass(frozen=True, slots=True)
class RunnerSettings:
    interval_s: float = 60.0
    """Live tick interval."""
    chunk_ms: int = 24 * HOUR_MS
    """Largest horizon step of one run (catch-up, recompute, import; plan §3.1)."""
    pipeline: PipelineConfig | None = None
    """Thresholds/windows (signals are filled from the mappings); ``None`` = defaults."""
    sources: SourceSettings = field(default_factory=SourceSettings)
    rule_versions: Mapping[str, str] = field(default_factory=dict)


class AnalysisRunner:
    """Orchestrates the pure pipeline over the store. Thread-safe; one writer at a time."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: RunnerSettings | None = None,
        *,
        clock: Callable[[], TimestampMs] = _wall_clock_ms,
        after_run: Sequence[AfterRunHook] = (),
    ) -> None:
        self._sessions = session_factory
        self.settings = settings if settings is not None else RunnerSettings()
        self._clock = clock
        self._after_run = tuple(after_run)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ public API

    def request_recompute(
        self,
        start_ts: TimestampMs,
        end_ts: TimestampMs | None = None,
        *,
        reason: str = "recompute",
    ) -> AnalysisRun:
        """Queue a recompute from ``start_ts`` (ADR-002 §4.6). Replace-from semantics
        recompute everything after ``start_ts`` anyway; ``end_ts`` is only recorded."""
        now = self._clock()
        with self._sessions.begin() as session:
            run = SqlAnalysisRunRepository(session).enqueue(
                AnalysisRun(
                    trigger=RunTrigger.RECOMPUTE,
                    status=RunStatus.QUEUED,
                    reason=reason,
                    emit_from_ts=start_ts,
                    requested_at_ts=now,
                    stats={} if end_ts is None else {"requested_end_ts": end_ts},
                )
            )
            session.expunge(run)
        return run

    def tick(self, now: TimestampMs | None = None) -> list[AnalysisRun]:
        """One live tick: catch up to ``now - settle`` (in chunks if far behind)."""
        now = self._clock() if now is None else now
        with self._lock:
            return self._run_chunks(now, RunTrigger.LIVE)

    def run_range(
        self,
        start_ts: TimestampMs,
        end_ts: TimestampMs,
        *,
        trigger: RunTrigger = RunTrigger.IMPORT,
        import_job_id: int | None = None,
    ) -> list[AnalysisRun]:
        """Process ``[start_ts, end_ts)`` in chunks (history import, ADR-002 §4.7): a queued
        request lowers the watermark to ``start_ts`` (a late-data case for already processed
        time) and horizons step to ``end_ts`` with ``now := chunk_end + settle``."""
        self.request_recompute(start_ts, end_ts, reason=trigger.value)
        with self._lock:
            settle = self._settings_config().settle_ms
            return self._run_chunks(end_ts + settle, trigger, import_job_id=import_job_id)

    def recover(self) -> int:
        """Mark runs left ``running`` by a crashed process as ``failed`` (startup)."""
        with self._lock, self._sessions.begin() as session:
            return SqlAnalysisRunRepository(session).fail_stale_running(self._clock())

    async def run_forever(self, stop: asyncio.Event | None = None) -> None:
        """Tick every ``interval_s`` until ``stop`` is set (or the task is cancelled)."""
        stop = stop if stop is not None else asyncio.Event()
        await asyncio.to_thread(self.recover)
        while not stop.is_set():
            try:
                await asyncio.to_thread(self.tick)
            except Exception:
                logger.exception("analysis tick failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.settings.interval_s)

    # ---------------------------------------------------------------- internals

    def _settings_config(self) -> PipelineConfig:
        base = self.settings.pipeline
        return base if base is not None else PipelineConfig(signals=())

    def _run_chunks(
        self,
        now: TimestampMs,
        trigger: RunTrigger,
        *,
        import_job_id: int | None = None,
    ) -> list[AnalysisRun]:
        with self._sessions() as session:
            mapped = load_mapped_signals(session)
            if not mapped:
                return []
            config = build_pipeline_config(
                session,
                mapped,
                self.settings.sources,
                base=self.settings.pipeline,
                rule_versions=self.settings.rule_versions,
            )
            runs = SqlAnalysisRunRepository(session)
            last = runs.last_succeeded()
            config_changed = last is not None and last.config_hash != config.config_hash
            has_queued = bool(runs.queued())
            earliest = earliest_data_ts(session, mapped)
            watermark = runs.effective_watermark()
        if config_changed and not has_queued and earliest is not None:
            # A global configuration change without a scoped request: recompute all data.
            self.request_recompute(earliest, reason="config_changed")
            watermark = earliest if watermark is None else min(watermark, earliest)
        if watermark is None:
            watermark = earliest  # first run ever: start at the oldest data
        if watermark is None:
            return []
        final_horizon = now - config.settle_ms
        done: list[AnalysisRun] = []
        horizon = floor_to_grid(watermark, config.grid_ms)
        while horizon < final_horizon:
            horizon = min(final_horizon, horizon + self.settings.chunk_ms)
            run = self._run_once(
                config, mapped, horizon + config.settle_ms, trigger, import_job_id, watermark
            )
            done.append(run)
            if run.status is not RunStatus.SUCCEEDED:
                break
        return done

    def _run_once(
        self,
        config: PipelineConfig,
        mapped: Sequence[MappedSignal],
        now: TimestampMs,
        trigger: RunTrigger,
        import_job_id: int | None,
        initial_watermark: TimestampMs,
    ) -> AnalysisRun:
        started = self._clock()
        with self._sessions.begin() as session:
            repo = SqlAnalysisRunRepository(session)
            queued = repo.queued()
            watermark = repo.effective_watermark()
            if watermark is None:
                watermark = initial_watermark
            window = AnalysisWindow.for_run(
                watermark=watermark,
                now=now,
                lookback_ms=config.lookback_ms,
                settle_ms=config.settle_ms,
                grid_ms=config.grid_ms,
            )
            covered = [r.id for r in queued]  # all: emit_from <= floor(each request)
            if covered and trigger is RunTrigger.LIVE:
                trigger = RunTrigger.RECOMPUTE
            run = repo.start(
                AnalysisRun(
                    trigger=trigger,
                    status=RunStatus.RUNNING,
                    reason=queued[0].reason if queued else None,
                    emit_from_ts=window.emit_from,
                    context_start_ts=window.context_start,
                    horizon_ts=window.end,
                    requested_at_ts=started,
                    started_at_ts=started,
                    rule_versions=dict(self.settings.rule_versions),
                    config_hash=config.config_hash,
                    import_job_id=import_job_id,
                )
            )
            session.expunge(run)
        run_id = run.id
        try:
            with self._sessions.begin() as session:
                observations, events = load_window_input(
                    session, mapped, self.settings.sources, window
                )
                result = run_pipeline(observations, events, config, window, now)
                SqlDerivedDataRepository(session).replace_from(window.emit_from, result, run_id)
                attached = session.merge(run)
                for hook in self._after_run:
                    hook(session, result, attached)
                repo = SqlAnalysisRunRepository(session)
                repo.supersede(covered, by_run=run_id, now_ts=self._clock())
                attached.status = RunStatus.SUCCEEDED
                attached.watermark_ts = result.next_watermark
                attached.finished_at_ts = self._clock()
                attached.stats = {
                    "observations": len(observations),
                    "connection_events": len(events),
                    "cycles": len(result.cycles),
                    "mode_segments": len(result.mode_segments),
                    "quality_events": len(result.quality_events),
                    "metrics": len(result.metrics),
                    "covered_requests": covered,
                }
                repo.finish(attached)
                session.flush()
                session.expunge(attached)
            return attached
        except Exception as exc:
            logger.exception("analysis run %s failed", run_id)
            with self._sessions.begin() as session:
                failed = session.get(AnalysisRun, run_id)
                if failed is not None:
                    failed.status = RunStatus.FAILED
                    failed.finished_at_ts = self._clock()
                    failed.errors = [f"{type(exc).__name__}: {exc}"]
                    session.flush()
                    session.expunge(failed)
                    return failed
            return run
