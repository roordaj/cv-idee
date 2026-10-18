"""Notification policy, sent notifications and the HA export (FR-38, FR-39)."""

from typing import TYPE_CHECKING

from fastapi import APIRouter, Request

from cvidee.api.routes.deps import Limit, Notifications, Offset
from cvidee.api.schemas.common import Page, problem_responses
from cvidee.api.schemas.notifications import (
    HaExport,
    Notification,
    NotificationPolicy,
    NotificationPolicyIn,
)

if TYPE_CHECKING:
    from cvidee.api.stubs.store import StubStore
    from cvidee.ha_export.service import ExportService

router = APIRouter(tags=["notifications"], responses=problem_responses(501))


@router.get("/notifications/policy")
async def get_notification_policy(store: Notifications) -> NotificationPolicy:
    """Channel per severity and noise suppression."""
    return store.policy


@router.put("/notifications/policy", responses=problem_responses(422))
async def update_notification_policy(
    body: NotificationPolicyIn, store: Notifications
) -> NotificationPolicy:
    """Change channels and noise suppression."""
    return store.put_policy(body)


@router.get("/notifications", responses=problem_responses(422))
async def list_notifications(
    store: Notifications, limit: Limit = 50, offset: Offset = 0
) -> Page[Notification]:
    """Recently sent notifications, newest first."""
    return store.notifications(limit, offset)


@router.get("/ha/export")
async def get_ha_export(request: Request) -> HaExport:
    """Current values of the entities exported to Home Assistant."""
    stub: StubStore | None = getattr(request.app.state, "stub_store", None)
    if stub is not None:
        return stub.ha_export()
    service: ExportService | None = getattr(request.app.state, "ha_export", None)
    if service is None:
        return HaExport(transport="none", connected=False, updated_at=None, entities=[])
    return service.snapshot()
