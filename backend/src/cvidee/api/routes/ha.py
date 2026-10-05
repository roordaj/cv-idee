"""Home Assistant endpoints: entity list and connection status (FR-01, #17).

Real implementations (not stubbed): without a configured Home Assistant the entity list
answers ``503``, an unreachable Home Assistant ``502`` (both as problem documents).
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from cvidee.api.schemas.common import problem_responses
from cvidee.api.schemas.signals import HaConnectionStatus, HaEntity
from cvidee.ingest.ha_client import HAClient, HAUnavailableError

router = APIRouter(prefix="/ha", tags=["home-assistant"])


def _client(request: Request) -> HAClient | None:
    client: HAClient | None = getattr(request.app.state, "ha_client", None)
    return client


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _time(ms: int | None) -> datetime | None:
    return None if ms is None else datetime.fromtimestamp(ms / 1000, tz=UTC)


@router.get("/entities", responses=problem_responses(502, 503))
async def list_ha_entities(request: Request) -> list[HaEntity]:
    """All Home Assistant entities, for the signal mapping picker (design additions §3b)."""
    client = _client(request)
    if client is None:
        raise HTTPException(status_code=503, detail="Home Assistant is not configured")
    try:
        states = await client.get_states()
    except HAUnavailableError as exc:
        raise HTTPException(status_code=502, detail="Home Assistant is not reachable") from exc
    return [
        HaEntity(
            id=s.entity_id,
            friendly_name=_text(s.attributes.get("friendly_name")),
            unit=_text(s.attributes.get("unit_of_measurement")),
            device_class=_text(s.attributes.get("device_class")),
            state_class=_text(s.attributes.get("state_class")),
            state=s.state,
            last_changed=_time(s.last_changed),
            last_reported=_time(s.last_reported or s.last_updated),
        )
        for s in sorted(states, key=lambda s: s.entity_id)
    ]


@router.get("/status")
async def get_ha_status(request: Request) -> HaConnectionStatus:
    """Whether Home Assistant is configured and the live connection is up."""
    client = _client(request)
    return HaConnectionStatus(
        configured=client is not None, connected=client is not None and client.connected
    )
