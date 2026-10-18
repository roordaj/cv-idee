"""Durable notification outbox, observed transitions and Amsterdam digest scheduling."""

import asyncio
import contextlib
import logging
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from datetime import time as clock_time
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from cvidee.ingest.ha_client import HAClient, HAError
from cvidee.notify.backend import read_policy
from cvidee.store.enums import (
    DeliveryStatus,
    FindingLifecycle,
    NotificationChannel,
    NotificationKind,
    ResolutionReason,
    Severity,
)
from cvidee.store.models import Finding, Notification, NotificationState

logger = logging.getLogger(__name__)
RANK = {Severity.INFO: 0, Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3}
AMSTERDAM = ZoneInfo("Europe/Amsterdam")


def digest_cutoff(now: int, channel: NotificationChannel) -> int:
    """Latest daily/weekly boundary: 08:00 local time, Monday for weekly reports."""
    local = datetime.fromtimestamp(now / 1000, UTC).astimezone(AMSTERDAM)
    day = local.date()
    if local.time() < clock_time(8):
        day -= timedelta(days=1)
    if channel is NotificationChannel.WEEKLY_REPORT:
        day -= timedelta(days=day.weekday())
    return round(datetime.combine(day, clock_time(8), AMSTERDAM).timestamp() * 1000)


def _event(
    session: Session,
    finding: Finding,
    kind: NotificationKind,
    channel: NotificationChannel,
    now: int,
    *,
    suppressed: bool = False,
) -> None:
    labels = {
        NotificationKind.FINDING_NEW: "Nieuwe bevinding",
        NotificationKind.FINDING_WORSENED: "Bevinding verslechterd",
        NotificationKind.FINDING_RESOLVED: "Bevinding hersteld",
    }
    at = datetime.fromtimestamp(now / 1000, UTC).astimezone(AMSTERDAM).strftime("%d-%m-%Y %H:%M")
    session.add(
        Notification(
            kind=kind,
            channel=channel,
            finding_id=finding.id,
            severity=finding.severity,
            title=f"{labels[kind]}: {finding.title}"[:255],
            body=f"{labels[kind]} · {finding.human_id} · {at} · {finding.observation}",
            payload={
                "finding_ids": [finding.human_id],
                "kind": kind.value,
                "severity": finding.severity.value,
                "certainty": finding.certainty.value,
                "observed_at_ts": now,
                "period_start_ts": finding.period_start_ts,
                "period_end_ts": finding.period_end_ts,
            },
            delivery_status=DeliveryStatus.SUPPRESSED if suppressed else DeliveryStatus.PENDING,
            ha_event_fired=False,
            created_at_ts=now,
        )
    )


def plan_notifications(session: Session, now: int) -> None:
    """Observe each finding once; gaps never count as recovery (engine owns that proof)."""
    policy = read_policy(session)
    for finding in session.scalars(select(Finding).order_by(Finding.id)):
        state = session.get(NotificationState, finding.id)
        channel = getattr(policy.channels, finding.severity.value)
        if state is None:
            if finding.lifecycle is FindingLifecycle.ACTIVE:
                _event(session, finding, NotificationKind.FINDING_NEW, channel, now)
            state = NotificationState(
                finding_id=finding.id,
                severity=finding.severity,
                lifecycle=finding.lifecycle,
                updated_at_ts=now,
            )
            session.add(state)
        elif finding.lifecycle is FindingLifecycle.ACTIVE:
            if state.lifecycle is FindingLifecycle.RESOLVED:
                _event(session, finding, NotificationKind.FINDING_NEW, channel, now)
            elif RANK[finding.severity] > RANK[state.severity]:
                _event(
                    session,
                    finding,
                    NotificationKind.FINDING_WORSENED,
                    channel,
                    now,
                    suppressed=not policy.renotify_on_worsening,
                )
        elif (
            state.lifecycle is FindingLifecycle.ACTIVE
            and finding.resolution_reason is ResolutionReason.RECOVERED
        ):
            _event(session, finding, NotificationKind.FINDING_RESOLVED, channel, now)
        state.severity, state.lifecycle, state.updated_at_ts = (
            finding.severity,
            finding.lifecycle,
            now,
        )
    session.flush()
    # A policy change also applies to events not yet handed to either HA transport.
    waiting = session.scalars(
        select(Notification).where(
            Notification.finding_id.is_not(None),
            Notification.delivery_status.in_((DeliveryStatus.PENDING, DeliveryStatus.FAILED)),
        )
    )
    for queued in waiting:
        if queued.ha_event_fired or queued.payload.get("notify_sent"):
            continue
        if queued.kind is NotificationKind.FINDING_WORSENED and not policy.renotify_on_worsening:
            queued.delivery_status = DeliveryStatus.SUPPRESSED
        elif queued.severity is not None:
            channel = getattr(policy.channels, queued.severity.value)
            if queued.channel is not channel:
                queued.channel = channel
                queued.delivery_status = DeliveryStatus.PENDING
    session.flush()
    for channel, kind, title in (
        (NotificationChannel.DAILY_DIGEST, NotificationKind.DAILY_DIGEST, "Dagbundel CV-analyse"),
        (
            NotificationChannel.WEEKLY_REPORT,
            NotificationKind.WEEKLY_REPORT,
            "Weekrapport CV-analyse",
        ),
    ):
        cutoff = digest_cutoff(now, channel)
        rows = list(
            session.scalars(
                select(Notification)
                .where(
                    Notification.channel == channel,
                    Notification.delivery_status == DeliveryStatus.PENDING,
                    Notification.finding_id.is_not(None),
                    Notification.created_at_ts <= cutoff,
                )
                .order_by(Notification.created_at_ts, Notification.id)
            )
        )
        if not rows:
            continue
        visible = (
            list({row.finding_id: row for row in rows}.values()) if policy.bundle_related else rows
        )
        parent = Notification(
            kind=kind,
            channel=channel,
            title=title,
            body="\n".join(row.body for row in visible),
            payload={
                "finding_ids": sorted({str(f) for row in rows for f in row.payload["finding_ids"]}),
                "event_ids": [row.id for row in rows],
                "cutoff_ts": cutoff,
                "kind": kind.value,
            },
            delivery_status=DeliveryStatus.PENDING,
            ha_event_fired=False,
            created_at_ts=now,
        )
        session.add(parent)
        session.flush()
        for row in rows:
            row.delivery_status = DeliveryStatus.SUPPRESSED
            row.payload = {**row.payload, "bundle_notification_id": parent.id}


class NotificationService:
    """One independent dispatcher. Transport errors never affect analysis transactions."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        client: HAClient | None,
        target: str | None = None,
        *,
        clock: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
        interval_s: float = 60,
    ) -> None:
        self.sessions, self.client = sessions, client
        self.target = target
        self.clock, self.interval_s = clock, interval_s
        self._stop = asyncio.Event()
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        if target is not None and not re.fullmatch(r"(?:notify\.)?[a-z0-9_]+", target):
            raise ValueError("Notification target must be a notify service")

    def _plan(self, now: int) -> list[int]:
        with self.sessions.begin() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            plan_notifications(session, now)
            return list(
                session.scalars(
                    select(Notification.id)
                    .where(
                        Notification.delivery_status.in_(
                            (DeliveryStatus.PENDING, DeliveryStatus.FAILED)
                        ),
                        (Notification.finding_id.is_(None))
                        | (
                            Notification.channel.in_(
                                (NotificationChannel.DIRECT, NotificationChannel.NONE)
                            )
                        ),
                    )
                    .order_by(Notification.created_at_ts, Notification.id)
                )
            )

    def _load(self, ident: int) -> Notification:
        with self.sessions() as session:
            row = session.get(Notification, ident)
            assert row is not None
            session.expunge(row)
            return row

    def _record(self, ident: int, **changes: Any) -> None:
        with self.sessions.begin() as session:
            row = session.get(Notification, ident)
            assert row is not None
            for key, value in changes.items():
                setattr(row, key, value)

    def _push_enabled(self, row: Notification) -> bool:
        with self.sessions() as session:
            policy = read_policy(session)
            members = (
                [row]
                if row.finding_id is not None
                else list(
                    session.scalars(
                        select(Notification).where(
                            Notification.id.in_(row.payload.get("event_ids", []))
                        )
                    )
                )
            )
            return any(
                member.severity is not None
                and getattr(policy.channels, member.severity.value) is not NotificationChannel.NONE
                and (
                    member.kind is not NotificationKind.FINDING_WORSENED
                    or policy.renotify_on_worsening
                )
                for member in members
            )

    async def tick(self) -> None:
        async with self._lock:
            ids = await asyncio.to_thread(self._plan, self.clock())
            if self.client is None or not self.client.connected:
                return
            for ident in ids:
                await self._deliver(ident)

    async def _deliver(self, ident: int) -> None:
        assert self.client is not None
        row = await asyncio.to_thread(self._load, ident)
        try:
            if (
                self.target
                and row.channel is not NotificationChannel.NONE
                and not row.payload.get("notify_sent")
                and await asyncio.to_thread(self._push_enabled, row)
            ):
                service = self.target.removeprefix("notify.")
                await self.client.call_service(
                    "notify", service, {"title": row.title, "message": row.body}
                )
                row.payload = {**row.payload, "notify_sent": True}
                await asyncio.to_thread(
                    self._record, ident, payload=row.payload, target=f"notify.{service}"
                )
            if not row.ha_event_fired:
                await self.client.fire_event(
                    "cv_analyse_finding",
                    {
                        **row.payload,
                        "notification_id": str(ident),
                        "title": row.title,
                        "detail": row.body,
                        "channel": row.channel.value,
                    },
                )
                await asyncio.to_thread(self._record, ident, ha_event_fired=True)
            await asyncio.to_thread(
                self._record,
                ident,
                delivery_status=DeliveryStatus.SENT,
                sent_at_ts=self.clock(),
                error=None,
            )
        except (HAError, TimeoutError, OSError):
            await asyncio.to_thread(
                self._record,
                ident,
                delivery_status=DeliveryStatus.FAILED,
                error="Home Assistant heeft de melding niet volledig bevestigd; opnieuw proberen.",
            )
            logger.warning("Notification %s delivery failed; retained for retry", ident)

    async def start(self) -> None:
        self._task = asyncio.create_task(self.run(), name="notifications")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await self.tick()
            except Exception:
                logger.exception("Notification dispatch failed; analysis remains available")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_s)
