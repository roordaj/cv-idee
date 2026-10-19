"""Real monitoring reads stay honest when the store is empty or disconnected."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from cvidee.analysis.types import Role
from cvidee.api.live_read import LiveReadModel, safe_url
from cvidee.api.problems import ProblemError
from cvidee.config import Settings
from cvidee.signals.catalog import sync_catalogue
from cvidee.store.engine import create_db_engine, create_session_factory, database_url
from cvidee.store.enums import ObservationKind, ObservationOrigin, ValueKind
from cvidee.store.models import SignalMapping, SourceEntity
from cvidee.store.observations import SqlObservationRepository
from cvidee.store.records import ObservationRecord
from cvidee.store.schema import upgrade_to_head


def make_model(tmp_path: Path, now: int = 1_791_100_800_000) -> LiveReadModel:
    url = database_url(tmp_path / "read.sqlite")
    upgrade_to_head(url)
    factory = create_session_factory(create_db_engine(url))
    return LiveReadModel(factory, Settings(), None, None, clock=lambda: now)


def test_empty_store_routes_have_explicit_unknown_state(tmp_path: Path) -> None:
    model = make_model(tmp_path)

    status = model.status()
    overview = model.overview()
    quality = model.quality()
    cycles = model.cycles(limit=20, offset=0)

    assert status.stub_data is False
    assert status.operating_mode.value == "unknown"
    assert status.counts.signals_linked == 0
    assert overview.assessment.level.value == "insufficient_data"
    assert overview.status_card.title == "Nog geen beoordeling mogelijk"
    assert overview.today.ch_cycles == 0
    assert {item.key for item in overview.kpis} >= {
        "flow_temperature",
        "return_temperature",
        "flow_setpoint",
        "modulation",
    }
    assert quality.core_coverage_pct is None
    assert quality.coverage
    assert all(row.coverage_pct is None for row in quality.coverage)
    assert all(
        segment.kind.value == "not_mapped" for row in quality.coverage for segment in row.segments
    )
    assert cycles.summary.starts_per_hour is None
    assert cycles.summary.total_burn_s is None


def test_monitoring_rejects_future_and_reversed_ranges(tmp_path: Path) -> None:
    model = make_model(tmp_path)
    with pytest.raises(ProblemError, match="maximaal 31 dagen"):
        model.quality(end=datetime.fromtimestamp(model.clock() / 1000, UTC) + timedelta(seconds=1))


def test_quality_uses_real_mappings_and_keeps_invalid_values_unknown(tmp_path: Path) -> None:
    model = make_model(tmp_path)
    with model.sessions.begin() as session:
        sync_catalogue(session)
        rows = [
            ObservationRecord(
                entity_id="binary_sensor.test_flame",
                ts=model.clock() - 3_600_000,
                state="on",
                value_num=1,
                kind=ObservationKind.CHANGE,
                origin=ObservationOrigin.LIVE,
                received_at_ts=model.clock() - 3_600_000,
            ),
            ObservationRecord(
                entity_id="binary_sensor.test_flame",
                ts=model.clock() - 1_800_000,
                state="unexpected",
                value_num=None,
                kind=ObservationKind.CHANGE,
                origin=ObservationOrigin.LIVE,
                received_at_ts=model.clock() - 1_800_000,
            ),
        ]
        SqlObservationRepository(session).add_observations(rows)
        entity = session.scalar(
            select(SourceEntity).where(SourceEntity.entity_id == "binary_sensor.test_flame")
        )
        assert entity is not None
        session.add(
            SignalMapping(
                role=Role.FLAME.value,
                scope_key="",
                source_entity_id=entity.id,
                kind=ValueKind.REPORTED,
                heartbeat_expected=False,
                max_age_ms=60_000,
                valid_from_ts=model.clock() - 3_600_000,
                created_at_ts=model.clock() - 3_600_000,
            )
        )

    quality = model.quality(
        start=datetime.fromtimestamp((model.clock() - 3_600_000) / 1000, UTC),
        end=datetime.fromtimestamp(model.clock() / 1000, UTC),
    )
    flame = next(row for row in quality.coverage if row.signal_ids == ["flame@boiler"])
    assert flame.coverage_pct is not None
    assert flame.coverage_pct < 100
    assert any(segment.kind.value == "unknown" for segment in flame.segments)
    assert any(
        row.signal_ids == ["flow_temperature@boiler"] and row.coverage_pct is None
        for row in quality.coverage
    )


def test_safe_url_removes_credentials_query_and_fragment() -> None:
    assert safe_url("http://admin:secret@ha.local:8123/path?token=secret#view") == (
        "http://ha.local:8123"
    )
    assert safe_url(None) is None
