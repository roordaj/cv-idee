"""Signal mappings, observed availability and pipeline validity boundaries (#18/#25)."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cvidee.analysis.timeline import build_timelines
from cvidee.analysis.types import HOUR_MS, AnalysisWindow, ObservationKind, Role
from cvidee.api.problems import ProblemError
from cvidee.api.routes.signals import get_signals
from cvidee.api.schemas.signals import SignalMappingUpdate
from cvidee.config import Settings
from cvidee.ingest.ha_client import HAClient, HAState, HAUnavailableError
from cvidee.main import create_app
from cvidee.runner.service import AnalysisRunner
from cvidee.runner.sources import (
    SourceSettings,
    build_pipeline_config,
    load_mapped_signals,
    load_window_input,
)
from cvidee.signals.backend import SignalsBackend
from cvidee.signals.catalog import BY_ROLE, sync_catalogue
from cvidee.store.engine import create_db_engine, create_session_factory, database_url
from cvidee.store.enums import ObservationOrigin
from cvidee.store.models import SignalDefinition, SignalMapping
from cvidee.store.observations import SqlObservationRepository
from cvidee.store.records import ObservationRecord
from cvidee.store.schema import upgrade_to_head

NOW = 1_791_100_800_000
DAY = 24 * HOUR_MS


@pytest.fixture
def sessions(tmp_path: Path) -> sessionmaker[Session]:
    url = database_url(tmp_path / "signals.sqlite")
    upgrade_to_head(url)
    return create_session_factory(create_db_engine(url))


@pytest.fixture
def backend(sessions: sessionmaker[Session]) -> SignalsBackend:
    client = MagicMock(spec=HAClient)
    client.get_states = AsyncMock(
        return_value=[
            HAState("binary_sensor.flame", "off", last_reported=NOW),
            HAState("sensor.mode", "1", last_reported=NOW),
            HAState("binary_sensor.demand", "on", last_reported=NOW),
            HAState("sensor.flow", "50", {"unit_of_measurement": "°C"}, last_reported=NOW),
            HAState("sensor.gas", "100", {"unit_of_measurement": "m³"}, last_reported=NOW),
            HAState("sensor.heat", "10", {"unit_of_measurement": "kWh"}, last_reported=NOW),
            HAState("sensor.power", "100", {"unit_of_measurement": "W"}, last_reported=NOW),
        ]
    )
    return SignalsBackend(
        sessions, client, MagicMock(spec=AnalysisRunner), MagicMock(), lambda: NOW
    )


async def test_circuit_scoped_mapping_reaches_pipeline(backend: SignalsBackend) -> None:
    result = await backend.update_signal(
        "pump_state@circuit:boven",
        SignalMappingUpdate(entity_id="binary_sensor.demand"),
    )
    assert result.scope_kind.value == "circuit"
    assert result.scope_key == "boven"
    with backend.sessions() as session:
        (mapping,) = load_mapped_signals(session)
        assert str(mapping.signal) == "pump_state@circuit:boven"


async def test_heartbeat_controls_staleness(backend: SignalsBackend) -> None:
    await backend.update_signal(
        "flame@boiler",
        SignalMappingUpdate(
            entity_id="binary_sensor.flame", max_age_s=5, expects_regular_updates=False
        ),
    )
    backend.clock = lambda: NOW + HOUR_MS
    unchanged = next(signal for signal in backend.signal_list().items if signal.role is Role.FLAME)
    assert unchanged.state.value == "ok"
    await backend.update_signal(
        "flame@boiler",
        SignalMappingUpdate(entity_id="binary_sensor.flame", expects_regular_updates=True),
    )
    backend.clock = lambda: NOW + HOUR_MS + 1000
    stale = next(signal for signal in backend.signal_list().items if signal.role is Role.FLAME)
    assert stale.state.value == "stale"


async def test_future_mapping_is_rejected(backend: SignalsBackend) -> None:
    with pytest.raises(ProblemError) as error:
        await backend.update_signal(
            "flame@boiler",
            SignalMappingUpdate(
                entity_id="binary_sensor.flame",
                valid_from=datetime.fromtimestamp((NOW + HOUR_MS) / 1000, UTC),
            ),
        )
    assert error.value.problem.status == 422


def test_catalogue_has_every_role_and_separate_manifold_scopes(backend: SignalsBackend) -> None:
    assert set(BY_ROLE) == set(Role)
    ids = {signal.id for signal in backend.signal_list().items}
    assert {
        "flow_temperature@boiler",
        "return_temperature@boiler",
        "manifold_flow_temperature@manifold:boven",
        "room_setpoint@room:woonkamer",
    } <= ids
    assert backend.signal_list().linked == 0
    with backend.sessions.begin() as session:
        sync_catalogue(session)
        sync_catalogue(session)
        assert len(list(session.scalars(select(SignalDefinition)))) == len(Role)


async def test_mapping_versions_refresh_ingest_and_queue_recompute(backend: SignalsBackend) -> None:
    saved = await backend.update_signal(
        "flame@boiler",
        SignalMappingUpdate(
            entity_id="binary_sensor.flame",
            location="Ketel",
            meaning="Werkelijke vlam",
            expected_resolution_s=4,
            expects_regular_updates=False,
        ),
    )
    assert saved.entity_id == "binary_sensor.flame"
    assert saved.state.value == "ok"
    assert saved.expected_resolution_s == 4
    assert backend.refresh is not None
    backend.refresh.assert_called_once()  # type: ignore[attr-defined]
    assert backend.runner is not None
    backend.runner.request_recompute.assert_called_once_with(  # type: ignore[attr-defined]
        NOW, reason="signal_mapping_changed"
    )
    backend.clock = lambda: NOW + 1000
    await backend.update_signal(
        "flame@boiler",
        SignalMappingUpdate(
            entity_id="binary_sensor.flame",
            max_age_s=60,
        ),
    )
    with backend.sessions() as session:
        rows = list(session.scalars(select(SignalMapping).order_by(SignalMapping.id)))
        assert len(rows) == 2
        assert rows[0].valid_to_ts == rows[1].valid_from_ts == NOW + 1000
        assert rows[1].location == "Ketel"
        assert rows[1].expected_resolution_ms == 4000


@pytest.mark.parametrize(
    ("ident", "entity", "status"),
    [
        ("nope@boiler", "binary_sensor.flame", 404),
        ("flame@room:woonkamer", "binary_sensor.flame", 404),
        ("room_temperature@room:missing", "sensor.flow", 404),
        ("flow_temperature@boiler", "sensor.power", 422),
        ("flow_temperature@boiler", "sensor.missing", 422),
    ],
)
async def test_invalid_mapping_rolls_back(
    backend: SignalsBackend, ident: str, entity: str, status: int
) -> None:
    with pytest.raises(ProblemError) as error:
        await backend.update_signal(ident, SignalMappingUpdate(entity_id=entity))
    assert error.value.problem.status == status
    with backend.sessions() as session:
        assert list(session.scalars(select(SignalMapping))) == []


async def test_unavailable_ha_does_not_prevent_unlink(backend: SignalsBackend) -> None:
    await backend.update_signal(
        "flame@boiler", SignalMappingUpdate(entity_id="binary_sensor.flame")
    )
    assert backend.client is not None
    backend.client.get_states.side_effect = HAUnavailableError("offline")  # type: ignore[attr-defined]
    with pytest.raises(ProblemError) as error:
        await backend.update_signal(
            "flame@boiler", SignalMappingUpdate(entity_id="binary_sensor.flame")
        )
    assert error.value.problem.status == 502
    backend.clock = lambda: NOW + 1000
    unlinked = await backend.update_signal("flame@boiler", SignalMappingUpdate(entity_id=None))
    assert unlinked.entity_id is None
    assert unlinked.state.value == "missing"


async def test_unlink_ends_pipeline_validity(backend: SignalsBackend) -> None:
    await backend.update_signal(
        "flame@boiler", SignalMappingUpdate(entity_id="binary_sensor.flame")
    )
    backend.clock = lambda: NOW + 1000
    await backend.update_signal("flame@boiler", SignalMappingUpdate(entity_id=None))
    with backend.sessions() as session:
        mappings = load_mapped_signals(session)
        config = build_pipeline_config(session, mappings, SourceSettings())
        window = AnalysisWindow(NOW, NOW, NOW + 2000)
        observations, events = load_window_input(session, mappings, SourceSettings(), window)
        (timeline,) = build_timelines(observations, events, config, window)
        assert sum(value.end - value.start for value in timeline.values) == 1000
        assert sum(gap.end - gap.start for gap in timeline.unknowns) == 1000
        later = AnalysisWindow(NOW + 1500, NOW + 1500, NOW + 3000)
        observations, events = load_window_input(session, mappings, SourceSettings(), later)
        (timeline,) = build_timelines(observations, events, config, later)
        assert timeline.values == ()


async def seed_role(backend: SignalsBackend, role: str, entity: str, state: str) -> None:
    await backend.update_signal(
        f"{role}@boiler",
        SignalMappingUpdate(
            entity_id=entity,
            value_map={"1": "ch"} if role == "operating_mode" else None,
            meaning="Explicit synthetic test mode table" if role == "operating_mode" else None,
            valid_from=datetime.fromtimestamp((NOW - DAY) / 1000, UTC),
        ),
    )
    with backend.sessions.begin() as session:
        SqlObservationRepository(session).add_observations(
            [
                ObservationRecord(
                    entity,
                    NOW - DAY + delta,
                    state,
                    None,
                    ObservationKind.CONFIRM,
                    ObservationOrigin.LIVE,
                    NOW - DAY + delta,
                )
                for delta in (0, 4000, 8000, 12000)
            ]
        )


async def test_no_gas_keeps_cycles_available_and_efficiency_requires_both(
    backend: SignalsBackend,
) -> None:
    for role, entity, state in [
        ("flame", "binary_sensor.flame", "off"),
        ("operating_mode", "sensor.mode", "1"),
        ("heat_demand", "binary_sensor.demand", "on"),
    ]:
        await seed_role(backend, role, entity, state)
    analyses = {item.id.value: item for item in backend.analyses().items}
    assert analyses["cycles"].status.value == "available"
    assert analyses["consumption"].status.value == "unavailable"
    assert "Gasgegevens ontbreken" in analyses["consumption"].note
    await seed_role(backend, "gas_cumulative", "sensor.gas", "100")
    assert (
        next(a for a in backend.analyses().items if a.id.value == "efficiency").status.value
        == "unavailable"
    )
    await seed_role(backend, "heat_meter", "sensor.heat", "10")
    assert (
        next(a for a in backend.analyses().items if a.id.value == "efficiency").status.value
        == "available"
    )


async def test_expected_resolution_does_not_invent_actual_resolution(
    backend: SignalsBackend,
) -> None:
    await backend.update_signal(
        "flame@boiler",
        SignalMappingUpdate(
            entity_id="binary_sensor.flame",
            expected_resolution_s=1,
        ),
    )
    backend.clock = lambda: NOW + 1000
    signal = next(s for s in backend.signal_list().items if s.role is Role.FLAME)
    assert signal.median_update_interval_s is None
    analysis = next(a for a in backend.analyses().items if a.id.value == "cycles")
    assert analysis.status.value == "limited"
    assert "meetresolutie onbekend" in analysis.note


async def test_real_routes_work_without_stub(backend: SignalsBackend) -> None:
    app = create_app(Settings.model_validate({}))
    app.dependency_overrides[get_signals] = lambda: backend
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/api/signals")).json()["linked"] == 0
        linked = await client.put(
            "/api/signals/flame@boiler", json={"entity_id": "binary_sensor.flame"}
        )
        assert linked.status_code == 200, linked.text
        assert len((await client.get("/api/analyses")).json()["items"]) == 8
