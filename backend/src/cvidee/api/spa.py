"""Serve the frontend build (single-page app) with Home Assistant ingress support.

Under ingress, Home Assistant proxies the add-on at ``/api/hassio_ingress/<token>/`` and
passes that prefix in the ``X-Ingress-Path`` header (the prefix itself is stripped from the
request path). The prefix is injected into ``index.html`` as ``<base href>`` (so relative
asset URLs also resolve on deep links) and as ``window.__INGRESS_PATH__`` (router basename
and API base for the frontend).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

INGRESS_HEADER = "X-Ingress-Path"

# Only plain path segments; anything else is ignored to rule out markup injection.
_SAFE_PREFIX = re.compile(r"^(/[A-Za-z0-9._~-]+)+$")
_HEAD_TAG = re.compile(r"<head[^>]*>", re.IGNORECASE)


def sanitize_ingress_path(value: str | None) -> str:
    """Return the ingress prefix without trailing slash, or ``""`` if absent or unsafe."""
    if not value:
        return ""
    prefix = value.rstrip("/")
    return prefix if _SAFE_PREFIX.fullmatch(prefix) else ""


def inject_base_path(index_html: str, base_path: str) -> str:
    """Insert ``<base href>`` and ``window.__INGRESS_PATH__`` right after ``<head>``."""
    snippet = (
        f'<base href="{base_path}/" />'
        f"<script>window.__INGRESS_PATH__ = {json.dumps(base_path)};</script>"
    )
    match = _HEAD_TAG.search(index_html)
    if match is None:
        return snippet + index_html
    return index_html[: match.end()] + snippet + index_html[match.end() :]


def create_spa_router(static_dir: Path) -> APIRouter:
    """Create a catch-all router serving files from ``static_dir`` with SPA fallback.

    Paths under ``/api`` are never answered with ``index.html``; they 404 instead.
    """
    root = static_dir.resolve()
    index_html = (root / "index.html").read_text(encoding="utf-8")
    router = APIRouter(include_in_schema=False)

    @router.get("/{path:path}")
    async def serve(path: str, request: Request) -> Response:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404)
        if path:
            candidate = (root / path).resolve()
            if candidate.is_relative_to(root) and candidate.is_file():
                return FileResponse(candidate)
        base_path = sanitize_ingress_path(request.headers.get(INGRESS_HEADER))
        return HTMLResponse(
            inject_base_path(index_html, base_path),
            headers={"Cache-Control": "no-cache"},
        )

    return router
