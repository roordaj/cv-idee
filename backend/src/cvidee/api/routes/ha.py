"""Home Assistant endpoints: entity list and connection status (FR-01, #17)."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from cvidee.ingest.ha_client import HAClient, HAUnavailableError

router = APIRouter(prefix="/api/ha", tags=["home-assistant"])


class HAEntity(BaseModel):
    id: str
    friendly_name: str | None = None
    unit: str | None = None
    device_class: str | None = None


class HAStatus(BaseModel):
    configured: bool
    connected: bool


def _client(request: Request) -> HAClient | None:
    client: HAClient | None = getattr(request.app.state, "ha_client", None)
    return client


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


@router.get("/entities")
async def list_entities(request: Request) -> list[HAEntity]:
    """All Home Assistant entities, for the signal mapping picker."""
    client = _client(request)
    if client is None:
        raise HTTPException(status_code=503, detail="Home Assistant is not configured")
    try:
        states = await client.get_states()
    except HAUnavailableError as exc:
        raise HTTPException(status_code=502, detail="Home Assistant is not reachable") from exc
    return [
        HAEntity(
            id=s.entity_id,
            friendly_name=_text(s.attributes.get("friendly_name")),
            unit=_text(s.attributes.get("unit_of_measurement")),
            device_class=_text(s.attributes.get("device_class")),
        )
        for s in sorted(states, key=lambda s: s.entity_id)
    ]


@router.get("/status")
async def status(request: Request) -> HAStatus:
    """Whether Home Assistant is configured and the live connection is up."""
    client = _client(request)
    return HAStatus(
        configured=client is not None, connected=client is not None and client.connected
    )
