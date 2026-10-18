"""HA summary ownership, freshness and retained broker behaviour."""

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import aiomqtt
import httpx
import pytest
from pydantic import SecretStr

from cvidee.config import Settings
from cvidee.ha_export.entities import ENTITIES, STATUS_TOPIC, ExportValue, validate_publish_topic
from cvidee.ha_export.service import ExportService
from cvidee.ha_export.summary import read_summary
from cvidee.main import create_app
from tests.runner.test_runner import T0, make_db


def test_discovery_is_owned_stable_and_has_no_control_topics() -> None:
    for entity in ENTITIES:
        validate_publish_topic(entity.config_topic)
        config = entity.discovery("http://localhost:8099/instellingen")
        assert config["unique_id"] == f"cv_analyse_{entity.key}"
        assert config["default_entity_id"] == entity.entity_id
        assert config["device"]["identifiers"] == ["cv_analyse"]
        assert config["availability_topic"] == STATUS_TOPIC
        assert not any("command" in key for key in config)
        validate_publish_topic(config["state_topic"])
        validate_publish_topic(config["json_attributes_topic"])


@pytest.mark.parametrize(
    "topic",
    [
        "other/state",
        "cv_analyse/+/state",
        "homeassistant/status",
        "homeassistant/switch/other/key/config",
        "homeassistant/sensor/cv_analyse/key/set",
        "cv_analyse/../#",
    ],
)
def test_foreign_topics_rejected(topic: str) -> None:
    with pytest.raises(ValueError, match="CV-analyse topics"):
        validate_publish_topic(topic)


def test_unconfigured_summary_is_explicitly_unknown(tmp_path: Path) -> None:
    factory = make_db(tmp_path)
    with factory() as session:
        values = read_summary(session, T0)
    assert values["starts_per_uur"].state == "unknown"
    assert values["korte_cycli_6u"].state == "unknown"
    assert values["bedrijfsmodus"].state == "onbekend"
    assert float(values["gegevensdekking"].state) == 0
    assert values["onvoldoende_gegevens"].state == "on"


async def test_export_route_uses_live_service(tmp_path: Path) -> None:
    app = create_app(Settings())
    service = ExportService(Settings(), make_db(tmp_path))
    service.transport = "mqtt"
    service.values = {"starts_per_uur": ExportValue("4.5")}
    app.state.ha_export = service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/ha/export")
    assert response.status_code == 200
    body = response.json()
    assert body["transport"] == "mqtt"
    assert not body["connected"]
    assert body["entities"][0]["state"] == "4.5"
    assert body["entities"][0]["display"] == "4,5"


@pytest.mark.skipif(not os.getenv("CVIDEE_TEST_MQTT_HOST"), reason="requires dev Mosquitto broker")
async def test_mosquitto_retained_discovery_and_shutdown(tmp_path: Path) -> None:
    settings = Settings(
        MQTT_HOST=os.environ["CVIDEE_TEST_MQTT_HOST"],
        MQTT_USER="dev",
        MQTT_PASSWORD=SecretStr("dev"),
    )
    service = ExportService(settings, make_db(tmp_path), interval_s=0.1)
    await service.start()
    try:
        async with asyncio.timeout(10):
            await service.ready.wait()
        async with aiomqtt.Client(
            settings.mqtt_host or "localhost", username="dev", password="dev"
        ) as subscriber:
            await subscriber.subscribe("homeassistant/+/cv_analyse/+/config")
            await subscriber.subscribe("cv_analyse/#")
            retained: dict[str, Any] = {}
            async with asyncio.timeout(5):
                async for message in subscriber.messages:
                    if message.retain:
                        retained[str(message.topic)] = bytes(message.payload).decode()
                    if len(retained) == 25:
                        break
            assert retained[STATUS_TOPIC] == "online"
            assert retained["cv_analyse/starts_per_uur/state"] == "None"
            for entity in ENTITIES:
                config = json.loads(retained[entity.config_topic])
                assert config["unique_id"] == f"cv_analyse_{entity.key}"
                assert config["device"]["name"] == "CV-analyse"
            await service.remove_entity(subscriber, "sensor", "obsolete")
        await service.stop()
        async with aiomqtt.Client(
            settings.mqtt_host or "localhost", username="dev", password="dev"
        ) as subscriber:
            await subscriber.subscribe(STATUS_TOPIC)
            async with asyncio.timeout(5):
                message = await anext(subscriber.messages)
            assert bytes(message.payload) == b"offline"
            assert message.retain
    finally:
        await service.stop()


def test_summary_uses_real_reports_and_drops_values_immediately_on_outage(tmp_path: Path) -> None:
    from sqlalchemy import select

    from cvidee.analysis.types import ConnectionEvent, ConnectionSource, Role
    from cvidee.signals.catalog import sync_catalogue
    from cvidee.store.enums import ObservationKind, ObservationOrigin, ValueKind
    from cvidee.store.models import SignalMapping, SourceEntity
    from cvidee.store.observations import SqlObservationRepository
    from cvidee.store.records import ObservationRecord

    factory = make_db(tmp_path)
    end = T0 + 7 * 3_600_000
    roles = (Role.FLAME, Role.OPERATING_MODE, Role.HEAT_DEMAND)
    records = []
    for ts in range(T0, end, 10_000):
        for role in roles:
            state = (
                "on"
                if role == Role.HEAT_DEMAND
                else "1"
                if role == Role.OPERATING_MODE
                else "on"
                if (ts - T0) % 240_000 < 120_000
                else "off"
            )
            records.append(
                ObservationRecord(
                    entity_id=f"sensor.test_{role.value}",
                    ts=ts,
                    state=state,
                    value_num=None,
                    kind=ObservationKind.CHANGE if ts % 120_000 == 0 else ObservationKind.CONFIRM,
                    origin=ObservationOrigin.LIVE,
                    received_at_ts=ts,
                    last_reported_ts=ts,
                )
            )
    with factory.begin() as session:
        sync_catalogue(session)
        repo = SqlObservationRepository(session)
        repo.add_observations(records)
        repo.add_connection_events([ConnectionEvent(T0, ConnectionSource.WS, True)])
        for role in roles:
            entity = session.scalar(
                select(SourceEntity).where(SourceEntity.entity_id == f"sensor.test_{role.value}")
            )
            assert entity is not None
            session.add(
                SignalMapping(
                    role=role.value,
                    scope_key="",
                    source_entity_id=entity.id,
                    kind=ValueKind.REPORTED,
                    heartbeat_expected=True,
                    max_age_ms=30_000,
                    valid_from_ts=T0,
                    created_at_ts=T0,
                )
            )
    with factory() as session:
        values = read_summary(session, end)
    assert float(values["starts_per_uur"].state) > 0
    assert float(values["korte_cycli_6u"].state) > 0
    assert values["bedrijfsmodus"].state == "cv"
    assert values["onvoldoende_gegevens"].state == "off"
    # Missing heat demand must not turn an unclassifiable stop into zero short cycles.
    with factory.begin() as session:
        demand_mapping = session.scalar(
            select(SignalMapping).where(SignalMapping.role == Role.HEAT_DEMAND.value)
        )
        assert demand_mapping is not None
        demand_mapping.valid_to_ts = T0 + 1
    with factory() as session:
        without_demand = read_summary(session, end)
    assert without_demand["starts_per_uur"].state != "unknown"
    assert without_demand["korte_cycli_6u"].state == "unknown"
    assert without_demand["onvoldoende_gegevens"].state == "on"
    with factory.begin() as session:
        demand_mapping = session.scalar(
            select(SignalMapping).where(SignalMapping.role == Role.HEAT_DEMAND.value)
        )
        assert demand_mapping is not None
        demand_mapping.valid_to_ts = None
    # The outage is inside the runner's settle delay: it must still clear live export.
    with factory.begin() as session:
        SqlObservationRepository(session).add_connection_events(
            [ConnectionEvent(end - 1_000, ConnectionSource.WS, False)]
        )
    with factory() as session:
        values = read_summary(session, end)
    assert values["starts_per_uur"].state == "unknown"
    assert values["korte_cycli_6u"].state == "unknown"
    assert values["bedrijfsmodus"].state == "onbekend"
    assert values["onvoldoende_gegevens"].state == "on"


@pytest.mark.skipif(not os.getenv("CVIDEE_TEST_MQTT_HOST"), reason="requires dev Mosquitto broker")
async def test_mosquitto_last_will_after_abrupt_export_process_exit(tmp_path: Path) -> None:
    import sys

    factory = make_db(tmp_path)
    del factory
    script = """
import asyncio
import sys
from cvidee.main import create_app
from cvidee.config import Settings
from cvidee.ha_export.service import ExportService
from cvidee.store.engine import create_db_engine, create_session_factory, database_url

async def main():
    settings = Settings(MQTT_HOST=sys.argv[1], MQTT_USER="dev", MQTT_PASSWORD="dev")
    factory = create_session_factory(create_db_engine(database_url(sys.argv[2])))
    export = ExportService(settings, factory)
    await export.start()
    await export.ready.wait()
    print("ready", flush=True)
    await asyncio.Event().wait()

asyncio.run(main())
"""
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        script,
        os.environ["CVIDEE_TEST_MQTT_HOST"],
        str(tmp_path / "db.sqlite"),
        stdout=asyncio.subprocess.PIPE,
    )
    try:
        assert child.stdout is not None
        async with asyncio.timeout(10):
            assert await child.stdout.readline() == b"ready\n"
        async with aiomqtt.Client(
            os.environ["CVIDEE_TEST_MQTT_HOST"], username="dev", password="dev"
        ) as subscriber:
            await subscriber.subscribe(STATUS_TOPIC)
            async with asyncio.timeout(5):
                assert bytes((await anext(subscriber.messages)).payload) == b"online"
            child.kill()
            await child.wait()
            async with asyncio.timeout(5):
                assert bytes((await anext(subscriber.messages)).payload) == b"offline"
    finally:
        if child.returncode is None:
            child.kill()
            await child.wait()
