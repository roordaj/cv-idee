"""Notification policy, sent notifications and the HA export (FR-38, FR-39)."""

from fastapi import APIRouter

from cvidee.api.routes.deps import Limit, Offset, Store
from cvidee.api.schemas.common import Page, problem_responses
from cvidee.api.schemas.notifications import (
    HaExport,
    Notification,
    NotificationPolicy,
    NotificationPolicyIn,
)

router = APIRouter(tags=["notifications"], responses=problem_responses(501))


@router.get("/notifications/policy")
async def get_notification_policy(store: Store) -> NotificationPolicy:
    """Channel per severity and noise suppression."""
    return store.policy


@router.put("/notifications/policy", responses=problem_responses(422))
async def update_notification_policy(
    body: NotificationPolicyIn, store: Store
) -> NotificationPolicy:
    """Change channels and noise suppression."""
    return store.put_policy(body)


@router.get("/notifications", responses=problem_responses(422))
async def list_notifications(
    store: Store, limit: Limit = 50, offset: Offset = 0
) -> Page[Notification]:
    """Recently sent notifications, newest first."""
    return store.notifications(limit, offset)


@router.get("/ha/export")
async def get_ha_export(store: Store) -> HaExport:
    """Current values of the entities exported to Home Assistant."""
    return store.ha_export()
