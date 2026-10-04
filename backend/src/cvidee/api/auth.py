"""Optional bearer-token check for the REST API in standalone mode."""

from __future__ import annotations

import secrets

from pydantic import SecretStr
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

# Reachable without token so container health checks keep working.
PUBLIC_API_PATHS = frozenset({"/api/health"})


class ApiTokenMiddleware(BaseHTTPMiddleware):
    """Require ``Authorization: Bearer <token>`` on ``/api/*`` (except public paths)."""

    def __init__(self, app: ASGIApp, token: SecretStr) -> None:
        super().__init__(app)
        self._expected = f"Bearer {token.get_secret_value()}".encode()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        is_api = path == "/api" or path.startswith("/api/")
        if is_api and path not in PUBLIC_API_PATHS:
            provided = request.headers.get("Authorization", "").encode()
            if not secrets.compare_digest(provided, self._expected):
                return JSONResponse(
                    {"detail": "Not authenticated"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
        return await call_next(request)
