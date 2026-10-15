"""Changes are persistent, atomically linked, and visible at exact timeline boundaries."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cvidee.config import Settings
from cvidee.main import create_app
from cvidee.runner.service import AnalysisRunner, RunnerSettings
from cvidee.store.enums import Certainty
from cvidee.store.models import Change, RecommendationSnapshot
from tests.findings.dummy import DummyRule, Emit
from tests.findings.test_api_and_runner import persist
from tests.runner.test_runner import END, HUGE, T0, make_db, seed


@pytest.fixture
def factory(tmp_path: Path) -> sessionmaker[Session]:
    return make_db(tmp_path, "changes")


@pytest.fixture
async def client(factory: sessionmaker[Session]) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(Settings.model_validate({}))
    app.state.session_factory = factory
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
    DummyRule.emit = ()


def payload(at: str = "2026-10-01T06:00:00Z") -> dict[str, str]:
    return {
        "at": at,
        "actor": "installer",
        "parameter": "Maximale CV-aanvoer",
        "old_value": "60 °C",
        "new_value": "55 °C",
        "reason": "Onderzoek korte cycli",
    }


async def test_log_is_persistent_and_linked_status_has_snapshot(
    client: httpx.AsyncClient, factory: sessionmaker[Session]
) -> None:
    persist(factory, Emit(certainty=Certainty.INSUFFICIENT_EVIDENCE))
    body = {**payload(), "finding_id": "B-001"}
    response = await client.post("/api/changes", json=body)
    assert response.status_code == 201
    change = response.json()
    assert change["id"] == "W-01"
    assert change["finding_id"] == "B-001"
    assert change["verdict"] == "pending"
    assert (await client.get("/api/findings/B-001")).json()["status"] == "done"
    assert (await client.get("/api/changes")).json()["items"] == [change]
    with factory() as session:
        row = session.scalar(select(Change))
        assert row is not None
        assert row.items[0].parameter_key == "max_ch_flow_temperature"
        assert row.recommendation_id is not None
        snapshot = session.scalar(select(RecommendationSnapshot))
        assert snapshot is not None
        assert snapshot.status.value == "done"
    assert (await client.get("/api/changes/W-01/evaluation")).status_code == 200
    custom = await client.post("/api/changes", json={**payload(), "parameter": "Eigen aanpassing"})
    assert custom.status_code == 201
    assert custom.json()["id"] == "W-02"


async def test_invalid_link_and_input_leave_no_changes(client: httpx.AsyncClient) -> None:
    for update, expected in (
        ({"finding_id": "B-999"}, 404),
        ({"parameter": "   "}, 422),
        ({"new_value": "   "}, 422),
        ({"at": "2099-01-01T00:00:00Z"}, 422),
    ):
        response = await client.post("/api/changes", json={**payload(), **update})
        assert response.status_code == expected
        assert response.headers["content-type"] == "application/problem+json"
    assert (await client.get("/api/changes")).json()["items"] == []
    assert (await client.get("/api/changes/W-99/evaluation")).status_code == 404


async def test_timeline_markers_use_half_open_range_and_latest_preceding_change(
    client: httpx.AsyncClient,
) -> None:
    for at in ("2026-10-01T05:00:00Z", "2026-10-01T06:00:00Z", "2026-10-01T07:00:00Z"):
        assert (await client.post("/api/changes", json=payload(at))).status_code == 201
    response = await client.get(
        "/api/timeline", params={"from": "2026-10-01T06:00:00Z", "to": "2026-10-01T07:00:00Z"}
    )
    assert response.status_code == 200
    body = response.json()
    assert [m["id"] for m in body["changes"]] == ["W-02"]
    assert body["changes"][0]["at"] == "2026-10-01T06:00:00Z"
    assert body["changes"][0]["actor"] == "installer"
    assert body["last_change_before"]["id"] == "W-01"
    assert set(body["series"]["flow_temperature"]) == {None}
    assert body["gaps"] == [body["range"]]
    assert body["modes"][0]["mode"] == "unknown"
    assert (
        await client.get(
            "/api/timeline", params={"from": "2026-10-02T00:00:00Z", "to": "2026-10-01T00:00:00Z"}
        )
    ).status_code == 422


async def test_timeline_reuses_known_gaps_and_persisted_cycles(
    client: httpx.AsyncClient, factory: sessionmaker[Session]
) -> None:
    from datetime import UTC, datetime

    seed(factory)
    runner = AnalysisRunner(factory, RunnerSettings(chunk_ms=HUGE))
    assert all(run.status.value == "succeeded" for run in runner.tick(END + 300_000))
    response = await client.get(
        "/api/timeline",
        params={
            "from": datetime.fromtimestamp(T0 / 1000, UTC).isoformat(),
            "to": datetime.fromtimestamp(END / 1000, UTC).isoformat(),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cycles"]
    assert body["gaps"]
    assert body["heat_demand"]
    assert len(body["series"]["flow_temperature"]) <= 1200


async def test_numeric_timeline_keeps_unavailable_and_implausible_values_unknown(
    client: httpx.AsyncClient, factory: sessionmaker[Session]
) -> None:
    from datetime import UTC, datetime

    from cvidee.analysis.types import Role
    from cvidee.store.enums import ObservationKind, ObservationOrigin, ValueKind
    from cvidee.store.models import SignalDefinition, SignalMapping, SourceEntity
    from cvidee.store.observations import SqlObservationRepository
    from cvidee.store.records import ObservationRecord

    entity_id = "sensor.boiler_flow"
    with factory.begin() as session:
        SqlObservationRepository(session).add_observations(
            [
                ObservationRecord(
                    entity_id=entity_id,
                    ts=T0 + seconds * 1000,
                    state=state,
                    value_num=value,
                    kind=ObservationKind.CHANGE,
                    origin=ObservationOrigin.LIVE,
                    received_at_ts=T0 + seconds * 1000,
                    last_reported_ts=None,
                )
                for seconds, state, value in (
                    (0, "45", 45.0),
                    (60, "999", 999.0),
                    (120, "unavailable", None),
                    (180, "55", 55.0),
                )
            ]
        )
        entity = session.scalar(select(SourceEntity).where(SourceEntity.entity_id == entity_id))
        assert entity is not None
        session.add(
            SignalDefinition(
                role=Role.FLOW_TEMPERATURE.value,
                value_type="numeric",
                unit="°C",
                scope_type="boiler",
                default_kind=ValueKind.REPORTED,
                default_max_age_ms=60_000,
                required_for=[],
                catalogue_version="test",
            )
        )
        session.flush()
        session.add(
            SignalMapping(
                role=Role.FLOW_TEMPERATURE.value,
                source_entity_id=entity.id,
                kind=ValueKind.REPORTED,
                heartbeat_expected=False,
                max_age_ms=60_000,
                valid_from_ts=T0,
                created_at_ts=T0,
            )
        )
    response = await client.get(
        "/api/timeline",
        params={
            "from": datetime.fromtimestamp(T0 / 1000, UTC).isoformat(),
            "to": datetime.fromtimestamp(T0 / 1000 + 240, UTC).isoformat(),
        },
    )
    assert response.status_code == 200
    values = response.json()["series"]["flow_temperature"]
    assert values[0] == 45
    assert values[60] is None
    assert values[120] is None
    assert values[180] == 55
