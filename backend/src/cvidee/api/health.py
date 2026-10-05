"""Health endpoint."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    """Liveness information."""

    status: Literal["ok"]


@router.get("/health", tags=["system"])
async def health() -> HealthResponse:
    """Report that the service is running."""
    return HealthResponse(status="ok")
