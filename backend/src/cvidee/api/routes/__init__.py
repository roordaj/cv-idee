"""REST routers under ``/api`` (plan §3.9 plus the additions of issue #11)."""

from fastapi import APIRouter

from cvidee.api.health import router as health_router
from cvidee.api.routes import (
    changes,
    data,
    findings,
    ha,
    history,
    import_,
    installation,
    notifications,
    periods,
    settings,
    signals,
    system,
)

router = APIRouter(prefix="/api")
router.include_router(health_router)
for module in (
    system,
    signals,
    ha,
    installation,
    periods,
    data,
    import_,
    findings,
    history,
    changes,
    notifications,
    settings,
):
    router.include_router(module.router)

__all__ = ["router"]
