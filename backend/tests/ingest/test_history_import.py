"""Recorder import uses persistent checkpoints and produces the same cycles as live data."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from cvidee.api.schemas.data import ImportRequest
from cvidee.config import HAConnection, Settings
from cvidee.ingest.ha_client import AiohttpHAClient
from cvidee.ingest.history_import import DAY_MS, HistoryImport, history_records
from cvidee.main import create_app
from cvidee.runner.service import AnalysisRunner, RunnerSettings
from cvidee.store.enums import ImportStatus, ObservationKind
from cvidee.store.models import BurnerCycle, ConnectionEvent, ImportJob, Observation, SourceEntity
from tests.fakes.ha_server import TOKEN, FakeHAServer, make_state
from tests.runner.test_runner import END, HUGE, T0, make_db, seed, settle_of


@pytest.fixture
async def rig(
    tmp_path: Path,
) -> AsyncIterator[tuple[sessionmaker[Session], HistoryImport, FakeHAServer]]:
    factory = make_db(tmp_path, "import")
    seed(factory)
    server = FakeHAServer()
    with factory.begin() as session:
        for row, entity in session.execute(
            select(Observation, SourceEntity.entity_id).join(SourceEntity)
        ):
            server.history_states.setdefault(entity, []).append(
                make_state(entity, row.state, changed=row.ts)
            )
        session.execute(delete(Observation))
        session.execute(delete(ConnectionEvent))
    await server.start()
    client = AiohttpHAClient(
        HAConnection(server.url + "/api/websocket", server.url + "/api", SecretStr(TOKEN)),
        tracked=lambda: (),
    )
    importer = HistoryImport(
        factory, client, AnalysisRunner(factory, RunnerSettings(chunk_ms=HUGE))
    )
    yield factory, importer, server
    await importer.stop()
    await client.close()
    await server.stop()


def request(end: int = END) -> ImportRequest:
    return ImportRequest.model_validate(
        {
            "from": datetime.fromtimestamp(T0 / 1000, UTC),
            "to": datetime.fromtimestamp(end / 1000, UTC),
        }
    )


def count(factory: sessionmaker[Session]) -> int:
    with factory() as session:
        return session.scalar(select(func.count()).select_from(Observation)) or 0


async def test_duplicate_import_is_idempotent_and_matches_live_cycles(
    rig: tuple[sessionmaker[Session], HistoryImport, FakeHAServer],
    tmp_path: Path,
) -> None:
    factory, importer, server = rig
    first = importer.start_import(request())
    assert importer.task is not None
    await importer.task
    result = importer.poll_import(first.id)
    assert result.status is ImportStatus.DONE
    assert result.observations_imported > 0
    inserted = count(factory)
    second = importer.start_import(request())
    assert importer.task is not None
    await importer.task
    again = importer.poll_import(second.id)
    assert again.status is ImportStatus.DONE
    assert again.observations_imported == 0
    assert again.duplicates_skipped == inserted
    assert count(factory) == inserted
    assert all(
        "minimal_response" in call and "no_attributes" in call for call in server.history_requests
    )
    live = make_db(tmp_path, "live")
    seed(live)
    with live.begin() as session:
        session.execute(delete(ConnectionEvent))
    runner = AnalysisRunner(live, RunnerSettings(chunk_ms=HUGE))
    runner.tick(END + settle_of(runner))

    def cycles(sessions: sessionmaker[Session]) -> list[tuple[Any, ...]]:
        with sessions() as session:
            return [
                (
                    c.start_ts,
                    c.end_ts,
                    c.mode,
                    c.end_reason,
                    c.duration_ms,
                    c.complete,
                    c.start_observed,
                )
                for c in session.scalars(select(BurnerCycle).order_by(BurnerCycle.start_ts))
            ]

    assert cycles(factory)
    assert cycles(factory) == cycles(live)
    assert not server.service_calls


async def test_failed_second_block_resumes_from_committed_cursor(
    rig: tuple[sessionmaker[Session], HistoryImport, FakeHAServer],
) -> None:
    factory, importer, server = rig
    server.history_fail_at = 3
    first = importer.start_import(request(T0 + 2 * DAY_MS))
    assert importer.task is not None
    await importer.task
    result = importer.poll_import(first.id)
    assert result.status is ImportStatus.FAILED
    assert result.blocks_done == 1
    inserted = count(factory)
    with factory() as session:
        row = session.get(ImportJob, int(first.id))
        assert row is not None
        assert row.cursor_ts == T0 + DAY_MS
    server.history_fail_at = None
    resumed = importer.start_import(request(T0 + 2 * DAY_MS))
    assert resumed.id == first.id
    assert importer.task is not None
    await importer.task
    result = importer.poll_import(first.id)
    assert result.status is ImportStatus.DONE
    assert result.blocks_done == 2
    assert count(factory) >= inserted
    assert len(server.history_requests) == 5


async def test_api_polling_is_read_only_and_conflicts_are_reported(
    rig: tuple[sessionmaker[Session], HistoryImport, FakeHAServer],
) -> None:
    factory, importer, _ = rig
    app = create_app(Settings.model_validate({}))
    app.state.session_factory, app.state.history_import = factory, importer
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        body = request().model_dump(mode="json", by_alias=True)
        response = await client.post("/api/import", json=body)
        assert response.status_code == 202
        ident = response.json()["id"]
        assert (await client.post("/api/import", json=body)).status_code == 409
        assert importer.task is not None
        await importer.task
        progress = (await client.get(f"/api/import/{ident}")).json()
        assert progress["status"] == "done"
        assert (await client.get(f"/api/import/{ident}")).json() == progress
        assert (await client.get("/api/import")).json()["items"][0] == progress
        assert (await client.get("/api/import/no-such-id")).status_code == 404
        assert (await client.post(f"/api/import/{ident}/cancel")).status_code == 409
        assert (
            await client.post("/api/import", json={**body, "signal_ids": ["missing@boiler"]})
        ).status_code == 422


def test_carry_in_is_poll_and_missing_heartbeats_are_not_invented() -> None:
    entity = "binary_sensor.flame"
    row = make_state(entity, "on", changed=T0 - DAY_MS)
    records = history_records([row], entity, T0, T0 + DAY_MS, END)
    assert records[0].kind is ObservationKind.POLL
    assert records[0].ts == T0
    assert records[0].last_reported_ts == T0 - DAY_MS


async def test_cancel_during_fetch_keeps_cancelled_state_and_uncommitted_rows_out(
    rig: tuple[sessionmaker[Session], HistoryImport, FakeHAServer],
) -> None:
    import asyncio
    from collections.abc import Mapping

    factory, importer, _ = rig
    original = importer.client
    assert original is not None
    fetch = original.history
    entered, release = asyncio.Event(), asyncio.Event()

    class BlockingHistory:
        async def history(
            self, entity_id: str, start: int, end: int, *, heartbeat_expected: bool = False
        ) -> list[Mapping[str, Any]]:
            entered.set()
            await release.wait()
            return await fetch(entity_id, start, end, heartbeat_expected=heartbeat_expected)

    importer.client = BlockingHistory()
    job = importer.start_import(request())
    await entered.wait()
    cancelled = importer.cancel_import(job.id)
    assert cancelled.status is ImportStatus.CANCELLED
    release.set()
    assert importer.task is not None
    await importer.task
    assert importer.poll_import(job.id).status is ImportStatus.CANCELLED
    assert count(factory) == 0


async def test_restart_recovers_checkpoint_and_preserves_heartbeat_response_fields(
    rig: tuple[sessionmaker[Session], HistoryImport, FakeHAServer],
) -> None:
    from cvidee.store.models import SignalMapping

    factory, importer, server = rig
    with factory.begin() as session:
        mapping = session.scalar(select(SignalMapping).where(SignalMapping.role == "flame"))
        assert mapping is not None
        mapping.heartbeat_expected = True
    server.history_fail_at = 3
    job = importer.start_import(request(T0 + 2 * DAY_MS))
    assert importer.task is not None
    await importer.task
    assert importer.poll_import(job.id).blocks_done == 1
    assert any("minimal_response" not in call for call in server.history_requests)
    with factory.begin() as session:
        row = session.get(ImportJob, int(job.id))
        assert row is not None
        row.status = ImportStatus.FETCHING
    server.history_fail_at = None
    restarted = HistoryImport(factory, importer.client, importer.runner)
    await restarted.recover()
    assert restarted.task is not None
    await restarted.task
    assert restarted.poll_import(job.id).status is ImportStatus.DONE
    assert restarted.poll_import(job.id).blocks_done == 2
    assert len(server.history_requests) == 5


def test_later_report_is_a_separate_confirmation_without_backfilling_coverage() -> None:
    entity = "sensor.flow"
    row = make_state(entity, "45", changed=T0 - 60_000, reported=T0 + 30_000)
    records = history_records([row], entity, T0, T0 + 60_000, END)
    assert [record.kind for record in records] == [ObservationKind.POLL, ObservationKind.CONFIRM]
    assert records[0].last_reported_ts is None
    assert records[1].ts == T0 + 30_000
    future = make_state(entity, "45", changed=T0 - 60_000, reported=T0 + DAY_MS)
    assert history_records([future], entity, T0, T0 + 60_000, END)[0].last_reported_ts is None
