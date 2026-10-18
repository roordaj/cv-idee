"""Installation prehistory is excluded; late signals and internal gaps stay unknown."""

from pathlib import Path

from sqlalchemy import delete, select

from cvidee.analysis.types import HOUR_MS, Role
from cvidee.api.schemas.settings import AnalysisSettings
from cvidee.rules.availability import AvailabilityPolicy
from cvidee.rules.base import RuleContext, RuleParams
from cvidee.rules.registry import RuleOutcome, RuleRegistry, default_registry
from cvidee.runner.service import AnalysisRunner, RunnerSettings
from cvidee.store.enums import ObservationKind, ObservationOrigin
from cvidee.store.models import Observation, SourceEntity
from cvidee.store.observations import SqlObservationRepository
from cvidee.store.records import ObservationRecord
from tests.runner.test_runner import DEMAND, END, FLAME, HUGE, T0, make_db, seed, settle_of


class RecordingRegistry(RuleRegistry):
    def __init__(self) -> None:
        super().__init__(default_registry())
        self.context: RuleContext | None = None

    def evaluate(
        self,
        rule_id: str,
        ctx: RuleContext,
        params: RuleParams,
        policy: AvailabilityPolicy | None = None,
    ) -> RuleOutcome:
        self.context = ctx
        return super().evaluate(rule_id, ctx, params, policy)


def test_first_installation_does_not_count_pre_mapping_data_or_hide_late_signal(
    tmp_path: Path,
) -> None:
    factory = make_db(tmp_path)
    seed(factory)
    with factory.begin() as session:
        repo = SqlObservationRepository(session)
        # Raw history outside every mapping's validity must not move the start back.
        repo.add_observations(
            [
                ObservationRecord(
                    entity_id=FLAME,
                    ts=T0 - 4 * HOUR_MS,
                    state="off",
                    value_num=0,
                    kind=ObservationKind.POLL,
                    origin=ObservationOrigin.IMPORT,
                    received_at_ts=T0,
                )
            ]
        )
        demand = session.scalar(select(SourceEntity.id).where(SourceEntity.entity_id == DEMAND))
        session.execute(
            delete(Observation).where(
                Observation.source_entity_id == demand,
                Observation.ts < T0 + 4 * HOUR_MS,
            )
        )
    registry = RecordingRegistry()
    runner = AnalysisRunner(factory, RunnerSettings(chunk_ms=HUGE, registry=registry))
    runs = runner.tick(END + settle_of(runner))
    assert runs
    assert all(run.status.value == "succeeded" for run in runs)
    ctx = registry.context
    assert ctx is not None
    assert ctx.period.start == T0
    assert ctx.period.end == END
    flame = next(s for s in ctx.signals if s.signal.role is Role.FLAME)
    demand_status = next(s for s in ctx.signals if s.signal.role is Role.HEAT_DEMAND)
    # The existing 20-minute WS outage stays in the denominator for both signals.
    assert flame.coverage > AnalysisSettings().min_assessment_coverage_pct / 100
    assert flame.coverage < 1
    assert demand_status.coverage < 10 / 14
    assert flame.coverage > demand_status.coverage
