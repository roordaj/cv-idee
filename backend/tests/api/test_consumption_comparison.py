"""Gas-period candidates require a stable, measured basis and never normalize values."""

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from cvidee.api.consumption_comparison import ConsumptionComparisonReadModel
from cvidee.api.schemas.consumption import (
    ConsumptionComparisonReason,
    ConsumptionComparisonRequest,
    ConsumptionComparisonStatus,
    ConsumptionComparisonWindow,
)
from cvidee.installation.defaults import default_profile
from cvidee.installation.specs import GAS_METER_SCOPE
from cvidee.signals.catalog import sync_catalogue
from cvidee.store.engine import create_db_engine, create_session_factory, database_url
from cvidee.store.enums import ObservationKind, ObservationOrigin, SpecStatus, ValueKind
from cvidee.store.models import SignalMapping, SourceEntity
from cvidee.store.observations import SqlObservationRepository
from cvidee.store.records import ObservationRecord
from cvidee.store.schema import upgrade_to_head

NOW = 1_791_100_800_000
HOUR = 3_600_000
DAY = 24 * HOUR


def _model(
    tmp_path: Path, *, scope: str | None = None, reset: bool = False
) -> ConsumptionComparisonReadModel:
    url = database_url(tmp_path / "comparison.sqlite")
    upgrade_to_head(url)
    factory = create_session_factory(create_db_engine(url))
    with factory.begin() as session:
        sync_catalogue(session)
        profile = default_profile(NOW - 3 * DAY)
        scope_spec = next(spec for spec in profile.specs if spec.key == GAS_METER_SCOPE)
        if scope is not None:
            scope_spec.status = SpecStatus.KNOWN
            scope_spec.value_text = scope
        session.add(profile)
        if scope is not None:
            readings = []
            for hour in range(72):
                value = 100 + hour
                if reset and hour >= 36:
                    value = 5 + hour - 36
                readings.append((NOW - 2 * DAY + hour * HOUR, float(value)))
            SqlObservationRepository(session).add_observations(
                [
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
            )
            entity = session.scalar(
                select(SourceEntity).where(SourceEntity.entity_id == "sensor.gas_total")
            )
            assert entity is not None
            entity.unit = "m³"
            session.add(
                SignalMapping(
                    role="gas_cumulative",
                    scope_key="",
                    source_entity_id=entity.id,
                    kind=ValueKind.MEASURED,
                    heartbeat_expected=False,
                    max_age_ms=HOUR,
                    valid_from_ts=readings[0][0],
                    created_at_ts=readings[0][0],
                    unit="m³",
                )
            )
    return ConsumptionComparisonReadModel(factory, clock=lambda: NOW)


def _dt(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, UTC)


def test_candidate_listing_reports_missing_meter_without_fake_zero(tmp_path: Path) -> None:
    model = _model(tmp_path)

    result = model.candidates(_dt(NOW - DAY), _dt(NOW))

    assert result.status is ConsumptionComparisonStatus.UNAVAILABLE
    assert result.candidates
    assert all(item.consumption_m3 is None for item in result.candidates)
    assert all(item.status is ConsumptionComparisonStatus.UNAVAILABLE for item in result.candidates)
    assert all(ConsumptionComparisonReason.NO_METER in item.reasons for item in result.candidates)


def test_unknown_scope_never_yields_an_eligible_pair(tmp_path: Path) -> None:
    model = _model(tmp_path, scope=None)

    result = model.compare(
        ConsumptionComparisonRequest(
            reference=ConsumptionComparisonWindow(start=_dt(NOW - 2 * DAY), end=_dt(NOW - DAY)),
            observation=ConsumptionComparisonWindow(start=_dt(NOW - DAY), end=_dt(NOW)),
        )
    )

    assert result.status is ConsumptionComparisonStatus.UNAVAILABLE
    assert result.difference_m3 is None
    assert ConsumptionComparisonReason.UNKNOWN_METER_SCOPE in result.reasons


def test_reset_and_partial_edge_coverage_are_explicit(tmp_path: Path) -> None:
    model = _model(tmp_path, scope="whole_house", reset=True)

    result = model.compare(
        ConsumptionComparisonRequest(
            reference=ConsumptionComparisonWindow(start=_dt(NOW - 2 * DAY), end=_dt(NOW - DAY)),
            observation=ConsumptionComparisonWindow(start=_dt(NOW - DAY), end=_dt(NOW)),
        )
    )

    assert result.status is ConsumptionComparisonStatus.UNAVAILABLE
    assert result.difference_m3 is None
    assert ConsumptionComparisonReason.COUNTER_RESET in result.reasons
    assert ConsumptionComparisonReason.DATA_GAP in result.reasons
    assert result.observation.meter_scope.value == "whole_house"
