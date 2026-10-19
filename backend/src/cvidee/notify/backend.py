"""Persistent notification channels and settings-backed noise suppression."""

import time
from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from cvidee.api.schemas.common import Page
from cvidee.api.schemas.notifications import Notification as NotificationOut
from cvidee.api.schemas.notifications import NotificationPolicy as PolicyOut
from cvidee.api.schemas.notifications import NotificationPolicyIn, SeverityChannels
from cvidee.settings.repository import current_revision, effective_values, settings_hash
from cvidee.store.enums import DeliveryStatus, NotificationChannel, Severity
from cvidee.store.models import Finding, Notification, NotificationPolicy, SettingsRevision

DEFAULT_CHANNELS = {
    Severity.HIGH: NotificationChannel.DIRECT,
    Severity.MEDIUM: NotificationChannel.DAILY_DIGEST,
    Severity.LOW: NotificationChannel.WEEKLY_REPORT,
    Severity.INFO: NotificationChannel.NONE,
}


def read_policy(session: Session) -> PolicyOut:
    channels = dict(DEFAULT_CHANNELS)
    channels.update(
        {row.severity: row.channel for row in session.scalars(select(NotificationPolicy))}
    )
    revision = current_revision(session)
    raw = {} if revision is None else revision.values
    values = effective_values(revision)
    weather = ", bij vergelijkbaar weer" if values.recovery_comparable_weather_only else ""
    return PolicyOut(
        channels=SeverityChannels(**{str(key): value for key, value in channels.items()}),
        bundle_related=bool(raw.get("notification.bundle_related", True)),
        renotify_on_worsening=bool(raw.get("notification.renotify_on_worsening", True)),
        daily_report_enabled=bool(raw.get("reports.daily_enabled", False)),
        weekly_report_enabled=bool(raw.get("reports.weekly_enabled", False)),
        recovery_text=(
            f"{values.recovery_days} dagen zonder patroon{weather} "
            f"en ≥ {values.recovery_min_coverage_pct} % gegevens"
        ),
    )


class NotificationBackend:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions

    @property
    def policy(self) -> PolicyOut:
        with self.sessions() as session:
            return read_policy(session)

    def put_policy(self, body: NotificationPolicyIn) -> PolicyOut:
        now = time.time_ns() // 1_000_000
        with self.sessions.begin() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            for severity in Severity:
                row = session.get(NotificationPolicy, severity)
                channel = getattr(body.channels, severity.value)
                if row is None:
                    session.add(
                        NotificationPolicy(severity=severity, channel=channel, updated_at_ts=now)
                    )
                else:
                    row.channel, row.updated_at_ts = channel, now
            current = current_revision(session)
            raw = {} if current is None else current.values
            toggles = {
                "notification.bundle_related": body.bundle_related,
                "notification.renotify_on_worsening": body.renotify_on_worsening,
            }
            toggles.update(
                {
                    "reports.daily_enabled": body.daily_report_enabled,
                    "reports.weekly_enabled": body.weekly_report_enabled,
                }
            )
            defaults = {
                "notification.bundle_related": True,
                "notification.renotify_on_worsening": True,
                "reports.daily_enabled": False,
                "reports.weekly_enabled": False,
            }
            if any(raw.get(key, defaults[key]) != value for key, value in toggles.items()):
                values = effective_values(current)
                session.add(
                    SettingsRevision(
                        values={**raw, **values.model_dump(mode="json"), **toggles},
                        config_hash=settings_hash(values),
                        created_at_ts=now,
                        changed_by="user",
                        note="Meldingsbeleid gewijzigd",
                        onboarding_completed_at_ts=None
                        if current is None
                        else current.onboarding_completed_at_ts,
                    )
                )
            session.flush()
            return read_policy(session)

    def notifications(self, limit: int, offset: int) -> Page[NotificationOut]:
        with self.sessions() as session:
            sent = Notification.sent_at_ts.is_not(None)
            total = session.scalar(select(func.count()).select_from(Notification).where(sent)) or 0
            rows = session.scalars(
                select(Notification)
                .where(sent)
                .order_by(Notification.sent_at_ts.desc(), Notification.id.desc())
                .limit(limit)
                .offset(offset)
            )
            items = []
            for row in rows:
                finding = (
                    session.get(Finding, row.finding_id) if row.finding_id is not None else None
                )
                assert row.sent_at_ts is not None
                items.append(
                    NotificationOut(
                        id=str(row.id),
                        kind=row.kind,
                        title=row.title,
                        detail=row.body,
                        finding_id=None if finding is None else finding.human_id,
                        sent_at=datetime.fromtimestamp(row.sent_at_ts / 1000, UTC),
                        channel=row.channel,
                        status=DeliveryStatus(row.delivery_status),
                    )
                )
            return Page[NotificationOut](items=items, total=total, limit=limit, offset=offset)
