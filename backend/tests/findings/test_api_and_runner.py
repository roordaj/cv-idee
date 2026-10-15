"""Real GET /api/findings over persisted findings, and the runner integration (#34)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy.orm import Session, sessionmaker

from cvidee.analysis.types import HOUR_MS
from cvidee.config import Settings
from cvidee.findings.engine import FindingsEngine
from cvidee.findings.repository import SqlFindingRepository
from cvidee.main import create_app
from cvidee.rules.base import Certainty, Severity
from cvidee.rules.registry import RuleRegistry
from cvidee.runner.service import AnalysisRunner, RunnerSettings
from cvidee.store.engine import create_db_engine, create_session_factory, database_url
from cvidee.store.models import Finding
from cvidee.store.schema import upgrade_to_head
from tests.runner.test_runner import END, HUGE, make_db, seed, settle_of

from .dummy import DummyRule, Emit
from .test_engine import NOW, make_ctx


@pytest.fixture(autouse=True)
def _reset_emit() -> Iterator[None]:
    DummyRule.emit = ()
    yield
    DummyRule.emit = ()


@pytest.fixture
def factory(tmp_path: Path) -> sessionmaker[Session]:
    url = database_url(tmp_path / "api.sqlite")
    upgrade_to_head(url)
    return create_session_factory(create_db_engine(url))


@pytest.fixture
async def client(factory: sessionmaker[Session]) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(Settings.model_validate({}))
    app.state.session_factory = factory
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


def persist(factory: sessionmaker[Session], *emit: Emit) -> None:
    DummyRule.emit = emit
    with factory.begin() as session:
        FindingsEngine(RuleRegistry([DummyRule()]), SqlFindingRepository(session)).evaluate(
            make_ctx(NOW), run_id=None
        )


async def test_list_returns_persisted_findings_by_priority(
    client: httpx.AsyncClient, factory: sessionmaker[Session]
) -> None:
    persist(
        factory,
        Emit("a", Severity.LOW),
        Emit("b", Severity.HIGH, Certainty.HIGH),
        Emit("c", Severity.INFO, Certainty.INSUFFICIENT_EVIDENCE),
    )
    body = (await client.get("/api/findings")).json()
    assert [i["title"] for i in body["items"]] == ["Dummy b", "Dummy a", "Dummy c"]
    assert [i["id"] for i in body["items"]] == ["B-002", "B-001", "B-003"]
    assert body["open_count"] == 1  # only the measurement advice is a recommendation
    assert body["items"][2]["certainty"] == "insufficient_evidence"
    assert body["items"][0]["status_text"] == "Open"


async def test_detail_has_evidence_links_and_priority(
    client: httpx.AsyncClient, factory: sessionmaker[Session]
) -> None:
    persist(factory, Emit(certainty=Certainty.INSUFFICIENT_EVIDENCE))
    body = (await client.get("/api/findings/B-001")).json()
    assert body["rule"] == {"id": "dummy-regel", "version": "1.0.0"}
    assert body["observation"].startswith("Waargenomen op boiler:ch")
    assert body["evidence"]["display"]["cycles"] == "6 van 10 cv-cycli"
    assert body["evidence"]["display"]["repetition"] == "2 van laatste 7 dagen"
    kinds = {link["kind"] for link in body["evidence_links"]}
    assert {"time_range", "cycle", "signal"} <= kinds
    cycle = next(link for link in body["evidence_links"] if link["kind"] == "cycle")
    assert cycle["start"].endswith("Z")
    assert body["timeline_range"] is not None
    assert body["recommendation"]["kind"] == "measurement"
    assert body["priority"]["factors"][0]["factor"] == "severity"
    assert body["priority"]["score"] > 0


async def test_unknown_finding_is_404(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/findings/B-999")
    assert resp.status_code == 404
    assert (await client.get("/api/findings")).json() == {"items": [], "open_count": 0}


async def test_routes_without_database_are_501() -> None:
    app = create_app(Settings.model_validate({}))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        assert (await ac.get("/api/findings")).status_code == 501


def test_runner_evaluates_registry_and_persists(tmp_path: Path) -> None:
    f = make_db(tmp_path, "runner")
    seed(f)
    DummyRule.emit = (Emit(),)
    registry = RuleRegistry([DummyRule()])
    runner = AnalysisRunner(f, RunnerSettings(chunk_ms=HUGE, registry=registry))
    assert runner.settings.rule_versions == {"dummy-regel": "1.0.0"}
    runner.tick(END + settle_of(runner))
    runner.tick(END + HOUR_MS + settle_of(runner))
    with f() as session:
        (finding,) = SqlFindingRepository(session).list_findings()
        assert isinstance(finding, Finding)
        assert finding.human_id == "B-001"  # deduped over several runs
        assert finding.last_run_id is not None
        assert finding.last_seen_ts > finding.first_seen_ts


async def test_follow_up_and_notes_survive_new_requests(
    client: httpx.AsyncClient, factory: sessionmaker[Session]
) -> None:
    persist(factory, Emit(certainty=Certainty.INSUFFICIENT_EVIDENCE))
    for status in ("accepted", "postponed", "done", "rejected", "open"):
        response = await client.post("/api/findings/B-001/status", json={"status": status})
        assert response.status_code == 200
        assert response.json()["status"] == status
        detail = (await client.get("/api/findings/B-001")).json()
        assert detail["status"] == status
        assert (detail["postponed_until"] is not None) == (status == "postponed")
    response = await client.post("/api/findings/B-001/notes", json={"text": "  Eerst meten.  "})
    assert response.status_code == 201
    note = response.json()
    assert note["text"] == "Eerst meten."
    assert (await client.get("/api/findings/B-001")).json()["notes"] == [note]


async def test_follow_up_rejects_invalid_input_and_missing_advice(
    client: httpx.AsyncClient, factory: sessionmaker[Session]
) -> None:
    persist(factory, Emit(certainty=Certainty.INSUFFICIENT_EVIDENCE), Emit("without"))
    for payload in (
        {"status": "postponed", "postponed_until": "2020-01-01T00:00:00Z"},
        {"status": "accepted", "postponed_until": "2099-01-01T00:00:00Z"},
        {"status": "rollback_triggered"},
    ):
        response = await client.post("/api/findings/B-001/status", json=payload)
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
    assert (await client.post("/api/findings/B-001/notes", json={"text": "   "})).status_code == 422
    for ident, expected in (("B-999", 404), ("B-002", 422)):
        assert (
            await client.post(f"/api/findings/{ident}/status", json={"status": "accepted"})
        ).status_code == expected
        assert (
            await client.post(f"/api/findings/{ident}/notes", json={"text": "Meten"})
        ).status_code == expected
    assert (await client.get("/api/findings/B-001")).json()["status"] == "open"


async def test_expired_postponement_reopens_without_new_data(
    client: httpx.AsyncClient, factory: sessionmaker[Session]
) -> None:
    from cvidee.store.enums import RecommendationStatus

    persist(factory, Emit(certainty=Certainty.INSUFFICIENT_EVIDENCE))
    with factory.begin() as session:
        repo = SqlFindingRepository(session)
        finding = repo.by_human_id("B-001")
        assert finding is not None
        rec = repo.recommendation_of(finding)
        assert rec is not None
        rec.status = RecommendationStatus.POSTPONED
        rec.postponed_until_ts = NOW
    body = (await client.get("/api/findings")).json()
    assert body["open_count"] == 1
    assert body["items"][0]["status"] == "open"
    with factory() as session:
        repo = SqlFindingRepository(session)
        finding = repo.by_human_id("B-001")
        assert finding is not None
        rec = repo.recommendation_of(finding)
        assert rec is not None
        assert rec.status is RecommendationStatus.OPEN
        assert rec.postponed_until_ts is None


async def test_runner_reopens_postponed_advice_on_new_severity(
    client: httpx.AsyncClient, factory: sessionmaker[Session]
) -> None:
    persist(factory, Emit(certainty=Certainty.INSUFFICIENT_EVIDENCE))
    response = await client.post(
        "/api/findings/B-001/status",
        json={"status": "postponed", "postponed_until": "2099-01-01T00:00:00Z"},
    )
    assert response.status_code == 200
    await client.post("/api/findings/B-001/notes", json={"text": "Meten na onderhoud."})
    DummyRule.emit = (Emit(severity=Severity.HIGH, certainty=Certainty.INSUFFICIENT_EVIDENCE),)
    with factory.begin() as session:
        FindingsEngine(RuleRegistry([DummyRule()]), SqlFindingRepository(session)).evaluate(
            make_ctx(NOW + HOUR_MS), run_id=None
        )
    body = (await client.get("/api/findings/B-001")).json()
    assert body["status"] == "open"
    assert body["postponed_until"] is None
    assert body["notes"][0]["text"] == "Meten na onderhoud."
    assert (await client.get("/api/findings")).json()["open_count"] == 1
