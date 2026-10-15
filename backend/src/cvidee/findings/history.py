"""Immutable recommendation history and comparison with today's rules (FR-41)."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cvidee.api.schemas.common import Page, TimeRange
from cvidee.api.schemas.findings import HistoryEntry, RuleRef
from cvidee.api.stubs.fixtures import status_text
from cvidee.installation.repository import SqlInstallationProfileRepository
from cvidee.installation.specs import SPEC_BY_KEY
from cvidee.rules.changelog import changes_since
from cvidee.rules.registry import RuleRegistry
from cvidee.settings.repository import current_revision, effective_values, rule_params
from cvidee.store.enums import SnapshotTrigger
from cvidee.store.models import AnalysisRun, Finding, RecommendationSnapshot


def latest_snapshot(session: Session, recommendation_id: int) -> RecommendationSnapshot | None:
    return session.scalar(
        select(RecommendationSnapshot)
        .where(RecommendationSnapshot.recommendation_id == recommendation_id)
        .order_by(RecommendationSnapshot.id.desc())
        .limit(1)
    )


def profile_settings(session: Session, profile_id: int | None) -> dict[str, Any] | None:
    profile = (
        None if profile_id is None else SqlInstallationProfileRepository(session).get(profile_id)
    )
    if profile is None:
        return None
    return {
        "version": str(profile.id),
        "details": deepcopy(profile.details),
        "specs": [
            {
                "key": s.key,
                "scope": s.scope_key,
                "status": str(s.status),
                "value": s.value_num if s.value_num is not None else s.value_text,
                "unit": s.unit,
            }
            for s in sorted(profile.specs, key=lambda s: (s.scope_key, s.key))
        ],
    }


def snapshot_transition(session: Session, finding: Finding, now: int) -> None:
    """Record a status transition without replacing the advice's original provenance."""
    from cvidee.api.findings_read import FindingsReadModel
    from cvidee.findings.repository import SqlFindingRepository

    rec = SqlFindingRepository(session).recommendation_of(finding)
    if rec is None:
        return
    previous = latest_snapshot(session, rec.id)
    rendered = (
        FindingsReadModel(session, lambda: now, refresh_status=False)
        .finding(finding.human_id)
        .model_dump(mode="json")
    )
    run = None if finding.last_run_id is None else session.get(AnalysisRun, finding.last_run_id)
    if previous is None:
        # Legacy findings may predate snapshots. Only use recorded run provenance.
        settings = {} if run is None else deepcopy(run.stats.get("settings", {}))
        profile = SqlInstallationProfileRepository(session).at(finding.period_end_ts)
        profile_id = None if profile is None else profile.id
        settings["installation_profile"] = profile_settings(session, profile_id)
        session.add(
            RecommendationSnapshot(
                recommendation_id=rec.id,
                finding_id=finding.id,
                taken_at_ts=now,
                trigger=SnapshotTrigger.STATUS_CHANGED,
                status=rec.status,
                outcome=rec.outcome,
                measurement_start_ts=finding.period_start_ts,
                measurement_end_ts=finding.period_end_ts,
                rule_id=rec.rule_id,
                rule_version=rec.rule_version,
                rule_params=deepcopy(finding.rule_params),
                profile_id=profile_id,
                settings_revision_id=None if run is None else run.settings_revision_id,
                config_hash="" if run is None else run.config_hash or "",
                settings=settings,
                content=rendered,
                note=max(rec.notes, key=lambda n: (n.created_at_ts, n.id)).text
                if rec.notes
                else None,
            )
        )
        session.flush()
        return
    content = deepcopy(previous.content)
    for key in ("status", "status_text", "postponed_until", "notes"):
        content[key] = rendered[key]
    session.add(
        RecommendationSnapshot(
            recommendation_id=rec.id,
            finding_id=finding.id,
            taken_at_ts=now,
            trigger=SnapshotTrigger.STATUS_CHANGED,
            status=rec.status,
            outcome=rec.outcome,
            measurement_start_ts=previous.measurement_start_ts,
            measurement_end_ts=previous.measurement_end_ts,
            rule_id=previous.rule_id,
            rule_version=previous.rule_version,
            rule_params=deepcopy(previous.rule_params),
            profile_id=previous.profile_id,
            settings_revision_id=previous.settings_revision_id,
            config_hash=previous.config_hash,
            settings=deepcopy(previous.settings),
            content=content,
            note=max(rec.notes, key=lambda n: (n.created_at_ts, n.id)).text if rec.notes else None,
        )
    )
    session.flush()


def _value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:g}".replace(".", ",")
    if value is None:
        return "onbekend"
    if isinstance(value, bool):
        return "ja" if value else "nee"
    return str(value)


class HistoryReadModel:
    def __init__(self, session: Session, registry: RuleRegistry) -> None:
        self.session = session
        self.registry = registry

    def history(self, limit: int, offset: int) -> Page[HistoryEntry]:
        total = self.session.scalar(select(func.count()).select_from(RecommendationSnapshot)) or 0
        rows = self.session.scalars(
            select(RecommendationSnapshot)
            .order_by(RecommendationSnapshot.taken_at_ts.desc(), RecommendationSnapshot.id.desc())
            .limit(limit)
            .offset(offset)
        )
        values = effective_values(current_revision(self.session))
        items = []
        for row in rows:
            fields = self._parameter_fields(row.rule_id)
            labels = [
                f"{fields.get(key, {}).get('title', key)}: {_value(value)}"
                + (f" {fields[key]['unit']}" if fields.get(key, {}).get("unit") else "")
                for key, value in sorted(row.rule_params.items())
            ]
            profile = row.settings.get("installation_profile") or profile_settings(
                self.session, row.profile_id
            )
            if profile:
                labels.insert(0, f"Profielversie {profile['version']}")
                for spec in profile.get("specs", []):
                    info = SPEC_BY_KEY.get(spec["key"])
                    label = info.label if info else spec["key"]
                    scope = f" ({spec['scope']})" if spec["scope"] else ""
                    value = (
                        "niet van toepassing"
                        if spec["status"] == "not_applicable"
                        else _value(spec["value"])
                    )
                    labels.append(
                        f"{label}{scope}: {value}"
                        + (f" {spec['unit']}" if spec["unit"] and spec["value"] is not None else "")
                    )
            if row.rule_id not in self.registry:
                since = (
                    "Deze regel is niet meer beschikbaar; "
                    "het oorspronkelijke advies blijft bewaard."
                )
            else:
                current = self.registry.get(row.rule_id)
                params = rule_params(self.registry, row.rule_id, values).model_dump(mode="json")
                changes = []
                if current.version != row.rule_version:
                    changes.append(
                        f"Regelversie gewijzigd van {row.rule_version} naar {current.version}."
                    )
                    changes.extend(changes_since(row.rule_id, row.rule_version, current.version))
                for key in sorted(row.rule_params.keys() | params.keys()):
                    if row.rule_params.get(key) != params.get(key):
                        label = fields.get(key, {}).get("title", key)
                        changes.append(
                            f"{label}: {_value(row.rule_params.get(key))} "
                            f"→ {_value(params.get(key))}."
                        )
                since = " ".join(changes) or "Regelversie en parameters zijn ongewijzigd."
            finding = self.session.get(Finding, row.finding_id)
            advice = row.content.get("recommendation") or {}
            items.append(
                HistoryEntry(
                    id=str(row.id),
                    recorded_at=datetime.fromtimestamp(row.taken_at_ts / 1000, UTC),
                    recommendation=advice.get("action") or row.content.get("title", "Aanbeveling"),
                    finding_id=row.content.get("id")
                    or (finding.human_id if finding else str(row.finding_id)),
                    observation_period=TimeRange(
                        start=datetime.fromtimestamp(row.measurement_start_ts / 1000, UTC),
                        end=datetime.fromtimestamp(row.measurement_end_ts / 1000, UTC),
                    ),
                    settings_text=" · ".join(labels) or "Instellingen niet vastgelegd.",
                    rule=RuleRef(id=row.rule_id, version=row.rule_version),
                    status=row.status,
                    outcome=row.outcome,
                    status_text=status_text(
                        row.status,
                        datetime.fromisoformat(row.content["postponed_until"])
                        if row.content.get("postponed_until")
                        else None,
                    ),
                    reasoning=" ".join(
                        filter(
                            None,
                            [
                                row.content.get("observation"),
                                row.content.get("interpretation"),
                                advice.get("reason"),
                            ],
                        )
                    ),
                    note=row.note,
                    rule_now_text=since,
                    parameters=deepcopy(row.rule_params),
                    config_hash=row.config_hash or None,
                    profile_version=None if row.profile_id is None else str(row.profile_id),
                )
            )
        return Page[HistoryEntry](items=items, total=total, limit=limit, offset=offset)

    def _parameter_fields(self, rule_id: str) -> dict[str, dict[str, Any]]:
        if rule_id not in self.registry:
            return {}
        return {
            key: {
                "title": field.title or key,
                "unit": (field.json_schema_extra or {}).get("x-unit"),
            }
            for key, field in self.registry.get(rule_id).params_schema.model_fields.items()
            if isinstance(field.json_schema_extra, dict) or field.json_schema_extra is None
        }
