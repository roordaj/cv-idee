"""Notification policy and sent notifications (FR-39)."""

from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from cvidee.store.base import Base, enum_column, ts_column
from cvidee.store.enums import DeliveryStatus, NotificationChannel, NotificationKind, Severity


class NotificationPolicy(Base):
    """Channel per severity. Missing row = code default (high=direct, medium=daily, …).

    Toggles (bundle same pattern, renotify on worsening) and recovery parameters are
    settings (``settings_revisions``), so they share history and the config hash.
    """

    __tablename__ = "notification_policy"

    severity: Mapped[Severity] = enum_column(Severity, "severity", primary_key=True)
    channel: Mapped[NotificationChannel] = enum_column(NotificationChannel, "channel")
    updated_at_ts: Mapped[int] = ts_column()


class Notification(Base):
    """A notification (to be) sent via ``notify.<target>`` plus the HA event."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_finding_id_created_at_ts", "finding_id", "created_at_ts"),
        Index("ix_notifications_created_at_ts", "created_at_ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[NotificationKind] = enum_column(NotificationKind, "kind")
    channel: Mapped[NotificationChannel] = enum_column(NotificationChannel, "channel")
    # NULL for digests/reports; their finding ids are in ``payload['finding_ids']``.
    finding_id: Mapped[int | None] = mapped_column(ForeignKey("findings.id", ondelete="SET NULL"))
    severity: Mapped[Severity | None] = enum_column(Severity, "severity", nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    target: Mapped[str | None] = mapped_column(String(255))  # 'notify.mobile_app_x'
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    delivery_status: Mapped[DeliveryStatus] = enum_column(DeliveryStatus, "delivery_status")
    ha_event_fired: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at_ts: Mapped[int] = ts_column()
    sent_at_ts: Mapped[int | None] = ts_column(nullable=True)
