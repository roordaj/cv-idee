"""MQTT discovery export, reconnect and guarded REST-state fallback."""

import asyncio
import contextlib
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any, Literal

import aiohttp
import aiomqtt
from sqlalchemy.orm import Session, sessionmaker

from cvidee.api.schemas.notifications import HaExport, HaExportEntity
from cvidee.config import Settings, fetch_mqtt_settings_from_supervisor
from cvidee.ha_export.entities import (
    BIRTH_TOPIC,
    ENTITIES,
    STATUS_TOPIC,
    ExportValue,
    validate_publish_topic,
)
from cvidee.ha_export.summary import read_summary

logger = logging.getLogger(__name__)


class ExportService:
    """A separate task: broker outages never roll back or stop analysis."""

    def __init__(
        self, settings: Settings, sessions: sessionmaker[Session], *, interval_s: float = 60
    ) -> None:
        self.settings = settings
        self.sessions = sessions
        self.interval_s = interval_s
        self.transport: Literal["mqtt", "fallback", "none"] = "none"
        self.connected = False
        self.updated_at: datetime | None = None
        self.values: dict[str, ExportValue] = {}
        self.stop_event = asyncio.Event()
        self.ready = asyncio.Event()
        self.task: asyncio.Task[None] | None = None
        self._sent: dict[str, str] = {}
        self._restart = asyncio.Event()

    def snapshot(self) -> HaExport:
        return HaExport(
            transport=self.transport,
            connected=self.connected,
            updated_at=self.updated_at,
            entities=[
                HaExportEntity(
                    entity_id=e.entity_id,
                    state=self.values.get(e.key, ExportValue("unknown")).state,
                    display=self.values.get(e.key, ExportValue("unknown")).state.replace(".", ","),
                    unit=e.unit,
                )
                for e in ENTITIES
            ],
        )

    def _read(self) -> dict[str, ExportValue]:
        with self.sessions() as session:
            return read_summary(session, time.time_ns() // 1_000_000)

    async def start(self) -> None:
        self.task = asyncio.create_task(self.run(), name="ha-export")

    async def stop(self) -> None:
        self.stop_event.set()
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
        self.connected = False

    async def _publish(
        self, client: aiomqtt.Client, topic: str, payload: str, *, force: bool = False
    ) -> None:
        validate_publish_topic(topic)
        if force or self._sent.get(topic) != payload:
            await client.publish(topic, payload, qos=1, retain=True)
            self._sent[topic] = payload

    async def remove_entity(self, client: aiomqtt.Client, component: str, key: str) -> None:
        """Remove an obsolete owned discovery entity with an empty retained config."""
        await self._publish(
            client, f"homeassistant/{component}/cv_analyse/{key}/config", "", force=True
        )

    async def _discovery(self, client: aiomqtt.Client) -> None:
        for entity in ENTITIES:
            await self._publish(
                client,
                entity.config_topic,
                json.dumps(entity.discovery(self.settings.export_url), ensure_ascii=False),
                force=True,
            )

    async def _refresh(self, client: aiomqtt.Client) -> None:
        self.values = await asyncio.to_thread(self._read)
        for entity in ENTITIES:
            value = self.values[entity.key]
            # Numeric MQTT sensors require the literal None to clear an old value.
            state = "None" if value.state == "unknown" else value.state
            await self._publish(
                client,
                entity.attributes_topic,
                json.dumps(value.attributes, ensure_ascii=False, sort_keys=True),
            )
            await self._publish(client, entity.state_topic, state)
        self.updated_at = datetime.now(UTC)

    async def run(self) -> None:
        delay = 1.0
        while not self.stop_event.is_set():
            try:
                broker = self.settings.mqtt_settings_from_env()
                if broker is None and self.settings.supervisor_token:
                    broker = await fetch_mqtt_settings_from_supervisor(self.settings)
                if broker is None:
                    self.transport = "fallback" if self.settings.ha_configured else "none"
                    await self._rest_loop()
                    return
                self.transport = "mqtt"
                async with aiomqtt.Client(
                    hostname=broker.host,
                    port=broker.port,
                    username=broker.username,
                    password=broker.password.get_secret_value() if broker.password else None,
                    identifier="cv_analyse",
                    will=aiomqtt.Will(STATUS_TOPIC, "offline", qos=1, retain=True),
                ) as client:
                    self._sent.clear()
                    await self._publish(client, STATUS_TOPIC, "offline", force=True)
                    await client.subscribe(BIRTH_TOPIC, qos=1)
                    await self._discovery(client)
                    await self._refresh(client)
                    await self._publish(client, STATUS_TOPIC, "online", force=True)
                    self.connected = True
                    self.ready.set()
                    delay = 1.0
                    reader = asyncio.create_task(self._births(client))
                    try:
                        while not self.stop_event.is_set():
                            done, _ = await asyncio.wait({reader}, timeout=self.interval_s)
                            if done:
                                await reader
                                raise aiomqtt.MqttError("MQTT message stream ended")
                            await self._refresh(client)
                    finally:
                        reader.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await reader
                        with contextlib.suppress(aiomqtt.MqttError):
                            await self._publish(client, STATUS_TOPIC, "offline", force=True)
            except asyncio.CancelledError:
                raise
            except (aiomqtt.MqttError, aiohttp.ClientError, TimeoutError, ValueError):
                logger.warning(
                    "HA export unavailable; retrying without changing analysis", exc_info=False
                )
            except Exception:
                logger.exception("HA export refresh failed")
            finally:
                self.connected = False
                self.ready.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.stop_event.wait(), timeout=delay)
            delay = min(delay * 2, 60)

    async def _births(self, client: aiomqtt.Client) -> None:
        async for message in client.messages:
            if str(message.topic) == BIRTH_TOPIC and bytes(message.payload).decode() == "online":
                await self._discovery(client)

    async def _watch_ha_start(self) -> None:
        connection = self.settings.ha_connection()
        while not self.stop_event.is_set():
            try:
                async with (
                    aiohttp.ClientSession() as http,
                    http.ws_connect(connection.websocket_url, heartbeat=20) as ws,
                ):
                    await ws.receive_json()
                    await ws.send_json(
                        {"type": "auth", "access_token": connection.token.get_secret_value()}
                    )
                    auth = await ws.receive_json()
                    if auth.get("type") != "auth_ok":
                        raise ValueError("HA export restart subscription authentication failed")
                    await ws.send_json(
                        {"id": 1, "type": "subscribe_events", "event_type": "homeassistant_started"}
                    )
                    # Reconnection also means the previous retained REST states may be gone.
                    self._restart.set()
                    async for message in ws:
                        if message.type == aiohttp.WSMsgType.TEXT:
                            data = message.json()
                            if data.get("type") == "event":
                                self._restart.set()
            except (aiohttp.ClientError, TimeoutError, ValueError):
                logger.warning("HA restart watcher disconnected; retrying")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.stop_event.wait(), timeout=5)

    async def _rest_loop(self) -> None:
        watcher = asyncio.create_task(self._watch_ha_start())
        try:
            await self._rest_publish_loop()
        finally:
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher

    async def _rest_publish_loop(self) -> None:
        if not self.settings.ha_configured:
            return
        connection = self.settings.ha_connection()
        headers = {"Authorization": f"Bearer {connection.token.get_secret_value()}"}
        async with aiohttp.ClientSession(
            headers=headers, timeout=aiohttp.ClientTimeout(total=20)
        ) as http:
            previous_up = False
            last_full = 0.0
            while not self.stop_event.is_set():
                try:
                    # A failed reachability check forces all owned states on recovery.
                    async with http.get(f"{connection.rest_url}/") as response:
                        response.raise_for_status()
                    now = time.monotonic()
                    force = not previous_up or self._restart.is_set() or now - last_full >= 300
                    self._restart.clear()
                    self.values = await asyncio.to_thread(self._read)
                    for entity in ENTITIES:
                        value = self.values[entity.key]
                        payload: dict[str, Any] = {
                            "state": value.state,
                            "attributes": {"friendly_name": entity.name, **value.attributes},
                        }
                        if entity.unit:
                            payload["attributes"]["unit_of_measurement"] = entity.unit
                        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
                        if force or self._sent.get(entity.entity_id) != encoded:
                            # Only our summary entities; never services or device entities.
                            async with http.post(
                                f"{connection.rest_url}/states/{entity.entity_id}", json=payload
                            ) as response:
                                response.raise_for_status()
                            self._sent[entity.entity_id] = encoded
                    if force:
                        last_full = now
                    previous_up = self.connected = True
                    self.updated_at = datetime.now(UTC)
                except (aiohttp.ClientError, TimeoutError):
                    previous_up = self.connected = False
                    logger.warning("HA REST export unavailable; retrying")
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self.stop_event.wait(), timeout=self.interval_s)
