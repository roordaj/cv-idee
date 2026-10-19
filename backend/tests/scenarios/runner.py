"""Real SQL ingestion and production runner for the unchanged MVP fixtures."""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cvidee.api.schemas.settings import SettingsIn
from cvidee.installation import default_profile
from cvidee.rules.availability import AvailabilityPolicy
from cvidee.rules.base import RuleContext, RuleParams
from cvidee.rules.registry import RuleOutcome, RuleRegistry, default_registry
from cvidee.runner.service import AnalysisRunner, RunnerSettings
from cvidee.settings.backend import SettingsBackend
from cvidee.signals.catalog import sync_catalogue
from cvidee.store.enums import ChangeActor, CircuitKind, ObservationOrigin, SpecialPeriodKind
from cvidee.store.models import (
    Change,
    ChangeItem,
    Finding,
    SignalMapping,
    SourceEntity,
    SpecialPeriod,
)
from cvidee.store.observations import SqlObservationRepository
from cvidee.store.records import ObservationRecord
from cvidee.testing.generator import GeneratedData
from tests.runner.test_runner import HUGE, make_db, settle_of
from tests.scenarios.harness import SCENARIO_ROOT, load_build


class RecordingRegistry(RuleRegistry):
    """Observe production outcomes without replacing any rule or availability logic."""

    def __init__(self) -> None:
        super().__init__(default_registry())
        self.context: RuleContext | None = None
        self.outcomes: dict[str, RuleOutcome] = {}
        self.cycling_lifecycles: list[tuple[int, tuple[tuple[str, str], ...]]] = []

    def evaluate(
        self,
        rule_id: str,
        ctx: RuleContext,
        params: RuleParams,
        policy: AvailabilityPolicy | None = None,
    ) -> RuleOutcome:
        self.context = ctx
        outcome = super().evaluate(rule_id, ctx, params, policy)
        self.outcomes[rule_id] = outcome
        return outcome


def run_scenario(
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
                    kind=config.provenance.kind,
                    heartbeat_expected=config.heartbeat_expected,
                    max_age_ms=config.max_age_ms or 300_000,
                    valid_from_ts=data.start_ms,
                    created_at_ts=data.start_ms,
                )
            )
        profile = default_profile(data.start_ms)
        profile.rooms = [room for room in profile.rooms if room.key in ("woonkamer", "slaapkamer")]
        if name != "06-mengverdeler-zonder-verdelerdata":
            for circuit in profile.circuits:
                circuit.kind = CircuitKind.DIRECT
        session.add(profile)
        for start, end, kind in data.special_periods:
            session.add(
                SpecialPeriod(
                    kind={"opstookprotocol": SpecialPeriodKind.COMMISSIONING}[kind],
                    start_ts=start,
                    end_ts=end,
                    created_at_ts=start,
                    updated_at_ts=start,
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
    runner = AnalysisRunner(
        factory, RunnerSettings(chunk_ms=HUGE, pipeline=data.config, registry=RecordingRegistry())
    )
    settings = SettingsBackend(factory, runner)
    current = settings.settings()
    settings.put_settings(
        SettingsIn(
            revision=current.revision,
            values=current.values.model_copy(update={"comparison_days": 3}),
        )
    )
    runs = []
    checkpoints = [data.end_ms]
    if data.gaps:
        checkpoints = sorted(
            {
                data.end_ms,
                *(at for start, end, _ in data.gaps for at in (start, (start + end) // 2, end)),
            }
        )
    for horizon in checkpoints:
        runs.extend(runner.tick(horizon + settle_of(runner)))
        with factory() as session:
            cycling = tuple(
                (f.human_id, f.lifecycle.value)
                for f in session.scalars(select(Finding).where(Finding.rule_id == "kort-branden"))
            )
            assert isinstance(runner.registry, RecordingRegistry)
            runner.registry.cycling_lifecycles.append((horizon, cycling))
    assert runs
    assert all(run.status.value == "succeeded" for run in runs)
    return factory, runner, data
