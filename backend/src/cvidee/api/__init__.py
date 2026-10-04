"""HTTP API (FastAPI routers, OpenAPI contract).

Exposes the REST endpoints under ``/api`` used by the frontend and, later, serves the
frontend build. The OpenAPI schema is the contract between backend and frontend.
"""

from fastapi import APIRouter

from cvidee.api.health import router as health_router
from cvidee.api.routes.ha import router as ha_router

router = APIRouter()
router.include_router(health_router)
router.include_router(ha_router)

__all__ = ["router"]
