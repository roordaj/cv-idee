"""Gas use remains raw, meter-scoped and conservative across resets and setting changes."""

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from cvidee.analysis.types import Role
from cvidee.api.consumption_read import ConsumptionReadModel
from cvidee.api.schemas.consumption import ConsumptionAvailability, ConsumptionReason
from cvidee.installation.defaults import default_profile
from cvidee.installation.specs import GAS_METER_SCOPE
from cvidee.signals.catalog import sync_catalogue
from cvidee.store.engine import create_db_engine, create_session_factory, database_url
from cvidee.store.enums import ObservationKind, ObservationOrigin, SpecStatus, ValueKind
from cvidee.store.models import SettingsRevision, SignalMapping, SourceEntity
from cvidee.store.observations import SqlObservationRepository
from cvidee.store.records import ObservationRecord
from cvidee.store.schema import upgrade_to_head

NOW = 1_791_100_800_000
STEP = 3_600_000


def setup_model(
    tmp_path: Path,
    readings: list[tuple[int, float]],
    *,
    max_age_ms: int = STEP,
    scope: str | None = "boiler_only",
    prices: list[tuple[int, float]] | None = None,
) -> ConsumptionReadModel:
    url = database_url(tmp_path / "consumption.sqlite")
    upgrade_to_head(url)
    factory = create_session_factory(create_db_engine(url))
    with factory.begin() as session:
        sync_catalogue(session)
        profile = default_profile(NOW)
        scope_spec = next(spec for spec in profile.specs if spec.key == GAS_METER_SCOPE)
        if scope is not None:
            scope_spec.status = SpecStatus.KNOWN
            scope_spec.value_text = scope
        session.add(profile)
        observations = [
            ObservationRecord(
                entity_id="sensor.gas_total",
                ts=ts,
                state=str(value),
                value_num=value,
                kind=ObservationKind.CHANGE,
                origin=ObservationOrigin.LIVE,
                received_at_ts=ts,
            )
            for ts, value in readings
        ]
        SqlObservationRepository(session).add_observations(observations)
        entity = session.scalar(
            select(SourceEntity).where(SourceEntity.entity_id == "sensor.gas_total")
        )
        assert entity is not None
        entity.unit = "m³"
        session.add(
            SignalMapping(
                role=Role.GAS_CUMULATIVE.value,
                scope_key="",
                source_entity_id=entity.id,
                kind=ValueKind.MEASURED,
                heartbeat_expected=False,
                max_age_ms=max_age_ms,
                valid_from_ts=readings[0][0],
                created_at_ts=readings[0][0],
                unit="m³",
            )
        )
        for created_at, price in prices or []:
            session.add(
                SettingsRevision(
                    values={"gas_price_eur_per_m3": price},
                    config_hash="test",
                    created_at_ts=created_at,
                )
            )
    return ConsumptionReadModel(factory, clock=lambda: NOW)


def dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts / 1000, UTC)


def test_counter_reset_is_excluded_from_both_volume_and_coverage(tmp_path: Path) -> None:
    model = setup_model(
        tmp_path,
        [(NOW, 100), (NOW + STEP, 101), (NOW + 2 * STEP, 5), (NOW + 3 * STEP, 7)],
        prices=[(NOW, 2.0), (NOW + 2 * STEP, 3.0)],
    )

    result = model.consumption(dt(NOW), dt(NOW + 3 * STEP + 1))

    assert result.availability is ConsumptionAvailability.LIMITED
    assert result.meter_scope.value == "boiler_only"
    assert result.consumption_m3 == 3.0
    assert result.coverage_pct == 66.67
    assert result.cost_eur is None
    assert [segment.cost_eur for segment in result.segments] == [2.0, 6.0]
    assert [segment.settings_revision for segment in result.segments] == [1, 2]
    assert result.reasons == [ConsumptionReason.COUNTER_RESET]
    assert result.events[0].start == dt(NOW + STEP)
    assert result.events[0].end == dt(NOW + 2 * STEP)


def test_long_counter_gap_is_not_summed_and_unknown_scope_stays_explicit(
    tmp_path: Path,
) -> None:
    model = setup_model(
        tmp_path,
        [(NOW, 10), (NOW + 2 * STEP, 12)],
        scope=None,
    )

    result = model.consumption(dt(NOW), dt(NOW + 2 * STEP + 1))

    assert result.availability is ConsumptionAvailability.UNAVAILABLE
    assert result.meter_scope.value == "unknown"
    assert result.consumption_m3 is None
    assert result.coverage_pct == 0.0
    assert set(result.reasons) == {
        ConsumptionReason.DATA_GAP,
        ConsumptionReason.NO_VALID_INTERVALS,
        ConsumptionReason.UNKNOWN_METER_SCOPE,
    }
    assert result.events[0].kind.value == "data_gap"
