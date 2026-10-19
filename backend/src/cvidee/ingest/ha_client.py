"""Home Assistant client: WebSocket live subscription, REST reads, reconnect (ADR-003 §5.1).

The client only transports. Mapping to observations lives in :mod:`cvidee.ingest.service`.

Read-only guard (AGENTS.md): :meth:`AiohttpHAClient.call_service` accepts ``notify`` services
only and :meth:`AiohttpHAClient.fire_event` accepts ``cv_analyse_finding`` only.

Connection protocol per attempt: authenticate -> ``subscribe_events(state_changed)`` ->
``get_states``. ``on_connected`` is called with the poll moment and the (tracked) states only
after all three succeeded; events arriving in between are buffered and delivered right
after. A failed attempt produces no event. ``on_disconnected`` is called exactly once per
loss, with the time of the last message received from HA.
"""

from __future__ import annotations

import asyncio
import logging
import statistics
import time
from collections import deque
from collections.abc import Awaitable, Callable, Collection, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlencode

import aiohttp

from cvidee.config import HAConnection

logger = logging.getLogger(__name__)

__all__ = [
    "ALLOWED_EVENT_TYPES",
    "ALLOWED_SERVICE_DOMAINS",
    "AiohttpHAClient",
    "HAAuthError",
    "HAClient",
    "HAError",
    "HAListener",
    "HAState",
    "HAUnavailableError",
    "StateChangedEvent",
    "now_ms",
    "parse_ha_time",
]

ALLOWED_SERVICE_DOMAINS = frozenset({"notify"})
ALLOWED_EVENT_TYPES = frozenset({"cv_analyse_finding"})

PING_INTERVAL_S = 20.0
PING_TIMEOUT_S = 10.0
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MS = timedelta(milliseconds=1)


class HAError(Exception):
    """Base class for Home Assistant client errors."""


class HAAuthError(HAError):
    """Authentication was rejected."""


class HAUnavailableError(HAError):
    """Home Assistant is not reachable (or the request failed)."""


class HANotFoundError(HAUnavailableError):
    """HTTP 404."""


def now_ms() -> int:
    return time.time_ns() // 1_000_000


def parse_ha_time(value: str | None) -> int | None:
    """ISO timestamp from HA -> UTC ms epoch, rounded down to whole milliseconds."""
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return (dt - _EPOCH) // _MS


@dataclass(frozen=True, slots=True)
class HAState:
    entity_id: str
    state: str
    attributes: Mapping[str, Any] = field(default_factory=dict)
    last_changed: int | None = None
    last_updated: int | None = None
    last_reported: int | None = None

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> HAState:
        return cls(
            entity_id=raw["entity_id"],
            state=str(raw.get("state")),
            attributes=raw.get("attributes") or {},
            last_changed=parse_ha_time(raw.get("last_changed")),
            last_updated=parse_ha_time(raw.get("last_updated")),
            last_reported=parse_ha_time(raw.get("last_reported")),
        )


@dataclass(frozen=True, slots=True)
class StateChangedEvent:
    entity_id: str
    time_fired: int
    old_state: HAState | None
    new_state: HAState | None


class HAListener(Protocol):
    async def on_connected(self, poll_ts: int, states: list[HAState]) -> None: ...

    async def on_disconnected(self, ts: int) -> None: ...

    async def on_state_changed(self, event: StateChangedEvent) -> None: ...


class HAClient(Protocol):
    """What the rest of the application needs from Home Assistant."""

    @property
    def clock_offset_ms(self) -> int: ...

    @property
    def connected(self) -> bool: ...

    async def run(self, listener: HAListener) -> None:
        """Connect, subscribe and reconnect with backoff until cancelled."""
        ...

    async def get_states(self) -> list[HAState]: ...

    async def get_state(self, entity_id: str) -> HAState | None: ...

    async def call_service(self, domain: str, service: str, data: Mapping[str, Any]) -> None: ...

    async def fire_event(self, event_type: str, data: Mapping[str, Any]) -> None: ...

    async def close(self) -> None: ...


class AiohttpHAClient:
    """:class:`HAClient` on aiohttp."""

    def __init__(
        self,
        connection: HAConnection,
        *,
        tracked: Callable[[], Collection[str]],
        clock: Callable[[], int] = now_ms,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        backoff_initial_s: float = 1.0,
        backoff_max_s: float = 60.0,
        ping_interval_s: float = PING_INTERVAL_S,
        ping_timeout_s: float = PING_TIMEOUT_S,
    ) -> None:
        self._conn = connection
        self._tracked = tracked
        self._clock = clock
        self._sleep = sleep
        self._backoff_initial = backoff_initial_s
        self._backoff_max = backoff_max_s
        self._ping_interval = ping_interval_s
        self._ping_timeout = ping_timeout_s
        self._http: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._next_id = 1
        self._pending: dict[int, asyncio.Future[Mapping[str, Any]]] = {}
        self._ready = False  # on_connected done, events flow directly
        self._up_reported = False  # on_connected was called without a matching on_disconnected
        self._buffer: list[StateChangedEvent] = []
        self._last_received = 0
        self._listener: HAListener | None = None
        self._subscription_id = 0
        self._clock_offsets: deque[int] = deque(maxlen=100)
        self._clock_warning_active = False

    # ------------------------------------------------------------------ public

    @property
    def clock_offset_ms(self) -> int:
        return int(statistics.median(self._clock_offsets)) if self._clock_offsets else 0

    @property
    def connected(self) -> bool:
        return self._ready

    async def close(self) -> None:
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        if self._http is not None:
            await self._http.close()
            self._http = None

    async def get_states(self) -> list[HAState]:
        if self._ready:
            return await self._ws_get_states()
        return [HAState.from_json(s) for s in await self._rest_get("/states")]

    async def get_state(self, entity_id: str) -> HAState | None:
        try:
            raw = await self._rest_get(f"/states/{entity_id}")
        except HANotFoundError:
            return None
        return HAState.from_json(raw)

    async def history(
        self, entity_id: str, start: int, end: int, *, heartbeat_expected: bool = False
    ) -> list[Mapping[str, Any]]:
        """Read recorder history; reduced rows inherit the requested entity id."""
        params = {
            "filter_entity_id": entity_id,
            "end_time": datetime.fromtimestamp(end / 1000, UTC).isoformat(),
        }
        if not heartbeat_expected:
            params.update({"minimal_response": "", "no_attributes": ""})
        stamp = datetime.fromtimestamp(start / 1000, UTC).isoformat()
        raw = await self._rest_get(f"/history/period/{stamp}?{urlencode(params)}")
        if not isinstance(raw, list):
            raise HAUnavailableError("Invalid history response")
        rows: list[Mapping[str, Any]] = []
        for group in raw:
            if not isinstance(group, list):
                raise HAUnavailableError("Invalid history group")
            for item in group:
                if not isinstance(item, dict) or item.get("entity_id", entity_id) != entity_id:
                    raise HAUnavailableError("Invalid history state")
                rows.append({**item, "entity_id": entity_id})
        return rows

    async def call_service(self, domain: str, service: str, data: Mapping[str, Any]) -> None:
        if domain not in ALLOWED_SERVICE_DOMAINS:
            raise HAError(f"Service domain {domain!r} is not allowed (read-only app)")
        await self._request(
            {"type": "call_service", "domain": domain, "service": service, "service_data": data}
        )

    async def fire_event(self, event_type: str, data: Mapping[str, Any]) -> None:
        if event_type not in ALLOWED_EVENT_TYPES:
            raise HAError(f"Event type {event_type!r} is not allowed (read-only app)")
        await self._request({"type": "fire_event", "event_type": event_type, "event_data": data})

    # --------------------------------------------------------------------- REST

    def _session(self) -> aiohttp.ClientSession:
        if self._http is None or self._http.closed:
            self._http = aiohttp.ClientSession()
        return self._http

    async def _rest_get(self, path: str) -> Any:
        url = self._conn.rest_url.rstrip("/") + path
        headers = {"Authorization": f"Bearer {self._conn.token.get_secret_value()}"}
        try:
            async with self._session().get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 404:
                    raise HANotFoundError(f"GET {path}: HTTP 404")
                if resp.status != 200:
                    raise HAUnavailableError(f"GET {path} failed: HTTP {resp.status}")
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise HAUnavailableError(f"GET {path} failed: {exc}") from exc

    # ---------------------------------------------------------------- WebSocket

    async def _request(self, payload: dict[str, Any]) -> Mapping[str, Any]:
        ws = self._ws
        if ws is None or ws.closed:
            raise HAUnavailableError("WebSocket not connected")
        msg_id = self._next_id
        self._next_id += 1
        future: asyncio.Future[Mapping[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = future
        try:
            await ws.send_json({**payload, "id": msg_id})
            reply = await future
        except (aiohttp.ClientError, ConnectionError) as exc:
            raise HAUnavailableError(str(exc)) from exc
        finally:
            self._pending.pop(msg_id, None)
        if reply.get("type") == "result" and not reply.get("success", False):
            raise HAError(f"{payload['type']} failed: {reply.get('error')}")
        return reply

    async def _ws_get_states(self) -> list[HAState]:
        reply = await self._request({"type": "get_states"})
        return [HAState.from_json(s) for s in reply.get("result") or []]

    async def run(self, listener: HAListener) -> None:
        """Connect and reconnect forever (exponential backoff) until cancelled."""
        self._listener = listener
        delay = self._backoff_initial
        try:
            while True:
                try:
                    await self._session_once(listener)
                except HAAuthError:
                    logger.error("Home Assistant rejected the access token")
                except (HAError, aiohttp.ClientError, OSError, TimeoutError) as exc:
                    logger.warning("Home Assistant connection ended: %s", exc)
                if self._up_reported:
                    self._up_reported = False
                    await listener.on_disconnected(self._last_received)
                    delay = self._backoff_initial
                logger.info("Reconnecting to Home Assistant in %.1f s", delay)
                await self._sleep(delay)
                delay = min(delay * 2, self._backoff_max)
        except asyncio.CancelledError:
            if self._up_reported:
                self._up_reported = False
                await listener.on_disconnected(self._last_received)
            raise
        finally:
            self._ready = False

    async def _session_once(self, listener: HAListener) -> None:
        async with self._session().ws_connect(self._conn.websocket_url, max_msg_size=0) as ws:
            self._ws = ws
            self._buffer = []
            self._ready = False
            reader: asyncio.Task[None] | None = None
            pinger: asyncio.Task[None] | None = None
            try:
                await self._authenticate(ws)
                reader = asyncio.create_task(self._read(ws))
                sub = await self._request(
                    {"type": "subscribe_events", "event_type": "state_changed"}
                )
                self._subscription_id = int(sub["id"])
                poll_ts = self._clock()
                tracked = self._tracked()
                states = [s for s in await self._ws_get_states() if s.entity_id in tracked]
                await listener.on_connected(poll_ts, states)
                self._up_reported = True
                self._ready = True
                buffered, self._buffer = self._buffer, []
                for event in buffered:
                    await listener.on_state_changed(event)
                pinger = asyncio.create_task(self._ping(ws))
                await reader
            finally:
                self._ready = False
                tasks = [t for t in (pinger, reader) if t is not None]
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                self._ws = None
                self._fail_pending()

    async def _authenticate(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        first = await ws.receive_json()
        self._last_received = self._clock()
        if first.get("type") != "auth_required":
            raise HAError(f"Unexpected first message: {first.get('type')}")
        await ws.send_json({"type": "auth", "access_token": self._conn.token.get_secret_value()})
        reply = await ws.receive_json()
        self._last_received = self._clock()
        if reply.get("type") == "auth_invalid":
            raise HAAuthError(reply.get("message", "auth_invalid"))
        if reply.get("type") != "auth_ok":
            raise HAError(f"Unexpected auth reply: {reply.get('type')}")

    async def _read(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        try:
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                self._last_received = self._clock()
                data = msg.json()
                kind = data.get("type")
                if kind in ("result", "pong"):
                    future = self._pending.get(data.get("id", -1))
                    if future is not None and not future.done():
                        future.set_result(data)
                elif kind == "event" and data.get("id") == self._subscription_id:
                    await self._on_event(data["event"], self._last_received)
        finally:
            self._fail_pending()

    async def _on_event(self, raw: Mapping[str, Any], received_at: int | None = None) -> None:
        if raw.get("event_type") != "state_changed":
            return
        payload = raw["data"]
        event_ts = parse_ha_time(raw.get("time_fired"))
        received = self._last_received if received_at is None else received_at
        if event_ts is not None:
            self._clock_offsets.append(received - event_ts)
            offset = self.clock_offset_ms
            warning = abs(offset) > 2_000
            if warning != self._clock_warning_active:
                if warning:
                    logger.warning("Home Assistant clock offset exceeds 2 s: %d ms", offset)
                else:
                    logger.info("Home Assistant clock offset returned within 2 s: %d ms", offset)
                self._clock_warning_active = warning
        entity_id = payload["entity_id"]
        if entity_id not in self._tracked():
            return
        old, new = payload.get("old_state"), payload.get("new_state")
        event = StateChangedEvent(
            entity_id=entity_id,
            time_fired=parse_ha_time(raw.get("time_fired")) or self._clock(),
            old_state=HAState.from_json(old) if old else None,
            new_state=HAState.from_json(new) if new else None,
        )
        if not self._ready:
            self._buffer.append(event)
        elif self._listener is not None:
            await self._listener.on_state_changed(event)

    def _fail_pending(self) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(HAUnavailableError("connection lost"))

    async def _ping(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """HA-level ping/pong (a pong counts as a received message for the down timestamp)."""
        while not ws.closed:
            await asyncio.sleep(self._ping_interval)
            try:
                await asyncio.wait_for(self._request({"type": "ping"}), self._ping_timeout)
            except (TimeoutError, HAError):
                logger.warning("Home Assistant ping timed out; closing connection")
                await ws.close()
                return
