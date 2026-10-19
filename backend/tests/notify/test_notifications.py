"""Durable deduplication, severity policy, dispatch retries and true recovery."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cvidee.api.schemas.notifications import NotificationPolicyIn
from cvidee.config import Settings
from cvidee.ingest.ha_client import HAError
from cvidee.main import create_app
from cvidee.notify.backend import NotificationBackend
from cvidee.notify.service import NotificationService, digest_cutoff
from cvidee.store.enums import (
    DeliveryStatus,
    FindingLifecycle,
    NotificationChannel,
    NotificationKind,
    ResolutionReason,
    Severity,
)
from cvidee.store.models import Finding, Notification
from tests.findings.dummy import DummyRule, Emit
from tests.findings.test_engine import NOW, engine, make_ctx
from tests.runner.test_runner import make_db


def seed(factory: sessionmaker[Session], severity: Severity = Severity.HIGH) -> None:
    with factory.begin() as session:
        DummyRule.emit = (Emit(severity=severity),)
        engine(session).evaluate(make_ctx(NOW), run_id=None)
    DummyRule.emit = ()


def client() -> Any:
    class FakeHA:
        connected = True
        call_service = AsyncMock()
        fire_event = AsyncMock()

    return FakeHA()


def rows(factory: sessionmaker[Session]) -> list[Notification]:
    with factory() as session:
        result = list(session.scalars(select(Notification).order_by(Notification.id)))
        session.expunge_all()
        return result


async def test_one_notification_for_repeated_cycles_and_after_restart(tmp_path: Path) -> None:
    factory = make_db(tmp_path)
    seed(factory)
    ha = client()
    dispatcher = NotificationService(factory, ha, "notify.mobile_app_test", clock=lambda: NOW)
    await dispatcher.tick()
    for _ in range(8):
        await dispatcher.tick()
    await NotificationService(factory, ha, "mobile_app_test", clock=lambda: NOW).tick()
    assert len(rows(factory)) == 1
    assert rows(factory)[0].delivery_status is DeliveryStatus.SENT
    ha.call_service.assert_awaited_once()
    assert ha.call_service.call_args.args[:2] == ("notify", "mobile_app_test")
    ha.fire_event.assert_awaited_once()
    assert ha.fire_event.call_args.args[0] == "cv_analyse_finding"


async def test_severity_increase_renotifies_but_same_severity_does_not(tmp_path: Path) -> None:
    factory = make_db(tmp_path)
    seed(factory, Severity.MEDIUM)
    backend = NotificationBackend(factory)
    policy = backend.policy.model_dump(exclude={"recovery_text"})
    policy["channels"]["medium"] = "direct"
    backend.put_policy(NotificationPolicyIn.model_validate(policy))
    ha = client()
    dispatcher = NotificationService(factory, ha, "mobile_app_test", clock=lambda: NOW)
    await dispatcher.tick()
    with factory.begin() as session:
        finding = session.scalar(select(Finding))
        assert finding is not None
        finding.severity = Severity.HIGH
    await dispatcher.tick()
    await dispatcher.tick()
    assert [r.kind for r in rows(factory)] == [
        NotificationKind.FINDING_NEW,
        NotificationKind.FINDING_WORSENED,
    ]
    assert ha.call_service.await_count == 2


async def test_worsening_toggle_is_persisted_and_suppresses_only_repeat(tmp_path: Path) -> None:
    factory = make_db(tmp_path)
    seed(factory, Severity.LOW)
    backend = NotificationBackend(factory)
    payload = backend.policy.model_dump(exclude={"recovery_text"})
    payload.update(renotify_on_worsening=False, bundle_related=False)
    payload["channels"]["low"] = "direct"
    saved = backend.put_policy(NotificationPolicyIn.model_validate(payload))
    assert not NotificationBackend(factory).policy.bundle_related
    assert not saved.renotify_on_worsening
    ha = client()
    dispatcher = NotificationService(factory, ha, "mobile_app_test", clock=lambda: NOW)
    await dispatcher.tick()
    with factory.begin() as session:
        finding = session.scalar(select(Finding))
        assert finding is not None
        finding.severity = Severity.HIGH
    await dispatcher.tick()
    assert ha.call_service.await_count == 1
    assert rows(factory)[-1].delivery_status is DeliveryStatus.SUPPRESSED


@pytest.mark.parametrize(
    "reason",
    [ResolutionReason.RECOVERED, ResolutionReason.SETTINGS_CHANGED, ResolutionReason.SUPERSEDED],
)
async def test_recovery_requires_engine_proof(tmp_path: Path, reason: ResolutionReason) -> None:
    factory = make_db(tmp_path)
    seed(factory)
    ha = client()
    dispatcher = NotificationService(factory, ha, clock=lambda: NOW)
    await dispatcher.tick()
    # Without an engine resolution, lack of newer samples does not resolve an alert.
    await dispatcher.tick()
    assert len(rows(factory)) == 1
    with factory.begin() as session:
        finding = session.scalar(select(Finding))
        assert finding is not None
        finding.lifecycle = FindingLifecycle.RESOLVED
        finding.resolution_reason = reason
        finding.resolved_at_ts = NOW
    await dispatcher.tick()
    assert len(rows(factory)) == (2 if reason is ResolutionReason.RECOVERED else 1)
    if reason is ResolutionReason.RECOVERED:
        assert rows(factory)[-1].kind is NotificationKind.FINDING_RESOLVED


async def test_partial_delivery_retries_event_without_repeating_successful_notify(
    tmp_path: Path,
) -> None:
    factory = make_db(tmp_path)
    seed(factory)
    ha = client()
    ha.fire_event.side_effect = [HAError("unavailable"), None]
    dispatcher = NotificationService(factory, ha, "mobile_app_test", clock=lambda: NOW)
    await dispatcher.tick()
    assert rows(factory)[0].delivery_status is DeliveryStatus.FAILED
    await dispatcher.tick()
    assert rows(factory)[0].delivery_status is DeliveryStatus.SENT
    assert ha.call_service.await_count == 1
    assert ha.fire_event.await_count == 2


async def test_no_notify_channel_still_exposes_one_automation_event(tmp_path: Path) -> None:
    factory = make_db(tmp_path)
    seed(factory, Severity.INFO)
    ha = client()
    dispatcher = NotificationService(factory, ha, "mobile_app_test", clock=lambda: NOW)
    await dispatcher.tick()
    ha.call_service.assert_not_awaited()
    ha.fire_event.assert_awaited_once()
    assert rows(factory)[0].delivery_status is DeliveryStatus.SENT


async def test_daily_digest_waits_for_next_local_boundary_and_survives_restart(
    tmp_path: Path,
) -> None:
    factory = make_db(tmp_path)
    seed(factory, Severity.MEDIUM)
    now = round(datetime(2026, 10, 24, 7, tzinfo=UTC).timestamp() * 1000)
    ha = client()
    dispatcher = NotificationService(factory, ha, "mobile_app_test", clock=lambda: now)
    await dispatcher.tick()
    ha.call_service.assert_not_awaited()
    now = round(datetime(2026, 10, 25, 7, tzinfo=UTC).timestamp() * 1000)
    await NotificationService(factory, ha, "mobile_app_test", clock=lambda: now).tick()
    ha.call_service.assert_awaited_once()
    sent = [r for r in rows(factory) if r.delivery_status is DeliveryStatus.SENT]
    assert len(sent) == 1
    assert sent[0].kind is NotificationKind.DAILY_DIGEST
    await dispatcher.tick()
    assert ha.call_service.await_count == 1


@pytest.mark.parametrize(
    ("at", "expected"),
    [
        ("2026-10-25T06:59:00+00:00", "2026-10-24T06:00:00+00:00"),
        ("2026-10-25T07:00:00+00:00", "2026-10-25T07:00:00+00:00"),
    ],
)
def test_daily_cutoff_uses_amsterdam_dst(at: str, expected: str) -> None:
    epoch = round(datetime.fromisoformat(at).timestamp() * 1000)
    cutoff = digest_cutoff(epoch, NotificationChannel.DAILY_DIGEST)
    assert datetime.fromtimestamp(cutoff / 1000, UTC).isoformat() == expected


async def test_real_policy_routes_and_paginated_sent_log(tmp_path: Path) -> None:
    factory = make_db(tmp_path)
    seed(factory)
    await NotificationService(factory, client(), clock=lambda: NOW).tick()
    app = create_app(Settings())
    app.state.session_factory = factory
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        policy = (await http.get("/api/notifications/policy")).json()
        assert policy["channels"] == {
            "high": "direct",
            "medium": "daily_digest",
            "low": "weekly_report",
            "info": "none",
        }
        assert "90 %" in policy.pop("recovery_text")
        policy["channels"]["info"] = "daily_digest"
        updated = await http.put("/api/notifications/policy", json=policy)
        assert updated.status_code == 200
        assert updated.json()["channels"]["info"] == "daily_digest"
        log = (await http.get("/api/notifications?limit=1&offset=0")).json()
        assert log["total"] == 1
        assert log["items"][0]["finding_id"] == "B-001"


def test_device_service_target_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="notify service"):
        NotificationService(make_db(tmp_path), client(), "climate.set_temperature")


async def test_weekly_report_and_related_bundling_keep_all_event_ids(tmp_path: Path) -> None:
    factory = make_db(tmp_path)
    seed(factory, Severity.LOW)
    now = round(datetime(2026, 10, 20, 8, tzinfo=UTC).timestamp() * 1000)
    ha = client()
    dispatcher = NotificationService(factory, ha, "mobile_app_test", clock=lambda: now)
    await dispatcher.tick()
    ha.call_service.assert_not_awaited()
    # Two observed transitions before next Monday are bundled to the final state.
    with factory.begin() as session:
        finding = session.scalar(select(Finding))
        assert finding is not None
        finding.lifecycle = FindingLifecycle.RESOLVED
        finding.resolution_reason = ResolutionReason.RECOVERED
        finding.resolved_at_ts = now
    await dispatcher.tick()
    now = round(datetime(2026, 10, 26, 7, tzinfo=UTC).timestamp() * 1000)
    await dispatcher.tick()
    ha.call_service.assert_awaited_once()
    report = rows(factory)[-1]
    assert report.kind is NotificationKind.WEEKLY_REPORT
    assert len(report.payload["event_ids"]) == 2
    assert report.payload["finding_ids"] == ["B-001"]
    assert "Bevinding hersteld" in report.body
    assert "Nieuwe bevinding" not in report.body


async def test_disabling_bundling_keeps_distinct_transitions_in_digest(tmp_path: Path) -> None:
    factory = make_db(tmp_path)
    seed(factory, Severity.MEDIUM)
    backend = NotificationBackend(factory)
    policy = backend.policy.model_dump(exclude={"recovery_text"})
    policy["bundle_related"] = False
    backend.put_policy(NotificationPolicyIn.model_validate(policy))
    now = round(datetime(2026, 10, 20, 8, tzinfo=UTC).timestamp() * 1000)
    dispatcher = NotificationService(factory, client(), clock=lambda: now)
    await dispatcher.tick()
    with factory.begin() as session:
        finding = session.scalar(select(Finding))
        assert finding is not None
        finding.lifecycle = FindingLifecycle.RESOLVED
        finding.resolution_reason = ResolutionReason.RECOVERED
        finding.resolved_at_ts = now
    await dispatcher.tick()
    now += 24 * 3_600_000
    await dispatcher.tick()
    report = rows(factory)[-1]
    assert "Nieuwe bevinding" in report.body
    assert "Bevinding hersteld" in report.body


async def test_disconnected_ha_keeps_outbox_for_later_delivery(tmp_path: Path) -> None:
    factory = make_db(tmp_path)
    seed(factory)
    ha = client()
    ha.connected = False
    await NotificationService(factory, ha, clock=lambda: NOW).tick()
    assert rows(factory)[0].delivery_status is DeliveryStatus.PENDING
    ha.fire_event.assert_not_awaited()
    ha.connected = True
    await NotificationService(factory, ha, clock=lambda: NOW).tick()
    assert rows(factory)[0].delivery_status is DeliveryStatus.SENT
    ha.fire_event.assert_awaited_once()


async def test_channel_change_applies_to_unsent_alerts(tmp_path: Path) -> None:
    factory = make_db(tmp_path)
    seed(factory)
    ha = client()
    ha.connected = False
    dispatcher = NotificationService(factory, ha, "mobile_app_test", clock=lambda: NOW)
    await dispatcher.tick()
    backend = NotificationBackend(factory)
    policy = backend.policy.model_dump(exclude={"recovery_text"})
    policy["channels"]["high"] = "none"
    backend.put_policy(NotificationPolicyIn.model_validate(policy))
    ha.connected = True
    await dispatcher.tick()
    ha.call_service.assert_not_awaited()
    ha.fire_event.assert_awaited_once()
    assert rows(factory)[0].channel is NotificationChannel.NONE


async def test_disabled_channel_stops_push_of_already_prepared_digest(tmp_path: Path) -> None:
    factory = make_db(tmp_path)
    seed(factory, Severity.MEDIUM)
    now = round(datetime(2026, 10, 20, 8, tzinfo=UTC).timestamp() * 1000)
    ha = client()
    ha.connected = False
    dispatcher = NotificationService(factory, ha, "mobile_app_test", clock=lambda: now)
    await dispatcher.tick()
    now += 24 * 3_600_000
    await dispatcher.tick()
    assert rows(factory)[-1].kind is NotificationKind.DAILY_DIGEST
    backend = NotificationBackend(factory)
    policy = backend.policy.model_dump(exclude={"recovery_text"})
    policy["channels"]["medium"] = "none"
    backend.put_policy(NotificationPolicyIn.model_validate(policy))
    ha.connected = True
    await dispatcher.tick()
    ha.call_service.assert_not_awaited()
    ha.fire_event.assert_awaited_once()


async def test_enabled_day_and_week_reports_are_idempotent(tmp_path: Path) -> None:
    factory = make_db(tmp_path)
    policy = NotificationBackend(factory).policy.model_dump(exclude={"recovery_text"})
    policy.update(daily_report_enabled=True, weekly_report_enabled=True)
    NotificationBackend(factory).put_policy(NotificationPolicyIn.model_validate(policy))
    built: list[tuple[str, str]] = []

    def build(kind: Any, reference_date: Any) -> Any:
        built.append((kind.value, reference_date.isoformat()))
        return SimpleNamespace(
            cycle_summary=SimpleNamespace(ch_cycles=3, dhw_cycles=1), findings=[1], changes=[]
        )

    monday_0800 = round(datetime(2026, 10, 19, 6, tzinfo=UTC).timestamp() * 1000)
    ha = client()
    dispatcher = NotificationService(
        factory, ha, "notify.mobile_app_test", clock=lambda: monday_0800, report_builder=build
    )
    await dispatcher.tick()
    await dispatcher.tick()
    reports = [row for row in rows(factory) if row.payload.get("kind") == "report"]
    assert {(row.payload["report_kind"], row.payload["report_period"]) for row in reports} == {
        ("day", "day:2026-10-18"),
        ("week", "week:2026-10-12"),
    }
    assert len(reports) == 2
    assert all(row.delivery_status is DeliveryStatus.SENT for row in reports)
    assert ha.call_service.await_count == 2


async def test_turning_off_report_delivery_suppresses_a_queued_report(tmp_path: Path) -> None:
    factory = make_db(tmp_path)
    backend = NotificationBackend(factory)
    policy = backend.policy.model_dump(exclude={"recovery_text"})
    policy["daily_report_enabled"] = True
    backend.put_policy(NotificationPolicyIn.model_validate(policy))

    def build(kind: Any, reference_date: Any) -> Any:
        return SimpleNamespace(
            cycle_summary=SimpleNamespace(ch_cycles=0, dhw_cycles=0), findings=[], changes=[]
        )

    monday_0800 = round(datetime(2026, 10, 19, 6, tzinfo=UTC).timestamp() * 1000)
    ha = client()
    ha.connected = False
    dispatcher = NotificationService(
        factory, ha, "mobile_app_test", clock=lambda: monday_0800, report_builder=build
    )
    await dispatcher.tick()
    queued = next(row for row in rows(factory) if row.payload.get("kind") == "report")
    assert queued.delivery_status is DeliveryStatus.PENDING

    policy["daily_report_enabled"] = False
    backend.put_policy(NotificationPolicyIn.model_validate(policy))
    ha.connected = True
    await dispatcher.tick()
    updated = next(row for row in rows(factory) if row.id == queued.id)
    assert updated.delivery_status is DeliveryStatus.SUPPRESSED
    ha.call_service.assert_not_awaited()
    ha.fire_event.assert_not_awaited()


def test_notification_policy_preserves_analysis_and_onboarding_across_saves(tmp_path: Path) -> None:
    from cvidee.api.schemas.settings import SettingsIn
    from cvidee.settings.backend import SettingsBackend

    factory = make_db(tmp_path)
    settings = SettingsBackend(factory)
    initial = settings.settings()
    completed = datetime(2026, 10, 18, 10, tzinfo=UTC)
    saved = settings.put_settings(
        SettingsIn(
            revision=initial.revision,
            values=initial.values.model_copy(update={"gas_price_eur_per_m3": 1.25}),
            onboarding_completed_at=completed,
        )
    )
    notifications = NotificationBackend(factory)
    policy = notifications.policy.model_dump(exclude={"recovery_text"})
    policy["bundle_related"] = False
    notifications.put_policy(NotificationPolicyIn.model_validate(policy))
    after_policy = settings.settings()
    assert after_policy.values.gas_price_eur_per_m3 == 1.25
    assert after_policy.onboarding_completed_at == completed
    assert after_policy.revision != saved.revision
    settings.put_settings(
        SettingsIn(
            revision=after_policy.revision,
            values=after_policy.values.model_copy(update={"recovery_days": 5}),
        )
    )
    assert not notifications.policy.bundle_related
    assert notifications.policy.recovery_text.startswith("5 dagen zonder patroon")
