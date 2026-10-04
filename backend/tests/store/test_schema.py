"""Migration and model smoke tests (ADR-001)."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, Engine, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cvidee.store.engine import create_db_engine, create_session_factory
from cvidee.store.enums import (
    Certainty,
    ChangeActor,
    CircuitKind,
    ConnectionSource,
    EmitterType,
    EvaluationVerdict,
    EvidenceKind,
    FindingLifecycle,
    MetricName,
    MetricStatus,
    MetricWindowKind,
    Mode,
    ModeCertainty,
    NotificationChannel,
    ObservationKind,
    ObservationOrigin,
    QualityEventKind,
    RecommendationOutcome,
    RecommendationStatus,
    Severity,
    SnapshotTrigger,
    SpecialPeriodKind,
    SpecStatus,
    TriState,
    ValueKind,
)
from cvidee.store.models import (
    Base,
    BurnerCycle,
    Change,
    ChangeEvaluation,
    ChangeItem,
    ConnectionEvent,
    Finding,
    FindingEvidence,
    FindingHypothesis,
    InstallationProfile,
    InstallationSpec,
    MetricValue,
    ModeSegment,
    Observation,
    ProfileCircuit,
    ProfileRoom,
    QualityEvent,
    Recommendation,
    RecommendationSnapshot,
    SignalDefinition,
    SignalMapping,
    SourceEntity,
    SpecialPeriod,
)
from cvidee.store.repositories import (
    SqlNotificationPolicyRepository,
    SqlSettingsRepository,
    StaleRevisionError,
)
from cvidee.store.schema import alembic_config, upgrade_to_head

T0 = 1_791_100_800_000  # 2026-10-04T08:00:00Z in ms


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'cvidee.sqlite3'}"


@pytest.fixture
def engine(db_url: str) -> Iterator[Engine]:
    upgrade_to_head(db_url)
    eng = create_db_engine(db_url)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with create_session_factory(engine)() as s:
        yield s


def test_upgrade_head_creates_all_tables(engine: Engine) -> None:
    tables = set(inspect(engine).get_table_names())
    assert set(Base.metadata.tables) <= tables
    assert "alembic_version" in tables


def test_single_migration_head(db_url: str) -> None:
    script = ScriptDirectory.from_config(alembic_config(db_url))
    assert len(script.get_heads()) == 1


def test_models_match_migrations(engine: Engine) -> None:
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_downgrade_to_base_and_back(db_url: str) -> None:
    cfg = alembic_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    eng = create_db_engine(db_url)
    assert set(inspect(eng).get_table_names()) <= {"alembic_version"}
    eng.dispose()
    command.upgrade(cfg, "head")


def test_sqlite_pragmas(engine: Engine) -> None:
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert conn.execute(text("PRAGMA busy_timeout")).scalar() == 5000


def test_check_constraints_match_models(engine: Engine) -> None:
    """Autogenerate does not compare CHECK constraints; verify their names explicitly."""
    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        expected = {str(c.name) for c in table.constraints if isinstance(c, CheckConstraint)}
        actual = {str(c["name"]) for c in insp.get_check_constraints(table.name)}
        assert actual == expected, table.name


def _signal_setup(session: Session) -> SourceEntity:
    session.add(
        SignalDefinition(
            role="flame",
            value_type="boolean",
            unit=None,
            scope_type="none",
            default_kind=ValueKind.REPORTED,
            default_max_age_ms=30_000,
            required_for=["cycles"],
            catalogue_version="1",
        )
    )
    entity = SourceEntity(entity_id="binary_sensor.remeha_flame", first_seen_ts=T0, last_seen_ts=T0)
    session.add(entity)
    session.flush()
    return entity


def test_observation_round_trip_and_dedupe(session: Session) -> None:
    entity = _signal_setup(session)
    obs = Observation(
        source_entity_id=entity.id,
        ts=T0,
        state="on",
        value_num=1.0,
        kind=ObservationKind.CHANGE,
        reported_kind=ObservationKind.CHANGE,
        origin=ObservationOrigin.LIVE,
        received_at_ts=T0 + 5,
    )
    session.add(obs)
    session.commit()
    got = session.scalars(select(Observation)).one()
    assert (got.ts, got.state, got.kind) == (T0, "on", ObservationKind.CHANGE)
    # Enum stored by value, not by name.
    raw = session.execute(text("SELECT kind FROM observations")).scalar()
    assert raw == "change"

    session.add(
        Observation(
            source_entity_id=entity.id,
            ts=T0,
            state="on",
            value_num=1.0,
            kind=ObservationKind.POLL,
            reported_kind=ObservationKind.POLL,
            origin=ObservationOrigin.IMPORT,
            received_at_ts=T0 + 9,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_one_current_signal_mapping(session: Session) -> None:
    entity = _signal_setup(session)

    def mapping(valid_from: int, valid_to: int | None) -> SignalMapping:
        return SignalMapping(
            role="flame",
            scope_key="",
            source_entity_id=entity.id,
            kind=ValueKind.REPORTED,
            heartbeat_expected=False,
            max_age_ms=30_000,
            valid_from_ts=valid_from,
            valid_to_ts=valid_to,
            created_at_ts=T0,
        )

    session.add_all([mapping(T0, T0 + 1000), mapping(T0 + 1000, None)])
    session.commit()
    session.add(mapping(T0 + 2000, None))
    with pytest.raises(IntegrityError):
        session.flush()


def test_foreign_keys_enforced(session: Session) -> None:
    session.add(
        SignalMapping(
            role="does_not_exist",
            scope_key="",
            source_entity_id=999,
            kind=ValueKind.MEASURED,
            heartbeat_expected=False,
            max_age_ms=1000,
            valid_from_ts=T0,
            created_at_ts=T0,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_profile_specs_explicit_unknown(session: Session) -> None:
    profile = InstallationProfile(valid_from_ts=T0, created_at_ts=T0)
    profile.circuits = [
        ProfileCircuit(
            key="beneden", name="Beneden", kind=CircuitKind.DIRECT, emitter=EmitterType.RADIATOR
        ),
        ProfileCircuit(
            key="boven",
            name="Boven",
            kind=CircuitKind.MIXING_MANIFOLD,
            emitter=EmitterType.UNDERFLOOR,
        ),
    ]
    profile.rooms = [
        ProfileRoom(
            key="woonkamer",
            name="Woonkamer",
            circuit_key="beneden",
            has_thermostat=True,
            is_demand_source=True,
        )
    ]
    profile.specs = [
        InstallationSpec(
            key="max_flow_temperature", status=SpecStatus.KNOWN, value_num=60.0, unit="°C"
        ),
        InstallationSpec(key="min_power", status=SpecStatus.UNKNOWN),
        InstallationSpec(
            scope_key="circuit:boven", key="loop_count", status=SpecStatus.KNOWN, value_num=5
        ),
    ]
    session.add(profile)
    session.commit()
    got = session.get(InstallationProfile, profile.id)
    assert got is not None
    assert {s.key: s.status for s in got.specs}["min_power"] is SpecStatus.UNKNOWN
    assert {c.key: c.kind for c in got.circuits}["boven"] is CircuitKind.MIXING_MANIFOLD

    # Unknown with a value, or known without one, is rejected.
    session.add(
        InstallationSpec(
            profile_id=profile.id, key="max_ch_power", status=SpecStatus.UNKNOWN, value_num=24
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
    session.add(InstallationSpec(profile_id=profile.id, key="pump", status=SpecStatus.KNOWN))
    with pytest.raises(IntegrityError):
        session.flush()


def test_special_period_open_ended_and_check(session: Session) -> None:
    session.add(
        SpecialPeriod(
            kind=SpecialPeriodKind.COMMISSIONING, start_ts=T0, created_at_ts=T0, updated_at_ts=T0
        )
    )
    session.commit()
    session.add(
        SpecialPeriod(
            kind=SpecialPeriodKind.VACATION,
            start_ts=T0,
            end_ts=T0 - 1,
            created_at_ts=T0,
            updated_at_ts=T0,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_derived_round_trip(session: Session) -> None:
    # Open cycle at the horizon: no end, no end reason, provisional.
    session.add(
        BurnerCycle(
            start_ts=T0,
            end_ts=None,
            duration_ms=150_000,
            complete=False,
            start_observed=True,
            mode=Mode.CH,
            end_reason=None,
            heat_demand_during=TriState.YES,
            heat_demand_after_stop=TriState.UNKNOWN,
            signal_coverage=1.0,
            final=False,
        )
    )
    session.add(
        ModeSegment(
            start_ts=T0,
            end_ts=T0 + 3_600_000,
            mode=Mode.UNKNOWN,
            certainty=ModeCertainty.NONE,
            final=True,
        )
    )
    session.add(
        QualityEvent(
            kind=QualityEventKind.CONNECTION_LOST, signal="", start_ts=T0, end_ts=None, final=False
        )
    )
    session.add(
        MetricValue(
            name=MetricName.STARTS,
            mode="",
            window_kind=MetricWindowKind.HOUR,
            window_start_ts=T0,
            cycle_start_ts=-1,
            window_end_ts=T0 + 3_600_000,
            status=MetricStatus.INSUFFICIENT_DATA,
            value_num=None,
            unit="count",
            time_basis_seconds=0.0,
            coverage=0.0,
            provenance_kind=ValueKind.DERIVED,
            final=True,
        )
    )
    session.commit()
    cycle = session.get(BurnerCycle, T0)
    assert cycle is not None
    assert cycle.heat_demand_after_stop is TriState.UNKNOWN
    key = (MetricName.STARTS.value, "", MetricWindowKind.HOUR, T0, -1)
    metric = session.get(MetricValue, key)
    assert metric is not None
    assert metric.provenance_kind is ValueKind.DERIVED
    # IntEnum ValueKind is stored by lower-case name.
    raw = session.execute(text("SELECT provenance_kind FROM metric_values")).scalar()
    assert raw == "derived"


def test_closed_cycle_needs_end_reason(session: Session) -> None:
    session.add(
        BurnerCycle(
            start_ts=T0,
            end_ts=T0 + 60_000,
            duration_ms=60_000,
            complete=True,
            start_observed=True,
            mode=Mode.CH,
            end_reason=None,
            heat_demand_during=TriState.YES,
            heat_demand_after_stop=TriState.YES,
            signal_coverage=1.0,
            final=True,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_finding_recommendation_snapshot_change(session: Session) -> None:
    finding = Finding(
        human_id="B-014",
        rule_id="kort-branden",
        rule_version="1.3.0",
        category="cycles",
        title="Herhaald kort branden tijdens aanhoudende warmtevraag",
        severity=Severity.HIGH,
        certainty=Certainty.MODERATE,
        relevance=["operational_stability", "energy"],
        observation="In 18 van 24 cv-cycli …",
        interpretation="Dit past bij …",
        period_start_ts=T0,
        period_end_ts=T0 + 3_600_000,
        lifecycle=FindingLifecycle.ACTIVE,
        first_seen_ts=T0,
        last_seen_ts=T0,
        support={"coverage": 0.93, "relevant_cycles": 18, "total_cycles": 24},
    )
    finding.hypotheses = [FindingHypothesis(ordinal=1, name="Te weinig open afgifte")]
    finding.evidence = [
        FindingEvidence(kind=EvidenceKind.CYCLE, cycle_start_ts=T0),
        FindingEvidence(
            kind=EvidenceKind.BUNDLED_CANDIDATE,
            rule_id="stop-tijdens-vraag",
            rule_version="1.1.0",
            summary="18x brander stopt tijdens warmtevraag",
        ),
    ]
    session.add(finding)
    session.flush()
    rec = Recommendation(
        finding_id=finding.id,
        rule_id="kort-branden",
        rule_version="1.3.0",
        is_additional_measurement=True,
        action="Controleer welke circuits werkelijk open staan.",
        reason="Onderscheidt hypothese 1 en 2.",
        expected_effect="Geen direct energie-effect.",
        magnitude="Niet te onderbouwen met huidige gegevens — geen getal genoemd.",
        status=RecommendationStatus.OPEN,
        outcome=RecommendationOutcome.PENDING,
        created_at_ts=T0,
        status_changed_at_ts=T0,
        rollback_spec={"metric": "room_cold_hours_per_week", "op": ">", "threshold": 4},
    )
    session.add(rec)
    session.flush()
    session.add(
        RecommendationSnapshot(
            recommendation_id=rec.id,
            finding_id=finding.id,
            taken_at_ts=T0,
            trigger=SnapshotTrigger.CREATED,
            status=rec.status,
            outcome=rec.outcome,
            measurement_start_ts=T0,
            measurement_end_ts=T0 + 3_600_000,
            rule_id="kort-branden",
            rule_version="1.3.0",
            rule_params={"short_cycle_max_s": 180},
            config_hash="abc",
        )
    )
    change = Change(
        human_id="W-07",
        changed_at_ts=T0,
        recorded_at_ts=T0,
        performed_by=ChangeActor.USER,
        recommendation_id=rec.id,
    )
    change.items = [
        ChangeItem(
            ordinal=1,
            parameter_key="max_flow_temperature",
            parameter_label="Maximale CV-aanvoer",
            old_value="70 °C",
            new_value="60 °C",
            old_value_num=70,
            new_value_num=60,
            unit="°C",
        )
    ]
    change.evaluation = ChangeEvaluation(
        computed_at_ts=T0,
        reference_start_ts=T0 - 7 * 86_400_000,
        reference_end_ts=T0,
        observation_start_ts=T0 + 86_400_000,
        observation_end_ts=T0 + 8 * 86_400_000,
        verdict=EvaluationVerdict.TRADE_OFF,
        rollback_triggered=True,
        rule_version="1.2.0",
        config_hash="abc",
    )
    session.add(change)
    session.commit()

    got = session.scalars(select(Finding).where(Finding.human_id == "B-014")).one()
    assert [h.name for h in got.hypotheses] == ["Te weinig open afgifte"]
    assert got.recommendations[0].rollback_spec == {
        "metric": "room_cold_hours_per_week",
        "op": ">",
        "threshold": 4,
    }
    w07 = session.scalars(select(Change).where(Change.human_id == "W-07")).one()
    assert w07.evaluation is not None
    assert w07.evaluation.verdict is EvaluationVerdict.TRADE_OFF


def test_settings_repository_history_and_optimistic_lock(session: Session) -> None:
    repo = SqlSettingsRepository(session)
    assert repo.current() is None
    r1 = repo.save({"short_cycle_max_min": 3}, based_on=None, config_hash="h1", now_ts=T0)
    r2 = repo.save({"short_cycle_max_min": 4}, based_on=r1.id, config_hash="h2", now_ts=T0 + 1)
    current = repo.current()
    assert current is not None
    assert current.id == r2.id
    assert [r.config_hash for r in repo.history()] == ["h2", "h1"]
    with pytest.raises(StaleRevisionError):
        repo.save({}, based_on=r1.id, config_hash="h3", now_ts=T0 + 2)


def test_notification_policy_defaults_and_override(session: Session) -> None:
    repo = SqlNotificationPolicyRepository(session)
    assert repo.get_all()[Severity.HIGH] is NotificationChannel.DIRECT
    repo.set(Severity.HIGH, NotificationChannel.DAILY_DIGEST, T0)
    repo.set(Severity.HIGH, NotificationChannel.NONE, T0 + 1)
    assert repo.get_all()[Severity.HIGH] is NotificationChannel.NONE
    assert repo.get_all()[Severity.INFO] is NotificationChannel.NONE


def _quality(session: Session, **kw: Any) -> None:
    values: dict[str, Any] = {
        "kind": QualityEventKind.CONNECTION_LOST,
        "signal": "",
        "start_ts": T0,
        "end_ts": T0 + 1000,
        "final": True,
    }
    session.add(QualityEvent(**{**values, **kw}))
    session.flush()


def test_quality_event_key_allows_sources_and_other_signals(session: Session) -> None:
    _quality(session, source=ConnectionSource.WS)
    _quality(session, source=ConnectionSource.CAN_GATEWAY)
    for other in ("return_temperature@boiler", "outdoor_temperature"):
        _quality(
            session,
            kind=QualityEventKind.MISALIGNED,
            signal="flow_temperature@boiler",
            other_signal=other,
        )
    session.commit()
    assert session.scalar(select(func.count()).select_from(QualityEvent)) == 4
    # Same key (incl. NULL source) is still unique.
    _quality(session, kind=QualityEventKind.STALE, signal="x")
    with pytest.raises(IntegrityError):
        _quality(session, kind=QualityEventKind.STALE, signal="x")


def test_history_connection_source_and_mode_device_code(session: Session) -> None:
    session.add(ConnectionEvent(source=ConnectionSource.HISTORY, ts=T0, up=True))
    session.add(
        ModeSegment(
            start_ts=T0,
            end_ts=T0 + 3_600_000,
            mode=Mode.FAULT_BLOCKING,
            certainty=ModeCertainty.DIRECT,
            final=True,
            device_code="E:04",
        )
    )
    session.commit()
    assert session.scalars(select(ModeSegment.device_code)).one() == "E:04"


def test_migration_0003_down_and_up(db_url: str) -> None:
    cfg = alembic_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0002")
    command.upgrade(cfg, "head")
