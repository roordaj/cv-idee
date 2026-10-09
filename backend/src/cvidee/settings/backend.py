"""Immutable settings revisions with optimistic locking and recompute requests."""

import time
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cvidee.api.problems import ProblemError
from cvidee.api.schemas.settings import (
    SettingsHistory,
    SettingsIn,
    SettingsResponse,
    SettingsRevisionOut,
)
from cvidee.rules.registry import RuleRegistry, default_registry
from cvidee.runner.service import AnalysisRunner
from cvidee.runner.sources import earliest_data_ts, load_mapped_signals
from cvidee.settings.repository import (
    current_revision,
    effective_values,
    revision_token,
    rule_params,
    settings_hash,
    settings_schema,
)
from cvidee.store.models import SettingsRevision


def _clock() -> int:
    return time.time_ns() // 1_000_000


class SettingsBackend:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        runner: AnalysisRunner | None = None,
        registry: RuleRegistry | None = None,
        clock: Callable[[], int] = _clock,
    ) -> None:
        self.sessions = sessions
        self.runner = runner
        self.registry = registry if registry is not None else default_registry()
        self.clock = clock

    def _response(self, row: SettingsRevision | None, recompute: bool = False) -> SettingsResponse:
        return SettingsResponse(
            revision=revision_token(row),
            updated_at=None
            if row is None
            else datetime.fromtimestamp(row.created_at_ts / 1000, UTC),
            values=effective_values(row),
            onboarding_completed_at=None
            if row is None or row.onboarding_completed_at_ts is None
            else datetime.fromtimestamp(row.onboarding_completed_at_ts / 1000, UTC),
            recompute_started=recompute,
            json_schema=settings_schema(self.registry),
        )

    def settings(self) -> SettingsResponse:
        with self.sessions() as session:
            return self._response(current_revision(session))

    def put_settings(self, body: SettingsIn) -> SettingsResponse:
        try:
            for rule in self.registry:
                rule_params(self.registry, rule.id, body.values)
        except ValidationError as exc:
            raise ProblemError(422, "Ongeldige regelparameters", str(exc)) from exc
        now = self.clock()
        with self.sessions.begin() as session:
            # Acquire SQLite's single-writer lock before reading the revision, so two
            # concurrent saves cannot both accept an obsolete token.
            from sqlalchemy import text

            session.execute(text("BEGIN IMMEDIATE"))
            current = current_revision(session)
            if body.revision != revision_token(current):
                raise ProblemError(
                    409,
                    "Instellingen zijn intussen gewijzigd",
                    "Herlaad om de nieuwste waarden te zien.",
                )
            onboarding = None if current is None else current.onboarding_completed_at_ts
            if "onboarding_completed_at" in body.model_fields_set:
                onboarding = (
                    None
                    if body.onboarding_completed_at is None
                    else round(body.onboarding_completed_at.timestamp() * 1000)
                )
            changed = body.values != effective_values(current)
            if not changed and onboarding == (
                None if current is None else current.onboarding_completed_at_ts
            ):
                return self._response(current)
            row = SettingsRevision(
                values={
                    **(
                        {}
                        if current is None
                        else {
                            key: value
                            for key, value in current.values.items()
                            if key not in type(body.values).model_fields
                            and key != "retention.raw_days"
                        }
                    ),
                    **body.values.model_dump(mode="json"),
                },
                config_hash=settings_hash(body.values),
                created_at_ts=now,
                changed_by=body.changed_by,
                note=body.note,
                onboarding_completed_at_ts=onboarding,
            )
            session.add(row)
            session.flush()
            start = earliest_data_ts(session, load_mapped_signals(session)) if changed else None
            response = self._response(row, self.runner is not None and start is not None)
        if response.recompute_started and self.runner is not None and start is not None:
            self.runner.request_recompute(start, reason="settings_changed")
        return response

    def settings_history(self) -> SettingsHistory:
        with self.sessions() as session:
            rows = session.scalars(select(SettingsRevision).order_by(SettingsRevision.id.desc()))
            return SettingsHistory(
                items=[
                    SettingsRevisionOut(
                        revision=revision_token(row),
                        config_hash=row.config_hash,
                        saved_at=datetime.fromtimestamp(row.created_at_ts / 1000, UTC),
                        changed_by=row.changed_by,
                        note=row.note,
                        values=effective_values(row),
                    )
                    for row in rows
                ]
            )
