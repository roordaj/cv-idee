"""Behaviour of the stub backend (design-v3 data and in-memory state)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from cvidee.api.stubs.sim import build_sim, fmt_duration, nl
from cvidee.config import Settings
from cvidee.main import create_app


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(Settings.model_validate({"CVIDEE_STUB_DATA": "1"}))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


def test_sim_matches_design_v3_numbers() -> None:
    """Values the v3 prototype shows (computed by its buildSim in the browser)."""
    sim = build_sim()
    st = sim.stats
    assert len(sim.cycles) == 25
    assert (st.ch_cycles, st.dhw_cycles, st.short_cycles, st.ch_cycles_before_gap) == (
        24,
        1,
        14,
        22,
    )
    assert nl(st.starts_per_hour) == "4,4"
    assert fmt_duration(st.median_burn_min) == "2:30"
    assert fmt_duration(st.mean_burn_min) == "4:34"
    assert fmt_duration(st.median_pause_min) == "6:30"
    assert st.total_burn_min == 110
    assert sum(1 for p in sim.points if p is None) == 60


async def test_finding_texts_use_sim_numbers(client: httpx.AsyncClient) -> None:
    finding = (await client.get("/api/findings/B-014")).json()
    assert finding["observation"].startswith("In 14 van 22 cv-cycli stopt de brander")
    assert finding["evidence"]["display"]["cycles"] == "14 van 22 cv-cycli"
    assert finding["bundle"][2]["text"] == "Mediaan pauze 6:30 tijdens vraag"
    assert finding["period"] == {"start": "2026-10-04T04:00:00Z", "end": "2026-10-04T08:10:00Z"}


async def test_consumption_stub_reports_missing_gas_meter(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/consumption")
    assert response.status_code == 200
    assert response.json()["availability"] == "unavailable"
    assert response.json()["reasons"] == ["no_meter"]
    assert response.json()["meter_scope"] == "unknown"
    assert response.json()["consumption_m3"] is None


async def test_postpone_finding_updates_status_and_counts(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/status")).json()["counts"]["open_findings"] == 5
    response = await client.post("/api/findings/B-014/status", json={"status": "postponed"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "postponed"
    assert body["status_text"] == "Uitgesteld tot 11 okt"
    assert body["postponed_until"] == "2026-10-11T10:00:00Z"
    assert (await client.get("/api/findings")).json()["open_count"] == 4


async def test_app_managed_status_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/findings/B-014/status", json={"status": "rollback_triggered"}
    )
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["errors"][0]["loc"] == ["body", "status"]


async def test_period_lifecycle(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/api/periods",
        json={
            "kind": "vacation",
            "start": "2026-10-10T00:00:00+02:00",
            "end": "2026-10-17T00:00:00+02:00",
            "description": "Herfstvakantie",
        },
    )
    assert created.status_code == 201
    period = created.json()
    assert period["start"] == "2026-10-09T22:00:00Z"
    assert period["excluded_from"] == {
        "normal_behaviour": True,
        "comparisons": True,
        "ch_conclusions": True,
    }
    bad = await client.put(
        f"/api/periods/{period['id']}",
        json={"kind": "vacation", "start": "2026-10-17T00:00:00Z", "end": "2026-10-10T00:00:00Z"},
    )
    assert bad.status_code == 422
    assert bad.json()["detail"] == "De eindtijd moet na de begintijd liggen."
    assert (await client.delete(f"/api/periods/{period['id']}")).status_code == 204
    assert (await client.delete(f"/api/periods/{period['id']}")).status_code == 404


async def test_settings_revision_conflict_and_cross_validation(
    client: httpx.AsyncClient,
) -> None:
    current = (await client.get("/api/settings")).json()
    stale = await client.put(
        "/api/settings", json={"revision": "outdated", "values": current["values"]}
    )
    assert stale.status_code == 409
    invalid = current["values"] | {"repetition_days": 9, "repetition_window_days": 7}
    response = await client.put(
        "/api/settings", json={"revision": current["revision"], "values": invalid}
    )
    assert response.status_code == 422
    changed = current["values"] | {"short_cycle_min": 4.0}
    saved = await client.put(
        "/api/settings", json={"revision": current["revision"], "values": changed}
    )
    assert saved.status_code == 200
    assert saved.json()["recompute_started"] is True
    assert saved.json()["revision"] != current["revision"]


async def test_import_progresses_per_poll_and_allows_one_at_a_time(
    client: httpx.AsyncClient,
) -> None:
    started = await client.post(
        "/api/import", json={"from": "2026-10-01T22:00:00Z", "to": "2026-10-04T10:00:00Z"}
    )
    assert started.status_code == 202
    job = started.json()
    assert job["status"] == "pending"
    assert job["blocks_total"] == 3
    again = await client.post(
        "/api/import", json={"from": "2026-10-02T00:00:00Z", "to": "2026-10-03T00:00:00Z"}
    )
    assert again.status_code == 409
    assert (await client.get("/api/status")).json()["live"]["state"] == "importing"
    statuses = [(await client.get(f"/api/import/{job['id']}")).json()["status"] for _ in range(5)]
    assert statuses == ["fetching", "fetching", "analysing", "done", "done"]
    assert (await client.get("/api/status")).json()["live"]["state"] == "live"


async def test_unlinking_a_signal_updates_counts(client: httpx.AsyncClient) -> None:
    response = await client.put(
        "/api/signals/room_temperature@room:slaapkamer", json={"entity_id": None}
    )
    assert response.status_code == 200
    assert response.json()["state"] == "missing"
    signals = (await client.get("/api/signals")).json()
    assert (signals["linked"], signals["total"]) == (8, 15)
    unknown = await client.put("/api/signals/nope@boiler", json={"entity_id": None})
    assert unknown.status_code == 404


async def test_new_change_shows_in_timeline_only_when_in_range(
    client: httpx.AsyncClient,
) -> None:
    created = await client.post(
        "/api/changes",
        json={
            "at": "2026-10-04T06:00:00Z",
            "actor": "installer",
            "parameter": "Pompstand",
            "old_value": "stand 2",
            "new_value": "stand 3",
        },
    )
    assert created.status_code == 201
    assert created.json()["id"] == "W-09"
    timeline = (await client.get("/api/timeline")).json()
    assert [c["id"] for c in timeline["changes"]] == ["W-09"]
    assert timeline["last_change_before"]["id"] == "W-07"
    evaluation = (await client.get("/api/changes/W-09/evaluation")).json()
    assert evaluation["verdict"] == "pending"
