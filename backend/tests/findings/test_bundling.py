"""Bundling keeps provenance without upgrading certainty or losing follow-up (#35)."""

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from cvidee.analysis.pipeline import run_pipeline
from cvidee.analysis.types import HOUR_MS, TimeRange
from cvidee.api.findings_read import FindingsReadModel
from cvidee.api.stubs.store import StubStore
from cvidee.findings.bundling import bundle_candidates
from cvidee.findings.engine import FindingsEngine
from cvidee.findings.repository import SqlFindingRepository
from cvidee.rules.base import CycleRef, RuleContext, SignalStatus, StaticTimelines
from cvidee.rules.registry import RuleOutcome, RuleRegistry, default_registry
from cvidee.store.engine import create_db_engine, create_session_factory, database_url
from cvidee.store.enums import (
    Certainty,
    EvidenceKind,
    FindingLifecycle,
    RecommendationStatus,
    ResolutionReason,
    Severity,
)
from cvidee.store.schema import upgrade_to_head
from tests.findings.dummy import DummyParams, DummyRule, Emit
from tests.findings.test_engine import NOW, make_ctx
from tests.rules.helpers import PROFILE
from tests.scenarios.harness import load_build, scenario_dirs


class Parent(DummyRule):
    id = "kort-branden"


class Child(DummyRule):
    id = "stop-tijdens-vraag"


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    url = database_url(tmp_path / "bundles.sqlite")
    upgrade_to_head(url)
    with create_session_factory(create_db_engine(url))() as session:
        yield session


def outcomes() -> tuple[RuleContext, RuleOutcome, RuleOutcome]:
    ctx = make_ctx(NOW)
    DummyRule.emit = (Emit(),)
    parent = RuleRegistry([Parent()]).evaluate(Parent.id, ctx, DummyParams())
    child = RuleRegistry([Child()]).evaluate(Child.id, ctx, DummyParams())
    child = replace(
        child,
        candidates=(
            replace(
                child.candidates[0], supports=(Parent.id,), observation="Ondersteunende waarneming"
            ),
        ),
    )
    DummyRule.emit = ()
    return ctx, parent, child


def test_order_does_not_change_bundle_or_parent_certainty() -> None:
    _ctx, parent, child = outcomes()
    first = bundle_candidates((parent, child), PROFILE)
    second = bundle_candidates((child, parent), PROFILE)
    assert first == second
    root = next(o for o in first.outcomes if o.snapshot.rule_id == Parent.id)
    assert root.candidates == parent.candidates
    assert first.parents == {(Child.id, "boiler:ch"): (Parent.id, "boiler:ch")}
    strong = replace(
        child,
        candidates=(
            replace(child.candidates[0], severity=Severity.HIGH, certainty=Certainty.HIGH_MEASURED),
        ),
    )
    stronger_plan = bundle_candidates((parent, strong), PROFILE)
    assert (
        next(o for o in stronger_plan.outcomes if o.snapshot.rule_id == Parent.id).candidates
        == parent.candidates
    )


def test_insufficient_supported_candidate_is_hidden_without_its_parent() -> None:
    ctx = make_ctx(NOW)
    DummyRule.emit = (Emit(certainty=Certainty.INSUFFICIENT_EVIDENCE),)
    child = RuleRegistry([Child()]).evaluate(Child.id, ctx, DummyParams())
    DummyRule.emit = ()
    candidate = replace(child.candidates[0], supports=(Parent.id,))
    plan = bundle_candidates((replace(child, candidates=(candidate,)),), PROFILE)
    assert plan.parents == {}
    assert all(not outcome.candidates for outcome in plan.outcomes)


@pytest.mark.parametrize(
    "variant", ["no-support", "other-scope", "touching", "other-cycles", "protected"]
)
def test_unrelated_or_protected_evidence_stays_independent(variant: str) -> None:
    _ctx, parent, child = outcomes()
    candidate = child.candidates[0]
    protected: frozenset[tuple[str, str]] = frozenset()
    if variant == "no-support":
        candidate = replace(candidate, supports=())
    if variant == "other-scope":
        candidate = replace(candidate, scope_key="room:slaapkamer")
    if variant == "touching":
        candidate = replace(
            candidate, period=TimeRange(parent.candidates[0].period.end, NOW + HOUR_MS)
        )
    if variant == "other-cycles":
        candidate = replace(candidate, refs=(CycleRef(NOW - 2 * HOUR_MS),))
    if variant == "protected":
        protected = frozenset({(Child.id, candidate.scope_key)})
    plan = bundle_candidates((parent, replace(child, candidates=(candidate,))), PROFILE, protected)
    assert plan.parents == {}
    assert len([c for o in plan.outcomes for c in o.candidates]) == 2


def test_database_and_api_preserve_original_source_and_links(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, parent, child = outcomes()
    registry = RuleRegistry([Parent(), Child()])
    monkeypatch.setattr(
        registry, "evaluate", lambda rule_id, *args: parent if rule_id == Parent.id else child
    )
    engine = FindingsEngine(registry, SqlFindingRepository(session))
    first = engine.evaluate(ctx)
    assert len(first.created) == 1
    session.commit()
    (finding,) = SqlFindingRepository(session).list_findings()
    original_score = finding.priority_score
    detail = FindingsReadModel(session, lambda: NOW).finding(finding.human_id)
    assert len(detail.bundle) == 1
    source = detail.bundle[0]
    assert source.rule is not None
    assert source.rule.id == Child.id
    assert source.rule.version == "1.0.0"
    assert source.parameters == {"threshold": 3}
    assert source.text == "Ondersteunende waarneming"
    assert source.evidence is not None
    assert source.evidence.pattern_cycles == child.candidates[0].evidence.pattern_cycles
    assert any(row.kind is EvidenceKind.BUNDLED_CANDIDATE for row in finding.evidence)
    assert any(
        row.rule_id == Child.id and row.kind is EvidenceKind.CYCLE for row in finding.evidence
    )
    assert engine.evaluate(ctx).created == []
    session.commit()
    assert finding.priority_score == original_score
    assert len(FindingsReadModel(session, lambda: NOW).finding(finding.human_id).bundle) == 1


def test_existing_child_is_superseded_not_recovered_and_reappears_if_parent_is_gone(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, parent, child = outcomes()
    registry = RuleRegistry([Parent(), Child()])
    state = {Parent.id: replace(parent, candidates=()), Child.id: child}
    monkeypatch.setattr(registry, "evaluate", lambda rule_id, *args: state[rule_id])
    engine = FindingsEngine(registry, SqlFindingRepository(session))
    old = engine.evaluate(ctx).created[0]
    state[Parent.id] = parent
    result = engine.evaluate(ctx)
    assert result.resolved[old] is ResolutionReason.SUPERSEDED
    session.commit()
    (root,) = SqlFindingRepository(session).list_findings()
    old_detail = FindingsReadModel(session, lambda: NOW).finding(old)
    assert old_detail.superseded_by == root.human_id
    assert root.support["bundled_candidates"][0]["source_finding_id"] == old
    state[Parent.id] = replace(parent, candidates=())
    returned = engine.evaluate(ctx)
    assert len(returned.created) == 1
    assert returned.created[0] != old


@pytest.mark.parametrize("with_notes", [False, True])
def test_followed_or_noted_child_is_not_hidden(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    with_notes: bool,
) -> None:
    ctx, parent, child = outcomes()
    candidate = replace(child.candidates[0], recommendation=parent.candidates[0].recommendation)
    # Dummy measurement advice is emitted only for insufficient evidence.
    from cvidee.rules.patterns import measurement

    candidate = replace(candidate, recommendation=measurement("Meet het signaal", "Ontbreekt"))
    child = replace(child, candidates=(candidate,))
    registry = RuleRegistry([Parent(), Child()])
    state = {Parent.id: replace(parent, candidates=()), Child.id: child}
    monkeypatch.setattr(registry, "evaluate", lambda rule_id, *args: state[rule_id])
    repo = SqlFindingRepository(session)
    engine = FindingsEngine(registry, repo)
    child_id = engine.evaluate(ctx).created[0]
    child_row = repo.by_human_id(child_id)
    assert child_row is not None
    rec = repo.recommendation_of(child_row)
    assert rec is not None
    if with_notes:
        from cvidee.store.models import RecommendationNote

        rec.notes.append(
            RecommendationNote(
                recommendation_id=rec.id,
                created_at_ts=NOW,
                text="Sensorplaatsing al gecontroleerd.",
            )
        )
    else:
        rec.status = RecommendationStatus.ACCEPTED
    state[Parent.id] = parent
    engine.evaluate(ctx)
    assert len(repo.list_findings()) == 2
    assert child_row.lifecycle is FindingLifecycle.ACTIVE


def test_disappearing_source_is_not_left_in_current_bundle(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, parent, child = outcomes()
    registry = RuleRegistry([Parent(), Child()])
    state = {Parent.id: parent, Child.id: child}
    monkeypatch.setattr(registry, "evaluate", lambda rule_id, *args: state[rule_id])
    engine = FindingsEngine(registry, SqlFindingRepository(session))
    engine.evaluate(ctx)
    state[Child.id] = replace(child, candidates=())
    engine.evaluate(ctx)
    session.commit()
    (root,) = SqlFindingRepository(session).list_findings()
    assert FindingsReadModel(session, lambda: NOW).finding(root.human_id).bundle == []


def test_overview_and_findings_use_the_same_priority_order() -> None:
    store = StubStore()
    assert [f.id for f in store.overview().findings.items] == [
        f.id for f in store.finding_list().items
    ]
    store.findings["B-012"] = store.findings["B-012"].model_copy(
        update={
            "severity": Severity.HIGH,
            "certainty": Certainty.HIGH_MEASURED,
            "period": store.findings["B-014"].period,
        }
    )
    assert store.finding_list().items[0].id == "B-012"
    assert store.overview().findings.items[0].id == "B-012"


def test_scenario_two_has_one_pattern_with_original_rule_versions(session: Session) -> None:
    data = load_build(next(path for path in scenario_dirs() if path.name == "02-kort-branden"))
    result = run_pipeline(
        data.observations,
        data.connection_events,
        data.config,
        data.window,
        data.end_ms + data.config.settle_ms,
    )
    period = TimeRange(data.start_ms, data.end_ms)
    from cvidee.rules.base import RuleContext

    ctx = RuleContext(
        now=data.end_ms,
        period=period,
        profile=PROFILE,
        signals=tuple(
            SignalStatus(t.signal, t.coverage(period), resolution_ms=4000) for t in result.timelines
        ),
        cycles=result.cycles,
        mode_segments=result.mode_segments,
        metrics=result.metrics,
        quality_events=result.quality_events,
        timelines=StaticTimelines(result.timelines),
    )
    registry = default_registry()
    # At least the stop and temperature rules emit supporting candidates independently.
    raw = {r.id: registry.evaluate(r.id, ctx, registry.default_params(r.id)) for r in registry}
    assert raw["stop-tijdens-vraag"].candidates
    assert raw["temperatuurverloop"].candidates
    FindingsEngine(registry, SqlFindingRepository(session)).evaluate(ctx)
    session.commit()
    findings = SqlFindingRepository(session).list_findings()
    # This fixture also contains six DHW cycles; its informational finding stays visible.
    assert {finding.rule_id for finding in findings} == {"kort-branden", "tapwater-uitgesloten"}
    patterns = [finding for finding in findings if finding.rule_id == "kort-branden"]
    assert len(patterns) == 1
    detail = FindingsReadModel(session, lambda: data.end_ms).finding(patterns[0].human_id)
    assert {source.rule.id for source in detail.bundle if source.rule is not None} >= {
        "stop-tijdens-vraag",
        "temperatuurverloop",
    }
    assert all(
        source.rule is not None and source.rule.version == raw[source.rule.id].snapshot.version
        for source in detail.bundle
    )


def test_snapshot_records_new_bundle_without_churning_each_live_tick(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from collections.abc import Sequence

    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker

    from cvidee.api.schemas.settings import SettingsIn
    from cvidee.rules.base import Certainty, FindingCandidate, RuleContext
    from cvidee.runner.service import AnalysisRunner, RunnerSettings
    from cvidee.settings.backend import SettingsBackend
    from cvidee.store.models import RecommendationSnapshot
    from tests.runner.test_runner import END, HUGE, seed

    class DynamicChild(Child):
        enabled = False

        def _evaluate(self, ctx: RuleContext, params: DummyParams) -> Sequence[FindingCandidate]:
            if not self.enabled:
                return ()
            return tuple(replace(c, supports=(Parent.id,)) for c in super()._evaluate(ctx, params))

    assert session.bind is not None
    factory = sessionmaker(bind=session.bind, expire_on_commit=False)
    seed(factory)
    child = DynamicChild()
    monkeypatch.setattr(DummyRule, "emit", (Emit(certainty=Certainty.INSUFFICIENT_EVIDENCE),))
    runner = AnalysisRunner(
        factory, RunnerSettings(chunk_ms=HUGE, registry=RuleRegistry([Parent(), child]))
    )
    backend = SettingsBackend(factory, runner)
    initial = backend.settings()
    backend.put_settings(
        SettingsIn(
            revision=initial.revision,
            values=initial.values.model_copy(update={"gas_price_eur_per_m3": 1.5}),
        )
    )
    first = runner.tick(END + 120_000)
    assert all(run.status.value == "succeeded" for run in first)
    with factory() as db:
        snapshots = list(db.scalars(select(RecommendationSnapshot)))
        assert len(snapshots) == 1
        assert snapshots[0].content["bundle"] == []
    child.enabled = True
    second = runner.tick(END + HOUR_MS + 120_000)
    assert first[-1].config_hash == second[-1].config_hash
    with factory() as db:
        snapshots = list(
            db.scalars(select(RecommendationSnapshot).order_by(RecommendationSnapshot.id))
        )
        assert len(snapshots) == 2
        assert snapshots[0].content["bundle"] == []
        assert snapshots[1].content["bundle"][0]["rule"]["id"] == Child.id
    runner.tick(END + 2 * HOUR_MS + 120_000)
    with factory() as db:
        assert len(list(db.scalars(select(RecommendationSnapshot)))) == 2
