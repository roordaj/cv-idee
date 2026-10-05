"""Findings engine: dedupe, lifecycle, recovery vs data gap, prioritisation (#34)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from cvidee.analysis.types import HOUR_MS, TimeRange
from cvidee.findings.engine import FindingsEngine, RecoverySettings
from cvidee.findings.priority import prioritise
from cvidee.findings.repository import SqlFindingRepository
from cvidee.rules.base import (
    Certainty,
    Relevance,
    RuleContext,
    RuleParams,
    Severity,
    StaticTimelines,
)
from cvidee.rules.registry import RuleRegistry
from cvidee.store.engine import create_db_engine, create_session_factory, database_url
from cvidee.store.enums import (
    EvidenceKind,
    FindingLifecycle,
    RecommendationStatus,
    ResolutionReason,
)
from cvidee.store.models import Finding
from cvidee.store.schema import upgrade_to_head
from tests.rules.helpers import PROFILE, boiler_signals

from .dummy import DAY_MS, FLAME, OUTDOOR, T0, DummyParams, DummyRule, Emit, timeline

NOW = T0 + 10 * DAY_MS


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    url = database_url(tmp_path / "findings.sqlite")
    upgrade_to_head(url)
    with create_session_factory(create_db_engine(url))() as s:
        yield s


@pytest.fixture(autouse=True)
def _reset_emit() -> Iterator[None]:
    DummyRule.emit = ()
    yield
    DummyRule.emit = ()


def make_ctx(
    now: int,
    *,
    flame_gap: TimeRange | None = None,
    flame_mapped: bool = True,
    outdoor_step: tuple[int, float] | None = None,
) -> RuleContext:
    period = TimeRange(now - 7 * DAY_MS, now)
    span = TimeRange(now - 30 * DAY_MS, now)
    timelines = [timeline(OUTDOOR, span, 8.0, step=outdoor_step)]
    if flame_mapped:
        timelines.append(timeline(FLAME, span, True, gap=flame_gap))
    from cvidee.analysis.types import Role

    return RuleContext(
        now=now,
        period=period,
        profile=PROFILE,
        signals=boiler_signals(without=() if flame_mapped else (Role.FLAME,)),
        timelines=StaticTimelines(tuple(timelines)),
    )


def engine(
    session: Session,
    recovery: RecoverySettings | None = None,
    threshold: int = 3,
) -> FindingsEngine:
    registry = RuleRegistry([DummyRule()])

    def params_for(rule_id: str) -> RuleParams:
        return DummyParams(threshold=threshold)

    return FindingsEngine(registry, SqlFindingRepository(session), recovery, params_for)


def all_findings(session: Session) -> list[Finding]:
    return SqlFindingRepository(session).list_findings(include_resolved=True)


# -- dedupe ----------------------------------------------------------------------------


def test_same_problem_is_one_finding_updated_per_cycle(session: Session) -> None:
    DummyRule.emit = (Emit(),)
    eng = engine(session)
    first = eng.evaluate(make_ctx(NOW), run_id=None)
    assert first.created == ["B-001"]
    for hour in (1, 2, 3):
        res = eng.evaluate(make_ctx(NOW + hour * HOUR_MS), run_id=None)
        assert res.created == []
        assert res.updated == ["B-001"]
    (finding,) = all_findings(session)
    assert finding.human_id == "B-001"
    assert finding.first_seen_ts == NOW
    assert finding.last_seen_ts == NOW + 3 * HOUR_MS
    assert finding.period_end_ts == NOW + 3 * HOUR_MS
    assert finding.support["relevant_cycles"] == 10
    assert finding.support["pattern_cycles"] == 6
    assert finding.support["repetition_days"] == 2
    kinds = sorted(str(e.kind) for e in finding.evidence)
    assert kinds.count(str(EvidenceKind.CYCLE)) == 1  # replaced, not accumulated
    assert EvidenceKind.TIME_RANGE in {e.kind for e in finding.evidence}
    assert finding.priority_explanation["factors"][0]["factor"] == "severity"


def test_second_scope_gets_next_human_id(session: Session) -> None:
    DummyRule.emit = (Emit("boiler:ch"), Emit("room:slaapkamer"))
    res = engine(session).evaluate(make_ctx(NOW), run_id=None)
    assert sorted(res.created) == ["B-001", "B-002"]


def test_insufficient_evidence_proposes_measurement(session: Session) -> None:
    DummyRule.emit = (Emit(certainty=Certainty.INSUFFICIENT_EVIDENCE),)
    engine(session).evaluate(make_ctx(NOW), run_id=None)
    repo = SqlFindingRepository(session)
    finding = repo.by_human_id("B-001")
    assert finding is not None
    assert finding.certainty is Certainty.INSUFFICIENT_EVIDENCE
    rec = repo.recommendation_of(finding)
    assert rec is not None
    assert rec.is_additional_measurement
    assert rec.status is RecommendationStatus.OPEN
    assert rec.magnitude.startswith("Niet te onderbouwen")


# -- recovery --------------------------------------------------------------------------


def seen_at_now(session: Session) -> FindingsEngine:
    DummyRule.emit = (Emit(),)
    eng = engine(session)
    eng.evaluate(make_ctx(NOW), run_id=None)
    DummyRule.emit = ()
    return eng


def test_closes_as_recovered_after_pattern_free_days(session: Session) -> None:
    eng = seen_at_now(session)
    early = eng.evaluate(make_ctx(NOW + 1 * DAY_MS), run_id=None)
    assert early.resolved == {}  # only 1 of 3 days without the pattern
    done = eng.evaluate(make_ctx(NOW + 3 * DAY_MS + HOUR_MS), run_id=None)
    assert done.resolved == {"B-001": ResolutionReason.RECOVERED}
    (finding,) = all_findings(session)
    assert finding.lifecycle is FindingLifecycle.RESOLVED
    assert finding.resolution_reason is ResolutionReason.RECOVERED
    assert finding.resolved_at_ts == NOW + 3 * DAY_MS + HOUR_MS


def test_recovery_days_are_configurable(session: Session) -> None:
    DummyRule.emit = (Emit(),)
    eng = engine(session, RecoverySettings(days_without_pattern=1))
    eng.evaluate(make_ctx(NOW), run_id=None)
    DummyRule.emit = ()
    done = eng.evaluate(make_ctx(NOW + DAY_MS + HOUR_MS), run_id=None)
    assert done.resolved == {"B-001": ResolutionReason.RECOVERED}


def test_data_gap_is_not_recovery(session: Session) -> None:
    eng = seen_at_now(session)
    now = NOW + 4 * DAY_MS
    gap = TimeRange(NOW + HOUR_MS, NOW + 3 * DAY_MS)  # most of the pattern-free window
    res = eng.evaluate(make_ctx(now, flame_gap=gap), run_id=None)
    assert res.resolved == {}
    # Once the data is back for the whole window, it does close.
    res = eng.evaluate(make_ctx(now), run_id=None)
    assert res.resolved == {"B-001": ResolutionReason.RECOVERED}


def test_unmapped_signal_is_not_recovery(session: Session) -> None:
    eng = seen_at_now(session)
    res = eng.evaluate(make_ctx(NOW + 5 * DAY_MS, flame_mapped=False), run_id=None)
    assert res.resolved == {}
    assert all_findings(session)[0].lifecycle is FindingLifecycle.ACTIVE


def test_not_comparable_weather_blocks_recovery(session: Session) -> None:
    eng = seen_at_now(session)
    now = NOW + 4 * DAY_MS
    warm_after = make_ctx(now, outdoor_step=(NOW + HOUR_MS, 20.0))
    assert eng.evaluate(warm_after, run_id=None).resolved == {}
    relaxed = engine(session, RecoverySettings(require_comparable_weather=False))
    assert relaxed.evaluate(warm_after, run_id=None).resolved == {
        "B-001": ResolutionReason.RECOVERED
    }


def test_recurrence_after_recovery_is_a_new_finding(session: Session) -> None:
    eng = seen_at_now(session)
    eng.evaluate(make_ctx(NOW + 4 * DAY_MS), run_id=None)
    DummyRule.emit = (Emit(),)
    res = eng.evaluate(make_ctx(NOW + 6 * DAY_MS), run_id=None)
    assert res.created == ["B-002"]
    states = {f.human_id: f.lifecycle for f in all_findings(session)}
    assert states == {"B-001": FindingLifecycle.RESOLVED, "B-002": FindingLifecycle.ACTIVE}


# -- settings change -------------------------------------------------------------------


def test_settings_change_closes_with_its_own_reason(session: Session) -> None:
    eng = seen_at_now(session)
    changed = engine(session, threshold=5)  # new threshold: rule no longer emits
    res = changed.evaluate(make_ctx(NOW + HOUR_MS), run_id=None)
    assert res.resolved == {"B-001": ResolutionReason.SETTINGS_CHANGED}
    assert eng is not changed


def test_settings_change_during_data_gap_does_not_close(session: Session) -> None:
    seen_at_now(session)
    changed = engine(session, threshold=5)
    gap = TimeRange(NOW - 6 * DAY_MS, NOW + 1 * HOUR_MS)
    res = changed.evaluate(make_ctx(NOW + HOUR_MS, flame_gap=gap), run_id=None)
    assert res.resolved == {}


def test_still_emitted_after_settings_change_stays_open_with_new_params(session: Session) -> None:
    DummyRule.emit = (Emit(),)
    engine(session).evaluate(make_ctx(NOW), run_id=None)
    res = engine(session, threshold=5).evaluate(make_ctx(NOW + HOUR_MS), run_id=None)
    assert res.resolved == {}
    assert res.updated == ["B-001"]
    assert all_findings(session)[0].rule_params == {"threshold": 5}


# -- prioritisation --------------------------------------------------------------------


def test_priority_orders_severity_certainty_relevance_recency() -> None:
    def score(
        sev: Severity = Severity.MEDIUM,
        cert: Certainty = Certainty.MODERATE,
        rel: tuple[Relevance, ...] = (Relevance.ENERGY,),
        age_days: int = 0,
    ) -> float:
        return prioritise(sev, cert, rel, NOW - age_days * DAY_MS, NOW).score

    base = score()
    assert score(sev=Severity.HIGH) > base > score(sev=Severity.LOW) > score(sev=Severity.INFO)
    assert score(cert=Certainty.HIGH) > base > score(cert=Certainty.PRELIMINARY)
    assert score(rel=(Relevance.DATA_RELIABILITY,)) < base
    assert score(rel=(Relevance.DATA_RELIABILITY, Relevance.ENERGY)) == base
    assert base > score(age_days=7) > score(age_days=30)
    assert score(age_days=30) == score(age_days=300)  # floor
    assert prioritise(Severity.HIGH, Certainty.HIGH, (), NOW, NOW) == prioritise(
        Severity.HIGH, Certainty.HIGH, (), NOW, NOW
    )  # deterministic


def test_priority_explanation_lists_factors() -> None:
    p = prioritise(Severity.HIGH, Certainty.MODERATE, (Relevance.COMFORT,), NOW - DAY_MS, NOW)
    assert [f["factor"] for f in p.explanation["factors"]] == [
        "severity",
        "certainty",
        "relevance",
        "recency",
    ]
    product = 1.0
    for f in p.explanation["factors"]:
        product *= f["weight"]
    assert p.score == pytest.approx(product, abs=1e-6)


def test_list_is_ordered_by_priority(session: Session) -> None:
    DummyRule.emit = (
        Emit("a", Severity.LOW),
        Emit("b", Severity.HIGH, Certainty.HIGH),
        Emit("c", Severity.MEDIUM),
    )
    engine(session).evaluate(make_ctx(NOW), run_id=None)
    ordered = [f.scope_key for f in SqlFindingRepository(session).list_findings()]
    assert ordered == ["b", "c", "a"]
