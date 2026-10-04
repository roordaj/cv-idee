"""Application entry point: FastAPI app factory.

Run with ``uvicorn cvidee.main:create_app --factory --port 8099``.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from cvidee import __version__
from cvidee.api import router as api_router
from cvidee.api.auth import ApiTokenMiddleware
from cvidee.api.spa import create_spa_router
from cvidee.config import Settings, get_settings
from cvidee.store.engine import database_url
from cvidee.store.schema import upgrade_to_head

logger = logging.getLogger(__name__)


def migrate_database(settings: Settings) -> None:
    """Create the database directory and bring the schema to ``head`` (ADR-001 §9).

    Raises on failure so the application does not start half-migrated.
    """
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    url = database_url(settings.db_path)
    logger.info("Migrating database to head (%s)", url)
    try:
        upgrade_to_head(url)
    except Exception:
        logger.exception("Database migration failed; refusing to start")
        raise
    logger.info("Database is at head")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Migrate before anything (ingest, runner) touches the database.
    migrate_database(app.state.settings)
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = settings if settings is not None else get_settings()
    app = FastAPI(title="CV-idee", version=__version__, lifespan=_lifespan)
    app.state.settings = settings
    if settings.api_auth_enabled and settings.api_token is not None:
        app.add_middleware(ApiTokenMiddleware, token=settings.api_token)
    app.include_router(api_router)
    # Must come last: catch-all route serving the frontend build (SPA fallback).
    if settings.static_dir is not None and (settings.static_dir / "index.html").is_file():
        app.include_router(create_spa_router(settings.static_dir))
    return app
