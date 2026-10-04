"""Application entry point: FastAPI app factory.

Run with ``uvicorn cvidee.main:create_app --factory --port 8099``.
"""

from fastapi import FastAPI

from cvidee import __version__
from cvidee.api import router as api_router
from cvidee.api.auth import ApiTokenMiddleware
from cvidee.api.spa import create_spa_router
from cvidee.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = settings if settings is not None else get_settings()
    app = FastAPI(title="CV-idee", version=__version__)
    app.state.settings = settings
    if settings.api_auth_enabled and settings.api_token is not None:
        app.add_middleware(ApiTokenMiddleware, token=settings.api_token)
    app.include_router(api_router)
    # Must come last: catch-all route serving the frontend build (SPA fallback).
    if settings.static_dir is not None and (settings.static_dir / "index.html").is_file():
        app.include_router(create_spa_router(settings.static_dir))
    return app
