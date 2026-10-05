"""Notification policy, sent notifications and the Home Assistant export (FR-38, FR-39)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from cvidee.api.schemas.common import ApiModel, UtcDateTime
from cvidee.store.enums import DeliveryStatus, NotificationChannel, NotificationKind


class SeverityChannels(ApiModel):
    high: NotificationChannel
    medium: NotificationChannel
    low: NotificationChannel
    info: NotificationChannel


class NotificationPolicyIn(ApiModel):
    channels: SeverityChannels
    bundle_related: bool = Field(description="Bundel meldingen die bij hetzelfde patroon horen.")
    renotify_on_worsening: bool = Field(description="Opnieuw melden als het erger wordt.")


class NotificationPolicy(NotificationPolicyIn):
    recovery_text: str = Field(
        description="Recovery criterion summary (from the settings, read-only here)."
    )


class Notification(ApiModel):
    id: str
    kind: NotificationKind
    title: str
    detail: str
    finding_id: str | None
    sent_at: UtcDateTime
    channel: NotificationChannel
    status: DeliveryStatus


class HaExportEntity(ApiModel):
    entity_id: str = Field(examples=["sensor.cv_analyse_starts_per_uur"])
    state: str = Field(description="Raw state as Home Assistant receives it.")
    display: str = Field(description="Dutch formatted value for the UI.")
    unit: str | None = None


class HaExport(ApiModel):
    transport: Literal["mqtt", "fallback", "none"]
    connected: bool
    updated_at: UtcDateTime | None
    entities: list[HaExportEntity]
