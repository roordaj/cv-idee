"""Contract tests: every stub response validates against its schema; no flag means 501."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from pydantic import TypeAdapter

from cvidee.api import health
from cvidee.api.openapi import render
from cvidee.api.routes import (
    changes,
    data,
    findings,
    ha,
    installation,
    notifications,
    periods,
    settings,
    signals,
    system,
)
from cvidee.config import Settings
from cvidee.main import create_app

PATH_IDS = {
    "signal_id": "flame@boiler",
    "period_id": "P-001",
    "import_id": "I-001",
    "finding_id": "B-014",
    "change_id": "W-07",
}
NOW = "2026-10-04T10:00:00Z"
BODIES: dict[tuple[str, str], dict[str, Any]] = {
    ("PUT", "/api/signals/{signal_id}"): {"entity_id": "binary_sensor.remeha_flame"},
    ("POST", "/api/periods"): {"kind": "test", "start": "2026-10-03T08:00:00Z"},
    ("PUT", "/api/periods/{period_id}"): {"kind": "vacation", "start": "2026-08-14T00:00:00Z"},
    ("POST", "/api/import"): {"from": "2026-10-01T00:00:00Z", "to": NOW},
    ("POST", "/api/findings/{finding_id}/status"): {"status": "accepted"},
    ("POST", "/api/findings/{finding_id}/notes"): {"text": "Groepen boven gecontroleerd."},
    ("POST", "/api/changes"): {
        "at": NOW,
        "actor": "user",
        "parameter": "Maximale CV-aanvoer",
        "old_value": "60 °C",
        "new_value": "70 °C",
        "finding_id": "B-011",
    },
    ("PUT", "/api/notifications/policy"): {
        "channels": {"high": "direct", "medium": "direct", "low": "none", "info": "none"},
        "bundle_related": False,
        "renotify_on_worsening": True,
    },
}


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def stub_app() -> FastAPI:
    return create_app(Settings.model_validate({"CVIDEE_STUB_DATA": "1"}))


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with _client(stub_app()) as ac:
        yield ac


def _operations() -> Iterator[tuple[str, APIRoute]]:
    """Every API operation, with its full path (routers are mounted under ``/api``)."""
    modules = (health, changes, data, findings, ha, installation, notifications, periods, settings)
    for module in (*modules, signals, system):
        for route in module.router.routes:
            assert isinstance(route, APIRoute)
            full = APIRoute(
                "/api" + route.path,
                route.endpoint,
                response_model=route.response_model,
                status_code=route.status_code,
                methods=route.methods,
            )
            for method in sorted(route.methods or ()):
                yield method, full


OPERATIONS = list(_operations())
STUBBED = [
    (m, r) for m, r in OPERATIONS if r.path != "/api/health" and not r.path.startswith("/api/ha/")
]
"""Operations served by the stub store (HA routes are real, see ``routes/ha.py``)."""


def _url(route: APIRoute) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: PATH_IDS[m.group(1)], route.path)


async def _body_for(client: httpx.AsyncClient, method: str, path: str) -> dict[str, Any] | None:
    if (method, path) in BODIES:
        return BODIES[method, path]
    if path == "/api/installation":
        profile = (await client.get(path)).json()
        return {k: v for k, v in profile.items() if k not in ("summary", "updated_at")}
    if path == "/api/settings":
        current = (await client.get(path)).json()
        return {"revision": current["revision"], "values": current["values"]}
    return None


@pytest.mark.parametrize(("method", "route"), STUBBED, ids=[f"{m} {r.path}" for m, r in STUBBED])
async def test_stub_response_matches_schema(
    client: httpx.AsyncClient, method: str, route: APIRoute
) -> None:
    body = await _body_for(client, method, route.path)
    url = _url(route)
    if route.path == "/api/import/{import_id}/cancel":  # needs a running import
        started = await client.post("/api/import", json=BODIES["POST", "/api/import"])
        url = route.path.replace("{import_id}", started.json()["id"])
    response = await client.request(method, url, json=body)
    assert response.status_code == route.status_code or (
        route.status_code is None and response.status_code == 200
    ), response.text
    if route.response_model is None:
        assert response.content == b""
        return
    model = TypeAdapter(route.response_model)
    model.validate_python(response.json())
    for match in re.finditer(r'"\w*(?:_at|start|end|now)":"([^"]+)"', response.text):
        assert match.group(1).endswith("Z"), f"timestamp not in UTC: {match.group(0)}"


@pytest.mark.parametrize(
    ("method", "route"),
    STUBBED,
    ids=[f"{m} {r.path}" for m, r in STUBBED],
)
async def test_without_stub_flag_routes_answer_501_problem(method: str, route: APIRoute) -> None:
    async with _client(create_app(Settings.model_validate({}))) as ac:
        body = BODIES.get((method, route.path))
        response = await ac.request(method, _url(route), json=body)
    if response.status_code == 422:  # body validation runs before the dependency
        return
    assert response.status_code == 501
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["status"] == 501


def test_committed_openapi_matches_generated() -> None:
    committed = Path(__file__).parents[3] / "api" / "openapi.json"
    assert committed.read_text(encoding="utf-8") == render(), "run `make openapi`"


def test_settings_schema_carries_x_extensions() -> None:
    schema = stub_app().openapi()["components"]["schemas"]["AnalysisSettings"]
    field = schema["properties"]["short_cycle_min"]
    assert field["x-unit"] == "min"
    assert field["x-step"] == 0.5
    assert field["x-group"] == "short_cycles"
    assert field["x-rule"] == ["kort-branden"]


async def test_ha_routes_are_real_without_ha(client: httpx.AsyncClient) -> None:
    """``/api/ha/*`` is not stubbed: without Home Assistant the entity list is 503."""
    entities = await client.get("/api/ha/entities")
    assert entities.status_code == 503
    assert entities.headers["content-type"] == "application/problem+json"
    status = await client.get("/api/ha/status")
    assert status.json() == {
        "configured": False,
        "connected": False,
        "clock_offset_ms": 0,
    }
