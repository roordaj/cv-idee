"""HTTP API (FastAPI routers, OpenAPI contract).

Exposes the REST endpoints under ``/api`` used by the frontend and, later, serves the
frontend build. The OpenAPI schema is the contract between backend and frontend.
"""

from cvidee.api.health import router

__all__ = ["router"]
