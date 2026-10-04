"""Application entry point: FastAPI app factory.

Run with ``uvicorn cvidee.main:create_app --factory --port 8099``.
"""

from fastapi import FastAPI

from cvidee import __version__
from cvidee.api import router as api_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="CV-idee", version=__version__)
    app.include_router(api_router)
    return app
