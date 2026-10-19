"""REST routers under ``/api`` (plan §3.9 plus the additions of issue #11)."""

from fastapi import APIRouter

from cvidee.api.health import router as health_router
from cvidee.api.routes import (
    changes,
    comfort,
    data,
    findings,
    ha,
    history,
    import_,
    installation,
    notifications,
    periods,
    reports,
    settings,
    signals,
    system,
    zone_analysis,
)

router = APIRouter(prefix="/api")
router.include_router(health_router)
for module in (
    system,
    comfort,
    signals,
    ha,
    installation,
    periods,
    reports,
    data,
    import_,
    findings,
    history,
    changes,
    notifications,
    settings,
    zone_analysis,
):
    router.include_router(module.router)

__all__ = ["router"]
