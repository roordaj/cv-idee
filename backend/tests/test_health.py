"""Tests for the health endpoint."""

import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from hypothesis import given
from hypothesis import strategies as st

from cvidee.main import create_app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with _client(create_app()) as ac:
        yield ac


async def test_health_returns_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_is_in_openapi_schema() -> None:
    schema = create_app().openapi()
    assert "/api/health" in schema["paths"]


_APP = create_app()
_ROUTE_NAMES = {path.split("/")[2] for path in _APP.openapi()["paths"] if path.startswith("/api/")}


@given(st.from_regex(r"\A[a-z]{1,12}\Z").filter(lambda name: name not in _ROUTE_NAMES))
def test_unknown_api_paths_return_404(name: str) -> None:
    async def get_status() -> int:
        async with _client(_APP) as ac:
            return (await ac.get(f"/api/{name}")).status_code

    assert asyncio.run(get_status()) == 404
