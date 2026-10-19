"""Database-backed signal mapping endpoints and availability read model."""

import math
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cvidee.analysis.types import (
    HOUR_MS,
    Mode,
    ObservationKind,
    Role,
    Scope,
    ScopeKind,
    SignalRef,
    TimeRange,
    ValueInterval,
    ValueKind,
)
from cvidee.api.problems import ProblemError, not_found
from cvidee.api.schemas.signals import (
    AnalysisList,
    AnalysisOut,
    Signal,
    SignalList,
    SignalMappingUpdate,
    SignalState,
    ValueKindName,
)
from cvidee.changes.evaluation import evaluate_changes
from cvidee.findings.stage import StoreTimelines
from cvidee.ingest.ha_client import HAClient, HAState, HAUnavailableError
from cvidee.installation import SqlInstallationProfileRepository, profile_facts
from cvidee.rules.availability import AvailabilityPolicy, assess_analyses
from cvidee.rules.base import (
    AnalysisId,
    AvailabilityIssue,
    AvailabilityStatus,
    InstallationFacts,
    IssueKind,
    signal_ref,
)
from cvidee.runner.service import AnalysisRunner
from cvidee.runner.sources import SourceSettings, build_pipeline_config, load_mapped_signals
from cvidee.settings.repository import current_revision, effective_values
from cvidee.signals.catalog import (
    ANALYSIS_NAMES,
    BY_ROLE,
    CATALOGUE,
    needed_for,
    parse_signal_id,
    sync_catalogue,
)
from cvidee.signals.quality import signal_statuses
from cvidee.store.enums import ObservationOrigin
from cvidee.store.models import SignalMapping, SourceEntity
from cvidee.store.observations import SqlObservationRepository
from cvidee.store.records import ObservationRecord

_ISSUE_LABELS = {
    IssueKind.NOT_MAPPED: "niet gekoppeld",
    IssueKind.NO_DATA: "geen gegevens",
    IssueKind.LOW_COVERAGE: "onvoldoende dekking",
    IssueKind.STALE: "verouderd",
    IssueKind.RESOLUTION: "meetresolutie te grof",
    IssueKind.RESOLUTION_UNKNOWN: "meetresolutie onbekend",
    IssueKind.NO_SCOPE_IN_PROFILE: "ontbreekt in installatieprofiel",
    IssueKind.NO_CHANGE_DATA: "geen wijziging vastgelegd",
    IssueKind.INSUFFICIENT_COMPARISON_EVIDENCE: "onvoldoende gegevens voor vergelijking",
    IssueKind.OVERLAPPING_CHANGES: "wijzigingen overlappen",
    IssueKind.WEATHER_NOT_COMPARABLE: "weer niet vergelijkbaar",
    IssueKind.SETPOINTS_NOT_COMPARABLE: "kamerdoelen niet vergelijkbaar",
}


def _issue_text(issue: AvailabilityIssue) -> str:
    label = _ISSUE_LABELS[issue.kind]
    return label if issue.role is None else f"{label}: {BY_ROLE[issue.role].name}"


def _clock() -> int:
    return time.time_ns() // 1_000_000


def _invalid(detail: str) -> ProblemError:
    return ProblemError(422, "Ongeldige signaalkoppeling", detail)


def _unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    return {"C": "°C", "degC": "°C", "m3": "m³", "l/min": "L/min"}.get(unit, unit)


class SignalsBackend:
    """Read HA states for validation, persist mappings and queue recomputations."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        client: HAClient | None = None,
        runner: AnalysisRunner | None = None,
        refresh: Callable[[], None] | None = None,
        clock: Callable[[], int] = _clock,
    ) -> None:
        self.sessions = sessions
        self.client = client
        self.runner = runner
        self.refresh = refresh
        self.clock = clock

    def _profile(self, session: Session, now: int) -> InstallationFacts:
        return profile_facts(SqlInstallationProfileRepository(session).current_or_default(now))

    def _refs(self, session: Session, now: int) -> list[str]:
        profile = self._profile(session, now)
        ids = {
            str(signal_ref(info.role, key))
            for info in CATALOGUE
            for key in (
                (None,)
                if info.role.scope_kind in (ScopeKind.BOILER, ScopeKind.OUTDOOR)
                else profile.scope_keys(info.role.scope_kind)
            )
        }
        ids.update(
            str(SignalRef(role, Scope(ScopeKind.CIRCUIT, key)))
            for role in (Role.FLOW_RATE, Role.PUMP_STATE)
            for key in profile.scope_keys(ScopeKind.CIRCUIT)
        )
        ids.update(
            str(mapping.signal) for mapping in load_mapped_signals(session) if mapping.valid_at(now)
        )
        return sorted(ids)

    @staticmethod
    def _parse(signal_id: str) -> SignalRef:
        try:
            return parse_signal_id(signal_id)
        except ValueError as exc:
            raise not_found("Signaal", signal_id) from exc

    def _signal(self, session: Session, signal_id: str, now: int) -> Signal:
        ref = self._parse(signal_id)
        role, key = ref.role, ref.scope.key
        info = BY_ROLE[role]
        scope_key = "" if key is None else f"{ref.scope.kind.value}:{key}"
        mapping = session.scalar(
            select(SignalMapping).where(
                SignalMapping.role == role.value,
                SignalMapping.scope_key == scope_key,
                SignalMapping.valid_to_ts.is_(None),
                SignalMapping.valid_from_ts <= now,
            )
        )
        entity = None if mapping is None else session.get(SourceEntity, mapping.source_entity_id)
        age = None
        state = SignalState.MISSING
        resolution = None
        if mapping is not None and entity is not None:
            row = SqlObservationRepository(session).last_before(entity.entity_id, now + 1)
            if row is not None and row.ts >= mapping.valid_from_ts:
                evidence = row.last_reported_ts if row.last_reported_ts is not None else row.ts
                age = max(0, (now - evidence) // 1000)
                if row.state not in ("unknown", "unavailable"):
                    state = (
                        SignalState.STALE
                        if mapping.heartbeat_expected and now - evidence >= mapping.max_age_ms
                        else SignalState.OK
                    )
        return Signal(
            id=signal_id,
            role=role,
            scope_kind=ref.scope.kind,
            scope_key=key,
            name=info.name if key is None else f"{info.name} {key}",
            group=info.group,
            entity_id=None if entity is None else entity.entity_id,
            unit=info.unit if mapping is None else mapping.unit,
            location=None if mapping is None else mapping.location,
            value_kind=None if mapping is None else cast(ValueKindName, mapping.kind.name.lower()),
            meaning=None if mapping is None else mapping.meaning,
            needed_for_text=", ".join(ANALYSIS_NAMES[analysis] for analysis in needed_for(role)),
            max_age_s=info.max_age_s if mapping is None else mapping.max_age_ms // 1000,
            expects_regular_updates=info.heartbeat_expected
            if mapping is None
            else mapping.heartbeat_expected,
            state=state,
            age_s=age,
            median_update_interval_s=resolution,
            expected_resolution_s=None
            if mapping is None or mapping.expected_resolution_ms is None
            else mapping.expected_resolution_ms / 1000,
            valid_from=None
            if mapping is None
            else datetime.fromtimestamp(mapping.valid_from_ts / 1000, UTC),
            value_map=None if mapping is None else mapping.value_map,
            mapping_version=None if mapping is None else mapping.id,
        )

    def signal_list(self) -> SignalList:
        now = self.clock()
        with self.sessions.begin() as session:
            sync_catalogue(session)
            items = [self._signal(session, ident, now) for ident in self._refs(session, now)]
            mappings = load_mapped_signals(session)
            rng = TimeRange(now - 24 * HOUR_MS, now)
            config = build_pipeline_config(session, mappings, SourceSettings())
            built = StoreTimelines(session, mappings, SourceSettings(), config, now).build(rng)
            statuses = {str(s.signal): s for s in signal_statuses(session, mappings, built, rng)}
            for item in items:
                status = statuses.get(item.id)
                if status is not None:
                    item.median_update_interval_s = (
                        None if status.resolution_ms is None else status.resolution_ms / 1000
                    )
                    if status.stale:
                        item.state = SignalState.STALE
                    elif not isinstance(built[parse_signal_id(item.id)].at(now - 1), ValueInterval):
                        item.state = SignalState.MISSING
            return SignalList(
                items=items,
                linked=sum(item.entity_id is not None for item in items),
                total=len(items),
            )

    async def update_signal(self, signal_id: str, body: SignalMappingUpdate) -> Signal:
        ref = self._parse(signal_id)
        role, key = ref.role, ref.scope.key
        now = self.clock()
        valid_from = now if body.valid_from is None else round(body.valid_from.timestamp() * 1000)
        if valid_from > now:
            raise _invalid("Een koppeling kan niet in de toekomst ingaan.")
        state: HAState | None = None
        if body.entity_id is not None:
            if self.client is None:
                raise ProblemError(503, "Home Assistant is niet ingesteld")
            try:
                state = next(
                    (s for s in await self.client.get_states() if s.entity_id == body.entity_id),
                    None,
                )
            except HAUnavailableError as exc:
                raise ProblemError(502, "Home Assistant is niet bereikbaar") from exc
            if state is None:
                raise _invalid(f"Home Assistant kent geen entiteit '{body.entity_id}'.")
        with self.sessions.begin() as session:
            sync_catalogue(session)
            if signal_id not in self._refs(session, now):
                raise not_found("Signaal", signal_id)
            scope_key = "" if key is None else f"{ref.scope.kind.value}:{key}"
            old = session.scalar(
                select(SignalMapping).where(
                    SignalMapping.role == role.value,
                    SignalMapping.scope_key == scope_key,
                    SignalMapping.valid_to_ts.is_(None),
                )
            )
            if old is not None and valid_from < old.valid_from_ts:
                raise _invalid("De ingangsdatum ligt vóór de huidige koppeling.")
            if old is not None:
                old.valid_to_ts = valid_from
                session.flush()
            if state is not None:
                self._save(session, role, scope_key, old, body, state, now, valid_from)
            result = self._signal(session, signal_id, now)
        if self.refresh is not None:
            self.refresh()
        if self.runner is not None:
            self.runner.request_recompute(valid_from, reason="signal_mapping_changed")
        return result

    @staticmethod
    def _save(
        session: Session,
        role: Role,
        scope_key: str,
        old: SignalMapping | None,
        body: SignalMappingUpdate,
        state: HAState,
        now: int,
        valid_from: int,
    ) -> None:
        info = BY_ROLE[role]
        source_unit = state.attributes.get("unit_of_measurement")
        unit = body.unit if body.unit is not None else source_unit
        if _unit(unit) != info.unit or (
            source_unit is not None and _unit(source_unit) != info.unit
        ):
            raise _invalid(f"Eenheid voor '{info.name}' moet {info.unit or 'zonder eenheid'} zijn.")
        entity = session.scalar(
            select(SourceEntity).where(SourceEntity.entity_id == state.entity_id)
        )
        if entity is None:
            entity = SourceEntity(entity_id=state.entity_id, first_seen_ts=now, last_seen_ts=now)
            session.add(entity)
        entity.unit = source_unit
        entity.friendly_name = state.attributes.get("friendly_name")
        entity.device_class = state.attributes.get("device_class")
        entity.last_seen_ts = now
        session.flush()
        values: dict[str, Any] = {
            "unit": info.unit,
            "location": None,
            "meaning": None,
            "kind": info.kind,
            "max_age_ms": info.max_age_s * 1000,
            "heartbeat_expected": info.heartbeat_expected,
            "expected_resolution_ms": None,
            "value_map": None,
        }
        if old is not None:
            values.update({field: getattr(old, field) for field in values})
        if role is Role.OPERATING_MODE and old is not None and old.source_entity_id != entity.id:
            # Semantics proven for one source must never follow an entity replacement.
            values["value_map"] = None
            values["meaning"] = None
        for api_name, field in {
            "unit": "unit",
            "location": "location",
            "meaning": "meaning",
            "expects_regular_updates": "heartbeat_expected",
            "value_map": "value_map",
        }.items():
            if api_name in body.model_fields_set:
                value = getattr(body, api_name)
                if value is not None or api_name in ("location", "meaning", "value_map"):
                    values[field] = info.unit if field == "unit" else value
        if role is Role.OPERATING_MODE and values["value_map"]:
            table = values["value_map"]
            if not isinstance(values["meaning"], str) or not values["meaning"].strip():
                raise _invalid("Leg de herkomst en betekenis van deze statuscode-mapping vast.")
            if any(not code.strip() or code != code.strip() for code in table):
                raise _invalid("Statuscodes mogen niet leeg zijn of spaties rondom bevatten.")
            if any(
                not isinstance(value, str) or value not in set(Mode) for value in table.values()
            ):
                raise _invalid(
                    "Koppel statuscodes alleen aan ch, dhw, standby, afterrun, "
                    "fault_blocking of unknown."
                )
        if body.value_kind is not None:
            values["kind"] = ValueKind[body.value_kind.upper()]
        if body.max_age_s is not None:
            values["max_age_ms"] = body.max_age_s * 1000
        if "expected_resolution_s" in body.model_fields_set:
            values["expected_resolution_ms"] = (
                None
                if body.expected_resolution_s is None
                else round(body.expected_resolution_s * 1000)
            )
        session.add(
            SignalMapping(
                role=role.value,
                scope_key=scope_key,
                source_entity_id=entity.id,
                valid_from_ts=valid_from,
                created_at_ts=now,
                **values,
            )
        )
        number: float | None
        try:
            number = float(state.state)
            number = number if math.isfinite(number) else None
        except ValueError:
            number = None
        SqlObservationRepository(session).add_observations(
            [
                ObservationRecord(
                    entity_id=state.entity_id,
                    ts=now,
                    state=state.state,
                    value_num=number,
                    kind=ObservationKind.POLL,
                    origin=ObservationOrigin.LIVE,
                    received_at_ts=now,
                    last_reported_ts=state.last_reported,
                )
            ]
        )
        session.flush()

    def analyses(self) -> AnalysisList:
        now = self.clock()
        rng = TimeRange(now - 24 * HOUR_MS, now)
        with self.sessions.begin() as session:
            sync_catalogue(session)
            profile = self._profile(session, now)
            mapped = load_mapped_signals(session)
            config = build_pipeline_config(session, mapped, SourceSettings())
            built = StoreTimelines(session, mapped, SourceSettings(), config, now).build(rng)
            settings = effective_values(current_revision(session))
            policy = AvailabilityPolicy(
                settings.min_assessment_coverage_pct / 100, settings.flame_resolution_s * 1000
            )
            statuses = signal_statuses(session, mapped, built, rng)
            items = []
            change_evaluations = evaluate_changes(session, now, settings, config)
            for result in assess_analyses(statuses, profile, policy, change_evaluations):
                reasons = sorted({_issue_text(issue) for issue in result.availability.issues})
                if result.analysis is AnalysisId.BEFORE_AFTER:
                    note = (
                        "Gebaseerd op vastgelegde wijzigingsevaluaties."
                        if not reasons
                        else "; ".join(reasons) + ". Vergelijking van vastgelegde wijzigingen."
                    )
                else:
                    note = (
                        "Beschikbaar op basis van de afgelopen 24 uur."
                        if not reasons
                        else "; ".join(reasons) + ". Beoordeling over de afgelopen 24 uur."
                    )
                if (
                    result.analysis.value == "consumption"
                    and result.availability.status is AvailabilityStatus.UNAVAILABLE
                ):
                    note = "Gasgegevens ontbreken. " + note
                items.append(
                    AnalysisOut(
                        id=result.analysis,
                        name=ANALYSIS_NAMES[result.analysis],
                        status=result.availability.status,
                        note=note,
                        missing_signals=[str(ref) for ref in result.availability.missing_signals],
                    )
                )
            return AnalysisList(items=items)
