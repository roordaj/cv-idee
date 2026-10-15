"""Fake HA REST/Supervisor endpoints and in-memory MQTT birth delivery."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import aiomqtt
import pytest
from aiohttp import web
from pydantic import SecretStr

from cvidee.config import Settings, fetch_mqtt_settings_from_supervisor
from cvidee.ha_export.entities import ENTITIES
from cvidee.ha_export.service import ExportService
from tests.runner.test_runner import make_db


async def local_server(app: web.Application) -> tuple[web.AppRunner, str]:
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 0).start()
    return runner, f"http://127.0.0.1:{runner.addresses[0][1]}"


async def test_rest_republishes_owned_states_on_restart(tmp_path: Path) -> None:
    received: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()

    async def health(request: web.Request) -> web.Response:
        return web.json_response({"message": "API running"})

    async def state(request: web.Request) -> web.Response:
        assert request.headers["Authorization"] == "Bearer fake-test-token"
        body = await request.json()
        await received.put((request.match_info["entity_id"], body))
        return web.json_response(body, status=201)

    app = web.Application()
    app.router.add_get("/api/", health)
    app.router.add_post("/api/states/{entity_id}", state)
    runner, url = await local_server(app)
    service = ExportService(
        Settings(HA_URL=url, HA_TOKEN=SecretStr("fake-test-token")),
        make_db(tmp_path),
        interval_s=0.01,
    )
    task = asyncio.create_task(service._rest_publish_loop())
    try:
        async with asyncio.timeout(5):
            initial = [await received.get() for _ in ENTITIES]
        assert {entity for entity, _ in initial} == {e.entity_id for e in ENTITIES}
        assert initial[0][1]["state"] == "unknown"
        service._restart.set()
        async with asyncio.timeout(5):
            after_restart = [await received.get() for _ in ENTITIES]
        assert {entity for entity, _ in after_restart} == {e.entity_id for e in ENTITIES}
        assert service.connected
    finally:
        service.stop_event.set()
        await task
        await runner.cleanup()


async def test_supervisor_service_lookup_and_missing_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    available = True

    async def mqtt(request: web.Request) -> web.Response:
        assert request.headers["Authorization"] == "Bearer fake-supervisor-token"
        if not available:
            return web.json_response({"result": "error"}, status=400)
        return web.json_response(
            {
                "result": "ok",
                "data": {
                    "host": "mosquitto",
                    "port": 1883,
                    "username": "test",
                    "password": "fake-password",
                },
            }
        )

    app = web.Application()
    app.router.add_get("/services/mqtt", mqtt)
    runner, url = await local_server(app)
    monkeypatch.setattr("cvidee.config.SUPERVISOR_API_URL", url)
    try:
        settings = Settings(SUPERVISOR_TOKEN=SecretStr("fake-supervisor-token"))
        broker = await fetch_mqtt_settings_from_supervisor(settings)
        assert broker is not None
        assert (broker.host, broker.port, broker.username) == ("mosquitto", 1883, "test")
        available = False
        assert await fetch_mqtt_settings_from_supervisor(settings) is None
    finally:
        await runner.cleanup()


async def test_mqtt_birth_republishes_discovery_without_publishing_birth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Message:
        topic = "homeassistant/status"
        payload = b"online"

    async def messages() -> AsyncIterator[Message]:
        yield Message()

    class FakeClient:
        pass

    fake = FakeClient()
    fake.messages = messages()  # type: ignore[attr-defined]
    service = ExportService(Settings(), make_db(tmp_path))
    discovery = AsyncMock()
    monkeypatch.setattr(service, "_discovery", discovery)
    await service._births(cast(aiomqtt.Client, fake))
    discovery.assert_awaited_once_with(fake)


async def test_rest_watcher_reads_restart_events(tmp_path: Path) -> None:
    subscribed = asyncio.Event()

    async def websocket(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_json({"type": "auth_required"})
        assert (await ws.receive_json())["type"] == "auth"
        await ws.send_json({"type": "auth_ok"})
        subscription = await ws.receive_json()
        assert subscription["type"] == "subscribe_events"
        assert subscription["event_type"] == "homeassistant_started"
        subscribed.set()
        await ws.send_json({"type": "event", "event": {"event_type": "homeassistant_started"}})
        async for _ in ws:
            pass
        return ws

    app = web.Application()
    app.router.add_get("/api/websocket", websocket)
    runner, url = await local_server(app)
    service = ExportService(
        Settings(HA_URL=url, HA_TOKEN=SecretStr("fake-test-token")), make_db(tmp_path)
    )
    task = asyncio.create_task(service._watch_ha_start())
    try:
        async with asyncio.timeout(5):
            await subscribed.wait()
            await service._restart.wait()
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await runner.cleanup()
