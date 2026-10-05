"""HA client + ingest service against the fake HA server (#17, ADR-003 §10.3)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from cvidee.analysis.types import ConnectionSource
from cvidee.config import HAConnection, Settings
from cvidee.ingest.ha_client import (
    AiohttpHAClient,
    HAError,
    HAState,
    StateChangedEvent,
    parse_ha_time,
)
from cvidee.ingest.service import (
    IngestService,
    TrackedEntity,
    confirm_poll_interval_ms,
    map_state_changed,
)
from cvidee.main import create_app
from cvidee.store.models import Base
from cvidee.store.observations import SqlObservationRepository
from tests.fakes.ha_server import TOKEN, FakeHAServer, make_state

FLAME = "binary_sensor.flame"
FLOW = "sensor.flow"
T0 = 1_800_000_000_000
MIN = 60_000


@dataclass
class Clock:
    t: int = T0

    def __call__(self) -> int:
        return self.t


async def until(cond: Callable[[], bool], limit: float = 5.0) -> None:
    async with asyncio.timeout(limit):
        while not cond():  # noqa: ASYNC110
            await asyncio.sleep(0.01)


@pytest.fixture
def engine() -> Engine:
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    return engine


def factory(engine: Engine) -> Callable[[], AbstractContextManager[Session]]:
    return lambda: Session(engine)


@pytest.fixture
async def server() -> AsyncIterator[FakeHAServer]:
    s = FakeHAServer()
    s.states[FLAME] = make_state(FLAME, "off", changed=T0 - 10 * MIN)
    s.states[FLOW] = make_state(
        FLOW, "40.5", changed=T0 - 10 * MIN, attributes={"unit_of_measurement": "°C"}
    )
    await s.start()
    yield s
    await s.stop()


@dataclass
class Rig:
    server: FakeHAServer
    client: AiohttpHAClient
    service: IngestService
    engine: Engine
    clock: Clock

    def repo_call[T](self, fn: Callable[[SqlObservationRepository], T]) -> T:
        with Session(self.engine) as s:
            return fn(SqlObservationRepository(s))

    def conn_events(self) -> list[tuple[int, bool]]:
        return self.repo_call(
            lambda r: [
                (e.ts, e.up)
                for e in r.connection_events(0, 10**15)
                if e.source is ConnectionSource.WS
            ]
        )

    def observations(self, entity: str) -> list[tuple[int, str, str]]:
        return self.repo_call(
            lambda r: [(o.ts, o.state, o.kind.value) for o in r.observations(entity, 0, 10**15)]
        )


@pytest.fixture
async def rig(server: FakeHAServer, engine: Engine) -> AsyncIterator[Rig]:
    clock = Clock()
    entities = [
        TrackedEntity(FLAME),
        TrackedEntity(FLOW, heartbeat_expected=True, max_age_ms=3 * MIN),
    ]
    holder: list[IngestService] = []

    async def fast_sleep(_: float) -> None:
        await asyncio.sleep(0.01)

    client = AiohttpHAClient(
        HAConnection(
            websocket_url=server.url.replace("http", "ws") + "/api/websocket",
            rest_url=server.url + "/api",
            token=SecretStr(TOKEN),
        ),
        tracked=lambda: holder[0].tracked_ids(),
        clock=clock,
        sleep=fast_sleep,
    )
    service = IngestService(client, factory(engine), lambda: entities, clock=clock)
    holder.append(service)
    await service.start()
    r = Rig(server, client, service, engine, clock)
    await until(lambda: client.connected)
    yield r
    await service.stop()


# ------------------------------------------------------------------ pure mapping


def st(
    entity: str, state: str, changed: int, updated: int | None = None, reported: int | None = None
) -> HAState:
    updated = changed if updated is None else updated
    return HAState(entity, state, {}, changed, updated, updated if reported is None else reported)


def ev(old: HAState | None, new: HAState | None, fired: int = 1000) -> StateChangedEvent:
    return StateChangedEvent(FLAME, fired, old, new)


def kinds(records: list) -> list[tuple[int, str, str]]:  # type: ignore[type-arg]
    return [(r.ts, r.state, r.kind.value) for r in records]


def test_i1_change() -> None:
    out = map_state_changed(ev(st(FLAME, "off", 100), st(FLAME, "on", 500)), 9)
    assert kinds(out) == [(500, "on", "change")]


def test_i2_same_state_confirm_at_last_updated() -> None:
    out = map_state_changed(ev(st(FLAME, "on", 100), st(FLAME, "on", 100, updated=700)), 9)
    assert kinds(out) == [(700, "on", "confirm")]


def test_i3_unchanged_report_old_last_reported_confirm_then_change() -> None:
    old = st(FLAME, "off", 100, updated=100, reported=400)
    out = map_state_changed(ev(old, st(FLAME, "on", 500)), 9)
    assert kinds(out) == [(400, "off", "confirm"), (500, "on", "change")]
    assert out[0].last_reported_ts == 400


def test_i3_no_confirm_when_never_reported_again() -> None:
    out = map_state_changed(ev(st(FLAME, "off", 100), st(FLAME, "on", 500)), 9)
    assert len(out) == 1


def test_i5_removed_entity_and_i6_unavailable() -> None:
    out = map_state_changed(ev(st(FLAME, "on", 100), None, fired=900), 9)
    assert kinds(out) == [(900, "unavailable", "change")]
    out = map_state_changed(ev(st(FLAME, "on", 100), st(FLAME, "unavailable", 800)), 9)
    assert out[0].value_num is None
    assert out[0].state == "unavailable"


def test_new_entity_without_old_state_is_change() -> None:
    out = map_state_changed(ev(None, st(FLAME, "on", 300)), 9)
    assert kinds(out) == [(300, "on", "change")]


def test_confirm_poll_interval_clamped() -> None:
    assert confirm_poll_interval_ms([TrackedEntity(FLAME)]) is None
    assert confirm_poll_interval_ms([TrackedEntity("a", True, 30_000)]) == 10_000
    assert confirm_poll_interval_ms([TrackedEntity("a", True, 3_000)]) == 5_000
    assert confirm_poll_interval_ms([TrackedEntity("a", True, 3_600_000)]) == 60_000


def test_parse_ha_time_floors_to_ms() -> None:
    assert parse_ha_time("2026-01-01T00:00:00.123987+00:00") == 1767225600123
    assert parse_ha_time(None) is None


# --------------------------------------------------------------- integration


async def test_connect_records_up_and_poll(rig: Rig) -> None:
    assert rig.conn_events() == [(T0, True)]
    assert rig.observations(FLAME) == [(T0, "off", "poll")]
    flow = rig.repo_call(lambda r: r.observations(FLOW, 0, 10**15))
    assert flow[0].last_reported_ts == T0 - 10 * MIN  # poll may carry older evidence (§4.3)
    assert flow[0].value_num == 40.5


async def test_live_change_and_unchanged_report_confirm(rig: Rig) -> None:
    s = rig.server
    old = s.states[FLAME]
    new = make_state(FLAME, "on", changed=T0 + 5_000)
    # old state was re-reported at T0-5min (last_reported > last_updated)
    old = {**old, "last_reported": make_state(FLAME, "x", changed=T0 - 5 * MIN)["last_changed"]}
    await s.push_state_changed(FLAME, new, old, T0 + 5_000)
    await until(lambda: len(rig.observations(FLAME)) >= 3)
    assert rig.observations(FLAME) == [
        (T0 - 5 * MIN, "off", "confirm"),
        (T0, "off", "poll"),
        (T0 + 5_000, "on", "change"),
    ]


async def test_untracked_entities_are_filtered(rig: Rig) -> None:
    await rig.server.push_state_changed(
        "sensor.other", make_state("sensor.other", "1", changed=T0 + 1), None, T0 + 1
    )
    await rig.server.push_state_changed(
        FLAME, make_state(FLAME, "on", changed=T0 + 2), None, T0 + 2
    )
    await until(lambda: len(rig.observations(FLAME)) == 2)
    assert rig.observations("sensor.other") == []


async def test_30_minute_disconnect_gives_exactly_one_down_up_pair(rig: Rig) -> None:
    rig.clock.t = T0 + 5 * MIN
    await rig.server.push_state_changed(
        FLAME, make_state(FLAME, "on", changed=T0 + 5 * MIN), None, T0 + 5 * MIN
    )
    await until(lambda: len(rig.observations(FLAME)) == 2)
    last_message = rig.clock.t

    await rig.server.stop()  # HA gone; the client retries (several failed attempts)
    await until(lambda: len(rig.conn_events()) == 2)
    await asyncio.sleep(0.2)  # many failed reconnect attempts: must not add events
    rig.clock.t = T0 + 35 * MIN
    rig.server.states[FLAME] = make_state(FLAME, "on", changed=T0 + 5 * MIN)
    await rig.server.start()
    await until(lambda: len(rig.conn_events()) == 3)
    await asyncio.sleep(0.1)

    assert rig.conn_events() == [(T0, True), (last_message, False), (T0 + 35 * MIN, True)]
    # reconnect get_states stored as POLL at the up timestamp, never as a change
    assert (T0 + 35 * MIN, "on", "poll") in rig.observations(FLAME)
    polls = [o for o in rig.observations(FLAME) if o[2] == "poll"]
    assert [p[0] for p in polls] == [T0, T0 + 35 * MIN]
    assert len(set(rig.observations(FLAME))) == len(rig.observations(FLAME))  # no duplicates


async def test_duplicate_event_delivery_does_not_duplicate(rig: Rig) -> None:
    new = make_state(FLAME, "on", changed=T0 + 1000)
    await rig.server.push_state_changed(FLAME, new, None, T0 + 1000)
    await rig.server.push_state_changed(FLAME, new, None, T0 + 1000)
    await until(lambda: len(rig.observations(FLAME)) >= 2)
    await asyncio.sleep(0.1)
    assert rig.observations(FLAME).count((T0 + 1000, "on", "change")) == 1


async def test_confirmation_poll_stores_confirm_only_when_evidence_advanced(rig: Rig) -> None:
    # stored: POLL(T0, 40.5, lr=T0-10min). HA re-reported the same value 5 min ago.. at T0+1min
    rig.server.states[FLOW] = make_state(FLOW, "40.5", changed=T0 - 10 * MIN, reported=T0 + MIN)
    rig.clock.t = T0 + 2 * MIN
    assert await rig.service.confirmation_poll() == 1
    assert (T0 + MIN, "40.5", "confirm") in rig.observations(FLOW)
    assert await rig.service.confirmation_poll() == 0  # not advanced >= max_age/3 again
    rig.server.states[FLOW] = make_state(FLOW, "41.0", changed=T0 + 3 * MIN)
    assert await rig.service.confirmation_poll() == 0  # other value: state_changed leads


async def test_call_service_and_fire_event_are_restricted(rig: Rig) -> None:
    await rig.client.call_service("notify", "mobile_app_x", {"message": "hi"})
    await rig.client.fire_event("cv_analyse_finding", {"id": "F-1"})
    assert len(rig.server.service_calls) == 1
    assert len(rig.server.fired_events) == 1
    with pytest.raises(HAError):
        await rig.client.call_service("climate", "set_temperature", {})
    with pytest.raises(HAError):
        await rig.client.call_service("switch", "turn_on", {})
    with pytest.raises(HAError):
        await rig.client.fire_event("something_else", {})


async def test_crash_restart_writes_down_at_alive_ts(server: FakeHAServer, engine: Engine) -> None:
    with Session(engine) as s:
        SqlObservationRepository(s).add_connection_events(
            [
                __import__("cvidee.analysis.types", fromlist=["x"]).ConnectionEvent(
                    T0, ConnectionSource.WS, True
                )
            ]
        )
        s.commit()

    class Alive:
        def read(self) -> int:
            return T0 + 7 * MIN

        def write(self, ts: int) -> None:
            pass

    svc = IngestService(
        AiohttpHAClient(HAConnection("ws://x", "http://x", SecretStr("t")), tracked=lambda: set()),
        factory(engine),
        lambda: [],
        alive_store=Alive(),
        clock=Clock(T0 + 60 * MIN),
    )
    svc._write_crash_down_event()
    with Session(engine) as s:
        events = SqlObservationRepository(s).connection_events(0, 10**15)
    assert [(e.ts, e.up) for e in events] == [(T0, True), (T0 + 7 * MIN, False)]


# ------------------------------------------------------------------------ API


async def test_entities_endpoint_lists_ha_entities(
    server: FakeHAServer, monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.setenv("HA_URL", server.url)
    monkeypatch.setenv("HA_TOKEN", TOKEN)
    monkeypatch.setenv("CVIDEE_DB_PATH", str(tmp_path) + "/db.sqlite")
    app = create_app(Settings())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c,
    ):
        r = await c.get("/api/ha/entities")
        status = await c.get("/api/ha/status")
    assert r.status_code == 200
    keys = ("id", "friendly_name", "unit", "device_class")
    assert [{k: e[k] for k in keys} for e in r.json()] == [
        {"id": FLAME, "friendly_name": None, "unit": None, "device_class": None},
        {"id": FLOW, "friendly_name": None, "unit": "°C", "device_class": None},
    ]
    assert status.json()["configured"] is True


async def test_entities_endpoint_503_without_ha(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    for var in ("HA_URL", "HA_TOKEN", "SUPERVISOR_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("CVIDEE_DB_PATH", str(tmp_path) + "/db.sqlite")
    app = create_app(Settings())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c,
    ):
        assert (await c.get("/api/ha/entities")).status_code == 503
        assert (await c.get("/api/ha/status")).json() == {
            "configured": False,
            "connected": False,
        }


_ = Awaitable
