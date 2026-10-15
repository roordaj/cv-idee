"""Checkpointed, idempotent recorder import through the live analysis runner (FR-06)."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Mapping
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from cvidee.api.problems import ProblemError, not_found
from cvidee.api.schemas.common import TimeRange
from cvidee.api.schemas.data import ImportJob as ImportOut
from cvidee.api.schemas.data import ImportList, ImportRequest, ImportSignalProgress
from cvidee.ingest.ha_client import HAError, now_ms, parse_ha_time
from cvidee.runner.service import AnalysisRunner
from cvidee.runner.sources import load_mapped_signals
from cvidee.store.enums import ImportStatus, ObservationKind, ObservationOrigin, RunStatus
from cvidee.store.models import BurnerCycle, ImportJob
from cvidee.store.observations import SqlObservationRepository
from cvidee.store.records import ObservationRecord

DAY_MS = 86_400_000
ACTIVE = (ImportStatus.PENDING, ImportStatus.FETCHING, ImportStatus.ANALYSING)


class HistoryClient(Protocol):
    async def history(
        self, entity_id: str, start: int, end: int, *, heartbeat_expected: bool = False
    ) -> list[Mapping[str, Any]]: ...


def _dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts / 1000, UTC)


def history_records(
    rows: list[Mapping[str, Any]], entity: str, start: int, end: int, received: int
) -> list[ObservationRecord]:
    records = []
    for index, row in enumerate(rows):
        changed = parse_ha_time(row.get("last_changed"))
        updated = parse_ha_time(row.get("last_updated")) or changed
        if changed is None or updated is None:
            raise HAError("History state has no timestamp")
        # Recorder's first row may be a carry-in state, not a burner transition.
        carry = index == 0 and changed <= start
        ts = start if carry else updated
        if ts < start or ts >= end:
            continue
        state = str(row.get("state", "unknown"))
        value: float | None
        try:
            value = float(state)
            value = value if math.isfinite(value) else None
        except ValueError:
            value = None
        kind = (
            ObservationKind.POLL
            if carry
            else ObservationKind.CONFIRM
            if updated > changed
            else ObservationKind.CHANGE
        )
        reported = parse_ha_time(row.get("last_reported"))
        if reported is not None and reported >= end:
            reported = None
        later_report = reported if reported is not None and reported > ts else None
        if later_report is not None:
            reported = None if carry else ts
        elif not carry:
            reported = max(ts, reported or ts)
        records.append(
            ObservationRecord(
                entity_id=entity,
                ts=ts,
                state=state,
                value_num=value,
                kind=kind,
                origin=ObservationOrigin.IMPORT,
                received_at_ts=received,
                last_reported_ts=reported,
            )
        )
        next_changed = (
            parse_ha_time(rows[index + 1].get("last_changed")) if index + 1 < len(rows) else end
        )
        if later_report is not None and later_report < (next_changed or end):
            records.append(
                ObservationRecord(
                    entity_id=entity,
                    ts=later_report,
                    state=state,
                    value_num=value,
                    kind=ObservationKind.CONFIRM,
                    origin=ObservationOrigin.IMPORT,
                    received_at_ts=received,
                    last_reported_ts=later_report,
                )
            )
    return records


class HistoryImport:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        client: HistoryClient | None,
        runner: AnalysisRunner,
        clock: Callable[[], int] = now_ms,
    ) -> None:
        self.sessions, self.client, self.runner, self.clock = sessions, client, runner, clock
        self.task: asyncio.Task[None] | None = None

    def _get(self, session: Session, ident: str) -> ImportJob:
        if not ident.isdigit() or (row := session.get(ImportJob, int(ident))) is None:
            raise not_found("Import", ident)
        return row

    def _out(self, row: ImportJob) -> ImportOut:
        return ImportOut(
            id=str(row.id),
            status=row.status,
            range=TimeRange(start=_dt(row.from_ts), end=_dt(row.to_ts)),
            blocks_done=row.blocks_done,
            blocks_total=row.blocks_total,
            current_block_day=_dt(row.cursor_ts or row.from_ts).date()
            if row.status in ACTIVE
            else None,
            observations_imported=row.observations_imported,
            duplicates_skipped=row.duplicates_skipped,
            signals=[
                ImportSignalProgress(
                    signal_id=s["signal_id"],
                    observations=s["observations"],
                    first_at=None if s["first_ts"] is None else _dt(s["first_ts"]),
                )
                for s in row.per_signal
            ],
            earliest_available_at=None
            if row.earliest_available_ts is None
            else _dt(row.earliest_available_ts),
            cycles_found=row.cycles_found,
            coverage_pct=None if row.coverage is None else row.coverage * 100,
            warnings=[
                "Recorderhistorie kan minder bevestigingen bevatten dan livegegevens; "
                "onbekende tijd blijft onbekend."
            ]
            + (
                [
                    "Sommige signaalkoppelingen gelden pas na het begin van de import; "
                    "eerdere gegevens blijven buiten die analyse."
                ]
                if any(r.get("valid_from", row.from_ts) > row.from_ts for r in row.roles or [])
                else []
            ),
            errors=[str(e) for e in row.errors],
            started_at=_dt(row.started_at_ts or row.created_at_ts),
            finished_at=None if row.finished_at_ts is None else _dt(row.finished_at_ts),
            eta_s=None,
        )

    def import_list(self) -> ImportList:
        with self.sessions() as session:
            rows = list(
                session.scalars(
                    select(ImportJob).order_by(ImportJob.created_at_ts.desc(), ImportJob.id.desc())
                )
            )
            return ImportList(items=[self._out(row) for row in rows], earliest_available_at=None)

    def poll_import(self, ident: str) -> ImportOut:
        with self.sessions() as session:
            return self._out(self._get(session, ident))

    def start_import(self, body: ImportRequest) -> ImportOut:
        if self.client is None:
            raise ProblemError(
                503, "Home Assistant niet ingesteld", "Stel eerst de Home Assistant-verbinding in."
            )
        start, end = int(body.start.timestamp() * 1000), int(body.end.timestamp() * 1000)
        if start >= end or end > self.clock():
            raise ProblemError(
                422, "Ongeldig tijdvak", "Kies een verstreken tijdvak met begin vóór einde."
            )
        with self.sessions.begin() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            if session.scalar(select(ImportJob.id).where(ImportJob.status.in_(ACTIVE))) is not None:
                raise ProblemError(
                    409, "Import loopt al", "Wacht tot de huidige import klaar is of annuleer die."
                )
            mapped = load_mapped_signals(session)
            selected = None if body.signal_ids is None else set(body.signal_ids)
            known = {str(m.signal) for m in mapped}
            if selected is not None and (not selected or selected - known):
                raise ProblemError(
                    422, "Ongeldige signalen", "Kies gekoppelde signalen voor de import."
                )
            roles: list[dict[str, Any]] = [
                {
                    "signal_id": str(m.signal),
                    "entity_id": m.entity_id,
                    "heartbeat_expected": m.heartbeat_expected,
                    "valid_from": m.valid_from,
                    "valid_to": m.valid_to,
                }
                for m in mapped
                if selected is None or str(m.signal) in selected
            ]
            roles = list({(r["signal_id"], r["entity_id"]): r for r in roles}.values())
            if not roles:
                raise ProblemError(
                    422,
                    "Geen gekoppelde signalen",
                    "Koppel eerst de signalen die je wilt importeren.",
                )
            previous = session.scalar(
                select(ImportJob)
                .where(
                    ImportJob.from_ts == start,
                    ImportJob.to_ts == end,
                    ImportJob.status.in_((ImportStatus.INTERRUPTED, ImportStatus.FAILED)),
                )
                .order_by(ImportJob.id.desc())
            )
            if previous is not None and previous.roles == roles:
                row = previous
                row.status, row.finished_at_ts, row.errors = ImportStatus.PENDING, None, []
            else:
                row = ImportJob(
                    status=ImportStatus.PENDING,
                    from_ts=start,
                    to_ts=end,
                    cursor_ts=start,
                    roles=roles,
                    blocks_done=0,
                    blocks_total=math.ceil((end - start) / DAY_MS),
                    created_at_ts=self.clock(),
                    per_signal=[
                        {"signal_id": s, "observations": 0, "first_ts": None}
                        for s in sorted({r["signal_id"] for r in roles})
                    ],
                )
                session.add(row)
            session.flush()
            result = self._out(row)
        self.launch(int(result.id))
        return result

    def launch(self, ident: int) -> None:
        self.task = asyncio.create_task(self.run_job(ident), name=f"history-import-{ident}")

    def cancel_import(self, ident: str) -> ImportOut:
        with self.sessions.begin() as session:
            row = self._get(session, ident)
            if row.status not in ACTIVE:
                raise ProblemError(
                    409, "Import niet actief", "Deze import is al afgerond of onderbroken."
                )
            row.status, row.finished_at_ts = ImportStatus.CANCELLED, self.clock()
            session.flush()
            return self._out(row)

    async def recover(self) -> None:
        with self.sessions.begin() as session:
            rows = list(session.scalars(select(ImportJob).where(ImportJob.status.in_(ACTIVE))))
            for row in rows:
                row.status = ImportStatus.INTERRUPTED
            ident = rows[0].id if rows and self.client is not None else None
            if ident is not None:
                rows[0].status = ImportStatus.PENDING
        if ident is not None:
            self.launch(ident)

    async def stop(self) -> None:
        if self.task is not None and not self.task.done():
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task

    async def run_job(self, ident: int) -> None:
        try:
            await self._run(ident)
        except asyncio.CancelledError:
            self._fail(ident, ImportStatus.INTERRUPTED, None)
            raise
        except Exception:
            # Never persist upstream exception text: it can contain credentials or URLs.
            self._fail(
                ident,
                ImportStatus.FAILED,
                "Import mislukt. Controleer de verbinding en hervat de import.",
            )

    def _fail(self, ident: int, status: ImportStatus, error: str | None) -> None:
        with self.sessions.begin() as session:
            row = session.get(ImportJob, ident)
            if row is not None and row.status in ACTIVE:
                row.status, row.finished_at_ts = status, self.clock()
                row.errors = [] if error is None else [error]

    async def _run(self, ident: int) -> None:
        if self.client is None:
            raise HAError("History client unavailable")
        while True:
            with self.sessions.begin() as session:
                row = session.get(ImportJob, ident)
                if row is None or row.status is ImportStatus.CANCELLED:
                    return
                row.started_at_ts = row.started_at_ts or self.clock()
                start, end = row.cursor_ts or row.from_ts, row.to_ts
                roles = list(row.roles or [])
                row.status = ImportStatus.FETCHING if start < end else ImportStatus.ANALYSING
            if start >= end:
                break
            block_end = min(end, start + DAY_MS)
            records: list[ObservationRecord] = []
            for entity in sorted({r["entity_id"] for r in roles}):
                heartbeat = any(r["heartbeat_expected"] for r in roles if r["entity_id"] == entity)
                raw = await self.client.history(
                    entity, start, block_end, heartbeat_expected=heartbeat
                )
                records.extend(history_records(raw, entity, start, block_end, self.clock()))
            with self.sessions.begin() as session:
                row = session.get(ImportJob, ident)
                if row is None or row.status is ImportStatus.CANCELLED:
                    return
                result = SqlObservationRepository(session).add_observations(records)
                row.observations_imported += result.inserted
                row.duplicates_skipped += result.duplicates_skipped
                progress = [dict(s) for s in row.per_signal]
                for signal in progress:
                    entities = {
                        r["entity_id"] for r in roles if r["signal_id"] == signal["signal_id"]
                    }
                    own = [r for r in records if r.entity_id in entities]
                    signal["observations"] += len(own)
                    first = min((r.ts for r in own), default=None)
                    if first is not None:
                        signal["first_ts"] = min(first, signal["first_ts"] or first)
                row.per_signal = progress
                row.cursor_ts, row.blocks_done = block_end, row.blocks_done + 1
            await asyncio.sleep(0)
        with self.sessions() as session:
            row = session.get(ImportJob, ident)
            assert row is not None
            start, end = row.from_ts, row.to_ts
        runs = await asyncio.to_thread(self.runner.run_range, start, end, import_job_id=ident)
        if any(run.status is not RunStatus.SUCCEEDED for run in runs):
            raise HAError("Imported data analysis failed")
        with self.sessions.begin() as session:
            row = session.get(ImportJob, ident)
            if row is None or row.status is ImportStatus.CANCELLED:
                return
            row.status, row.finished_at_ts = ImportStatus.DONE, self.clock()
            row.cycles_found = (
                session.scalar(
                    select(func.count())
                    .select_from(BurnerCycle)
                    .where(BurnerCycle.start_ts >= start, BurnerCycle.start_ts < end)
                )
                or 0
            )
