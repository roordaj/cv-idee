"""HTTP API (FastAPI routers, OpenAPI contract).

Exposes the REST endpoints under ``/api`` used by the frontend and, later, serves the
frontend build. The OpenAPI schema is the contract between backend and frontend
(``api/openapi.json``, issue #11).
"""

from cvidee.api.routes import router

__all__ = ["router"]
