"""Fake Home Assistant: WebSocket API (auth, subscribe_events, get_states, ping, call_service,
fire_event) and the REST state endpoints, for ingest tests (#17)."""

from __future__ import annotations

import json
import socket
from datetime import UTC, datetime
from typing import Any

from aiohttp import WSMsgType, web

TOKEN = "test-token"


def iso(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=UTC).isoformat()


def make_state(
    entity_id: str,
    state: str,
    *,
    changed: int,
    updated: int | None = None,
    reported: int | None = None,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    updated = changed if updated is None else updated
    reported = updated if reported is None else reported
    return {
        "entity_id": entity_id,
        "state": state,
        "attributes": attributes or {},
        "last_changed": iso(changed),
        "last_updated": iso(updated),
        "last_reported": iso(reported),
    }


class FakeHAServer:
    def __init__(self) -> None:
        self.states: dict[str, dict[str, Any]] = {}
        self.fired_events: list[dict[str, Any]] = []
        self.service_calls: list[dict[str, Any]] = []
        self.connection_count = 0
        self._port = 0
        self._runner: web.AppRunner | None = None
        self._sockets: list[web.WebSocketResponse] = []
        self._subscription: dict[web.WebSocketResponse, int] = {}

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    async def start(self) -> None:
        """Start (again on the same port after :meth:`stop`)."""
        if not self._port:
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                self._port = s.getsockname()[1]
        app = web.Application()
        app.router.add_get("/api/websocket", self._ws)
        app.router.add_get("/api/states", self._rest_states)
        app.router.add_get("/api/states/{entity_id}", self._rest_state)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        await web.TCPSite(self._runner, "127.0.0.1", self._port).start()

    async def stop(self) -> None:
        """Drop all connections and refuse new ones (HA gone)."""
        for ws in list(self._sockets):
            await ws.close()
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def push_state_changed(
        self, entity_id: str, new: dict[str, Any] | None, old: dict[str, Any] | None, fired: int
    ) -> None:
        """Update the state table and send ``state_changed`` to subscribers."""
        if new is None:
            self.states.pop(entity_id, None)
        else:
            self.states[entity_id] = new
        for ws, sub_id in list(self._subscription.items()):
            await ws.send_json(
                {
                    "type": "event",
                    "id": sub_id,
                    "event": {
                        "event_type": "state_changed",
                        "data": {"entity_id": entity_id, "old_state": old, "new_state": new},
                        "time_fired": iso(fired),
                    },
                }
            )

    # ------------------------------------------------------------------ handlers

    async def _ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.connection_count += 1
        self._sockets.append(ws)
        try:
            await ws.send_json({"type": "auth_required", "ha_version": "2026.1.0"})
            auth = await ws.receive_json()
            if auth.get("access_token") != TOKEN:
                await ws.send_json({"type": "auth_invalid", "message": "Invalid access token"})
                return ws
            await ws.send_json({"type": "auth_ok", "ha_version": "2026.1.0"})
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                await self._handle(ws, json.loads(msg.data))
        finally:
            self._sockets.remove(ws)
            self._subscription.pop(ws, None)
        return ws

    async def _handle(self, ws: web.WebSocketResponse, msg: dict[str, Any]) -> None:
        mid, kind = msg["id"], msg["type"]
        if kind == "ping":
            await ws.send_json({"type": "pong", "id": mid})
            return
        result: Any
        if kind == "subscribe_events":
            self._subscription[ws] = mid
            result = None
        elif kind == "get_states":
            result = list(self.states.values())
        elif kind == "fire_event":
            self.fired_events.append(msg)
            result = {"context": {}}
        elif kind == "call_service":
            self.service_calls.append(msg)
            result = {"context": {}}
        else:
            await ws.send_json(
                {"type": "result", "id": mid, "success": False, "error": {"code": "unknown"}}
            )
            return
        await ws.send_json({"type": "result", "id": mid, "success": True, "result": result})

    async def _rest_states(self, request: web.Request) -> web.Response:
        if request.headers.get("Authorization") != f"Bearer {TOKEN}":
            return web.Response(status=401)
        return web.json_response(list(self.states.values()))

    async def _rest_state(self, request: web.Request) -> web.Response:
        if request.headers.get("Authorization") != f"Bearer {TOKEN}":
            return web.Response(status=401)
        state = self.states.get(request.match_info["entity_id"])
        if state is None:
            return web.Response(status=404)
        return web.json_response(state)
