"""Application entry point: FastAPI app factory.

Run with ``uvicorn cvidee.main:create_app --factory --port 8099``.
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.routing import APIRoute

from cvidee import __version__
from cvidee.analysis.types import Role
from cvidee.api import router as api_router
from cvidee.api.auth import ApiTokenMiddleware
from cvidee.api.live_read import LiveReadModel
from cvidee.api.problems import install_problem_handlers
from cvidee.api.report_read import ReportsReadModel
from cvidee.api.spa import create_spa_router
from cvidee.api.stubs.store import StubStore
from cvidee.config import Settings, get_settings
from cvidee.ha_export.service import ExportService
from cvidee.ingest.ha_client import AiohttpHAClient
from cvidee.ingest.history_import import HistoryImport
from cvidee.ingest.service import FileAliveStore, IngestService, sql_tracked_entities
from cvidee.notify.service import NotificationService
from cvidee.runner.service import AnalysisRunner, RunnerSettings
from cvidee.runner.sources import SourceSettings
from cvidee.signals.catalog import sync_catalogue
from cvidee.store.engine import create_db_engine, create_session_factory, database_url
from cvidee.store.schema import upgrade_to_head

logger = logging.getLogger(__name__)


def _operation_id(route: APIRoute) -> str:
    """Use the endpoint function name as OpenAPI operationId (stable client names)."""
    return route.name


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


def _start_ingest(app: FastAPI, settings: Settings) -> IngestService | None:
    """Build the HA client and ingest service; ``None`` (no-op) when HA is not configured."""
    app.state.ha_client = None
    app.state.ingest = None
    if not settings.ha_configured:
        logger.info("Home Assistant is not configured; ingest disabled")
        return None
    factory = create_session_factory(create_db_engine(database_url(settings.db_path)))
    holder: list[IngestService] = []
    client = AiohttpHAClient(
        settings.ha_connection(),
        tracked=lambda: holder[0].tracked_ids() if holder else (),
    )
    service = IngestService(
        client,
        factory,
        lambda: sql_tracked_entities(
            factory,
            gateway_entity_id=settings.can_gateway_entity_id,
            gateway_roles=[
                role.strip() for role in settings.can_gateway_roles.split(",") if role.strip()
            ],
        ),
        alive_store=FileAliveStore(settings.db_path.parent / "ingest_alive_at"),
    )
    holder.append(service)
    app.state.ha_client = client
    app.state.ingest = service
    return service


def _start_runner(
    app: FastAPI, settings: Settings
) -> tuple[AnalysisRunner, asyncio.Event, asyncio.Task[None]] | None:
    """Start the analysis runner loop; ``None`` when disabled. A tick without signal
    mappings is a no-op, so an unconfigured installation does nothing."""
    app.state.runner = None
    if not settings.analysis_enabled:
        logger.info("Analysis runner disabled")
        return None
    factory = create_session_factory(create_db_engine(database_url(settings.db_path)))
    runner = AnalysisRunner(
        factory,
        RunnerSettings(
            interval_s=settings.analysis_interval_s,
            sources=SourceSettings(
                can_gateway_entity_id=settings.can_gateway_entity_id,
                can_gateway_roles=frozenset(
                    Role(role.strip())
                    for role in settings.can_gateway_roles.split(",")
                    if role.strip()
                ),
            ),
        ),
    )
    stop = asyncio.Event()
    app.state.runner = runner
    return runner, stop, asyncio.create_task(runner.run_forever(stop), name="analysis-runner")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Migrate before anything (ingest, runner) touches the database.
    settings: Settings = app.state.settings
    migrate_database(settings)
    app.state.session_factory = create_session_factory(
        create_db_engine(database_url(settings.db_path))
    )
    with app.state.session_factory.begin() as session:
        sync_catalogue(session)
    ingest = _start_ingest(app, settings)
    if ingest is not None:
        await ingest.start()
    started = _start_runner(app, settings)
    imports = HistoryImport(
        app.state.session_factory,
        app.state.ha_client,
        app.state.runner or AnalysisRunner(app.state.session_factory),
    )
    app.state.history_import = imports
    await imports.recover()
    export = ExportService(settings, app.state.session_factory)
    app.state.ha_export = export
    report_monitoring = LiveReadModel(
        app.state.session_factory, settings, app.state.ha_client, export
    )
    reports = ReportsReadModel(app.state.session_factory, report_monitoring)
    notifications = NotificationService(
        app.state.session_factory,
        app.state.ha_client,
        settings.notify_target,
        report_builder=reports.report,
    )
    app.state.notifications = notifications
    if not settings.stub_data:
        await export.start()
        await notifications.start()
    try:
        yield
    finally:
        await notifications.stop()
        await export.stop()
        await imports.stop()
        if started is not None:
            _, stop, task = started
            stop.set()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if ingest is not None:
            await ingest.stop()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = settings if settings is not None else get_settings()
    app = FastAPI(
        title="CV-idee",
        version=__version__,
        description="Read-only analysis and advice API for a central-heating installation. "
        "Contract of issue #11; errors are RFC 7807 problem documents.",
        lifespan=_lifespan,
        generate_unique_id_function=_operation_id,
    )
    app.state.settings = settings
    app.state.stub_store = StubStore() if settings.stub_data else None
    app.state.session_factory = None  # set by the lifespan once the database is migrated
    install_problem_handlers(app)
    if settings.api_auth_enabled and settings.api_token is not None:
        app.add_middleware(ApiTokenMiddleware, token=settings.api_token)
    app.include_router(api_router)
    # Must come last: catch-all route serving the frontend build (SPA fallback).
    if settings.static_dir is not None and (settings.static_dir / "index.html").is_file():
        app.include_router(create_spa_router(settings.static_dir))
    return app
