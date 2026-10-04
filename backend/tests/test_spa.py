"""Tests for serving the frontend build and ingress path injection."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from hypothesis import given
from hypothesis import strategies as st

from cvidee.api.spa import inject_base_path, sanitize_ingress_path
from cvidee.config import Settings
from cvidee.main import create_app

INDEX_HTML = (
    '<!doctype html><html><head><meta charset="UTF-8" />'
    '<script type="module" src="./assets/index.js"></script></head>'
    '<body><div id="root"></div></body></html>'
)


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (dist / "assets" / "index.js").write_text("console.log('hi');", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    return dist


@pytest.fixture
async def client(static_dir: Path) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(Settings(CVIDEE_STATIC_DIR=static_dir))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_root_serves_index_with_default_base(client: httpx.AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert '<base href="/" />' in response.text
    assert 'window.__INGRESS_PATH__ = "";' in response.text
    assert '<div id="root">' in response.text


async def test_ingress_header_is_injected(client: httpx.AsyncClient) -> None:
    response = await client.get("/", headers={"X-Ingress-Path": "/api/hassio_ingress/AbC123_-xyz"})
    assert '<base href="/api/hassio_ingress/AbC123_-xyz/" />' in response.text
    assert 'window.__INGRESS_PATH__ = "/api/hassio_ingress/AbC123_-xyz";' in response.text
    # Injected before the module script so relative asset URLs use the base.
    assert response.text.index("<base") < response.text.index("./assets/index.js")


async def test_deep_link_falls_back_to_index(client: httpx.AsyncClient) -> None:
    response = await client.get("/bevindingen/42", headers={"X-Ingress-Path": "/ingress/x"})
    assert response.status_code == 200
    assert 'window.__INGRESS_PATH__ = "/ingress/x";' in response.text


async def test_static_asset_is_served(client: httpx.AsyncClient) -> None:
    response = await client.get("/assets/index.js")
    assert response.status_code == 200
    assert response.text == "console.log('hi');"


async def test_path_traversal_does_not_escape_static_dir(client: httpx.AsyncClient) -> None:
    response = await client.get("/..%2Fsecret.txt")
    assert "secret" not in response.text


async def test_unknown_api_path_is_404_not_index(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/does-not-exist")).status_code == 404
    assert (await client.get("/api")).status_code == 404
    assert (await client.get("/api/health")).json() == {"status": "ok"}


@pytest.mark.parametrize(
    "header",
    ['/x"><script>alert(1)</script>', "javascript:alert(1)", "//evil.example", "/a b"],
)
def test_unsafe_ingress_values_are_ignored(header: str) -> None:
    assert sanitize_ingress_path(header) == ""


@given(st.lists(st.from_regex(r"\A[A-Za-z0-9._~-]{1,20}\Z"), min_size=1, max_size=4))
def test_safe_ingress_paths_are_kept(segments: list[str]) -> None:
    path = "/" + "/".join(segments)
    assert sanitize_ingress_path(path + "/") == path


def test_inject_without_head_tag_prepends() -> None:
    assert inject_base_path("<p>x</p>", "").startswith('<base href="/" />')


def test_no_static_dir_means_no_frontend_routes() -> None:
    app = create_app(Settings())
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/{path:path}" not in paths
