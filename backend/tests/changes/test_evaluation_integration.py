"""Scenario evaluations pass through real SQL storage, runner, rules and API."""

from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cvidee.api.schemas.settings import SettingsIn
from cvidee.changes.evaluation import evaluate_changes
from cvidee.config import Settings
from cvidee.installation import SqlInstallationProfileRepository, profile_facts
from cvidee.main import create_app
from cvidee.rules.availability import assess_analyses
from cvidee.rules.base import AnalysisId, AvailabilityStatus
from cvidee.runner.service import AnalysisRunner, RunnerSettings
from cvidee.runner.sources import SourceSettings, build_pipeline_config, load_mapped_signals
from cvidee.settings.backend import SettingsBackend
from cvidee.settings.repository import current_revision, effective_values
from cvidee.signals.backend import SignalsBackend
from cvidee.signals.catalog import sync_catalogue
from cvidee.store.enums import ChangeActor, ObservationOrigin, RecommendationStatus
from cvidee.store.models import (
    Change,
    ChangeItem,
    Finding,
    Recommendation,
    RecommendationSnapshot,
    SignalMapping,
    SourceEntity,
)
from cvidee.store.observations import SqlObservationRepository
from cvidee.store.records import ObservationRecord
from cvidee.testing.generator import GeneratedData
from tests.runner.test_runner import HUGE, make_db, settle_of
from tests.scenarios.harness import SCENARIO_ROOT, load_build


def seed_evaluation(
    tmp_path: Path, name: str
) -> tuple[sessionmaker[Session], AnalysisRunner, GeneratedData]:
    data = load_build(SCENARIO_ROOT / name)
    factory = make_db(tmp_path, name)
    entities = {
        signal: f"sensor.synthetic_{signal.role}_{signal.scope.key or signal.scope.kind}"
        for signal in data.signals
    }
    with factory.begin() as session:
        sync_catalogue(session)
        records = []
        for observation in data.observations:
            value = observation.value
            state = (
                "unavailable"
                if value is None
                else "on"
                if value is True
                else "off"
                if value is False
                else str(value)
            )
            try:
                numeric = float(state)
            except ValueError:
                numeric = None
            records.append(
                ObservationRecord(
                    entity_id=entities[observation.signal],
                    ts=observation.ts,
                    state=state,
                    value_num=numeric,
                    kind=observation.kind,
                    origin=ObservationOrigin.LIVE,
                    received_at_ts=observation.ts,
                    last_reported_ts=observation.last_reported,
                )
            )
        SqlObservationRepository(session).add_observations(records)
        SqlObservationRepository(session).add_connection_events(data.connection_events)
        for config in data.config.signals:
            entity = session.scalar(
                select(SourceEntity).where(SourceEntity.entity_id == entities[config.signal])
            )
            assert entity is not None
            scope = config.signal.scope
            session.add(
                SignalMapping(
                    role=config.signal.role.value,
                    scope_key=f"{scope.kind}:{scope.key}" if scope.key is not None else "",
                    source_entity_id=entity.id,
                    value_map={code: mode.value for code, mode in data.config.mode_mapping}
                    if config.signal.role.value == "operating_mode"
                    else None,
                    meaning="Explicit synthetic scenario mode table"
                    if config.signal.role.value == "operating_mode" and data.config.mode_mapping
                    else None,
                    kind=config.provenance.kind,
                    heartbeat_expected=config.heartbeat_expected,
                    max_age_ms=config.max_age_ms or 300_000,
                    valid_from_ts=data.start_ms,
                    created_at_ts=data.start_ms,
                )
            )
        for number, (at, parameter, old, new) in enumerate(data.changes, 1):
            session.add(
                Change(
                    human_id=f"W-{number:02d}",
                    changed_at_ts=at,
                    recorded_at_ts=at,
                    performed_by=ChangeActor.USER,
                    reason="Synthetische proef",
                    items=[
                        ChangeItem(
                            ordinal=1,
                            parameter_key=parameter,
                            parameter_label=parameter,
                            old_value=old,
                            new_value=new,
                        )
                    ],
                )
            )
    runner = AnalysisRunner(factory, RunnerSettings(chunk_ms=HUGE, pipeline=data.config))
    settings = SettingsBackend(factory, runner)
    current = settings.settings()
    settings.put_settings(
        SettingsIn(
            revision=current.revision,
            values=current.values.model_copy(update={"comparison_days": 3}),
        )
    )
    runs = runner.tick(data.end_ms + settle_of(runner))
    assert runs
    assert all(run.status.value == "succeeded" for run in runs)
    return factory, runner, data


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("07-aanvoerwijziging-comfort", AvailabilityStatus.AVAILABLE),
        ("08-gelijktijdige-wijzigingen", AvailabilityStatus.LIMITED),
        ("10-onvoldoende-gegevens", AvailabilityStatus.UNAVAILABLE),
    ],
)
def test_before_after_analysis_availability_uses_production_evaluation(
    tmp_path: Path, name: str, expected: AvailabilityStatus
) -> None:
    factory, runner, data = seed_evaluation(tmp_path, name)
    with factory.begin() as session:
        now = data.end_ms
        profile = profile_facts(SqlInstallationProfileRepository(session).current_or_default(now))
        settings = effective_values(current_revision(session))
        mapped = load_mapped_signals(session)
        config = build_pipeline_config(session, mapped, SourceSettings())
        evaluations = evaluate_changes(session, now, settings, config)
        statuses = assess_analyses((), profile, change_evaluations=evaluations)
    before_after = next(item for item in statuses if item.analysis is AnalysisId.BEFORE_AFTER)
    assert before_after.availability.status is expected
    read_model = SignalsBackend(factory, runner=runner, clock=lambda: data.end_ms).analyses()
    api_item = next(item for item in read_model.items if item.id is AnalysisId.BEFORE_AFTER)
    assert api_item.status is expected
    if expected is AvailabilityStatus.UNAVAILABLE and name.endswith("10-onvoldoende-gegevens"):
        assert before_after.availability.issues
        assert "geen wijziging vastgelegd" in api_item.note


async def test_real_runner_and_api_show_trade_off_and_preserve_rollback_history(
    tmp_path: Path,
) -> None:
    factory, runner, data = seed_evaluation(tmp_path, "07-aanvoerwijziging-comfort")
    with factory.begin() as session:
        findings = list(session.scalars(select(Finding).where(Finding.rule_id == "voor-na")))
        assert len(findings) == 1
        assert findings[0].severity.value == "medium"
        assert findings[0].certainty.value == "reasonable"
        change = session.scalar(select(Change))
        assert change is not None
        assert change.evaluation is not None
        assert change.evaluation.verdict.value == "trade_off"
        assert change.evaluation.rollback_triggered
        original = session.scalar(select(Finding).where(Finding.rule_id == "kort-branden"))
        assert original is not None
        rec = original.recommendations[-1]
        rec.status = RecommendationStatus.DONE
        change.recommendation_id = rec.id
        rec_id = rec.id
    app = create_app(Settings.model_validate({}))
    app.state.session_factory, app.state.runner = factory, runner
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/changes/W-01/evaluation")
        assert response.status_code == 200
        body = response.json()
        assert body["verdict"] == "trade_off"
        assert any(
            "slaapkamer" in metric["label"] and metric["assessment"] == "worse"
            for metric in body["metrics"]
        )
        assert "terugdraaicriterium" in body["summary"]
        assert (await client.get("/api/changes")).json()["items"][0]["rollback_advised"]
        with factory() as session:
            history = list(
                session.scalars(
                    select(RecommendationSnapshot).where(
                        RecommendationSnapshot.recommendation_id == rec_id
                    )
                )
            )
            assert history[-1].status is RecommendationStatus.ROLLBACK_TRIGGERED
        await client.get("/api/changes/W-01/evaluation")
        with factory() as session:
            after = list(
                session.scalars(
                    select(RecommendationSnapshot).where(
                        RecommendationSnapshot.recommendation_id == rec_id
                    )
                )
            )
            assert len(after) == len(history)
        entries = (await client.get("/api/history")).json()["items"]
        recorded = next(entry for entry in entries if entry["status"] == "rollback_triggered")
        assert recorded["change_evaluation"]["verdict"] == "trade_off"
        assert recorded["evaluation_parameters"]["comfort_deficit_c"] == 0.5

        settings = SettingsBackend(factory, runner)
        current = settings.settings()
        settings.put_settings(
            SettingsIn(
                revision=current.revision,
                values=current.values.model_copy(update={"comfort_margin_c": 1.5}),
            )
        )
        entries = (await client.get("/api/history")).json()["items"]
        saved = next(entry for entry in entries if entry["id"] == recorded["id"])
        assert saved["change_evaluation"] == recorded["change_evaluation"]
        assert saved["evaluation_parameters"] == recorded["evaluation_parameters"]
        assert "voor/na-evaluatie zijn sindsdien gewijzigd" in saved["rule_now_text"]
        with factory.begin() as session:
            loaded_rec = session.get(Recommendation, rec_id)
            assert loaded_rec is not None
            loaded_rec.rollback_spec = {"metric": "unsupported", "threshold": 4}
        result = (await client.get("/api/changes/W-01/evaluation")).json()
        assert "niet automatisch" in result["summary"]
        with factory() as session:
            loaded_rec = session.get(Recommendation, rec_id)
            assert loaded_rec is not None
            assert loaded_rec.status is RecommendationStatus.ROLLBACK_TRIGGERED
            assert loaded_rec.outcome.value == "unfavourable"
    assert data.changes


async def test_experiment_reuses_change_evaluation_and_persists_lifecycle(tmp_path: Path) -> None:
    factory, runner, _ = seed_evaluation(tmp_path, "07-aanvoerwijziging-comfort")
    app = create_app(Settings.model_validate({}))
    app.state.session_factory, app.state.runner = factory, runner
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        comparison = (await client.get("/api/changes/W-01/evaluation")).json()
        created = await client.post("/api/experiments", json={"change_id": "W-01"})
        assert created.status_code == 201
        body = created.json()
        assert body["evaluation"] == comparison
        assert body["status"] == "completed"
        assert body["completed_at"] is not None
        assert (await client.get("/api/experiments/W-01")).json()["evaluation"] == comparison
        assert (await client.get("/api/experiments?limit=1")).json()["total"] == 1
        duplicate = await client.post("/api/experiments", json={"change_id": "W-01"})
        assert duplicate.status_code == 409
        assert (await client.post("/api/experiments/W-01/end")).status_code == 409


async def test_experiment_keeps_existing_overlap_verdict(tmp_path: Path) -> None:
    factory, runner, _ = seed_evaluation(tmp_path, "08-gelijktijdige-wijzigingen")
    app = create_app(Settings.model_validate({}))
    app.state.session_factory, app.state.runner = factory, runner
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        current = (await client.get("/api/changes/W-01/evaluation")).json()
        created = await client.post("/api/experiments", json={"change_id": "W-01"})
        assert created.status_code == 201
        assert created.json()["evaluation"] == current
        assert created.json()["evaluation"]["verdict"] == "not_attributable"


def test_real_runner_bundles_simultaneous_changes_without_attribution(tmp_path: Path) -> None:
    factory, _, _ = seed_evaluation(tmp_path, "08-gelijktijdige-wijzigingen")
    with factory() as session:
        findings = list(session.scalars(select(Finding).where(Finding.rule_id == "voor-na")))
        assert len(findings) == 1
        assert findings[0].severity.value == "info"
        assert findings[0].certainty.value == "preliminary"
        changes = list(session.scalars(select(Change)))
        assert len(changes) == 2
        assert all(
            change.evaluation is not None and change.evaluation.verdict.value == "not_attributable"
            for change in changes
        )
