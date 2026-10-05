"""Database-backed installation profile and special periods (FR-02, FR-03, FR-10).

The real implementation behind ``/api/installation`` and ``/api/periods`` (the stub serves
them with ``CVIDEE_STUB_DATA``). Every change queues a recompute of the affected range.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cvidee.analysis.types import TimestampMs
from cvidee.api.problems import ProblemError, not_found
from cvidee.api.schemas.data import (
    PeriodExclusions,
    SpecialPeriod,
    SpecialPeriodIn,
    SpecialPeriodList,
)
from cvidee.api.schemas.installation import (
    BoilerInfo,
    Circuit,
    InstallationProfile,
    InstallationProfileIn,
    Room,
    Specification,
)
from cvidee.installation import SqlInstallationProfileRepository
from cvidee.installation.specs import MODULATION_TO_KW, SPEC_BY_KEY
from cvidee.periods import SqlSpecialPeriodRepository
from cvidee.runner.service import AnalysisRunner
from cvidee.store.enums import CircuitKind, EmitterType, SpecStatus
from cvidee.store.models import (
    Change,
    InstallationSpec,
    ProfileCircuit,
    ProfileRoom,
    ProfileZone,
)
from cvidee.store.models import InstallationProfile as ProfileRow
from cvidee.store.models import SpecialPeriod as PeriodRow

_EMITTER_TEXT = {
    EmitterType.RADIATOR: "radiatoren",
    EmitterType.UNDERFLOOR: "vloerverwarming",
    EmitterType.OTHER: "overige afgifte",
    EmitterType.UNKNOWN: "onbekende afgifte",
}
_PERIOD_ID = re.compile(r"^P-(\d+)$")


def _wall_clock_ms() -> TimestampMs:
    return int(time.time() * 1000)


def _dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts / 1000, UTC)


def _ms(value: datetime) -> int:
    return round(value.timestamp() * 1000)


def _invalid(detail: str) -> ProblemError:
    return ProblemError(422, "Ongeldig installatieprofiel", detail)


class ConfigBackend:
    """Installation profile and special periods over the database."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        runner: AnalysisRunner | None = None,
        clock: Callable[[], TimestampMs] = _wall_clock_ms,
    ) -> None:
        self._sessions = sessions
        self._runner = runner
        self._clock = clock

    def _recompute(self, start_ts: int, end_ts: int | None, reason: str) -> None:
        if self._runner is not None:
            self._runner.request_recompute(start_ts, end_ts, reason=reason)

    # ------------------------------------------------------------ installation

    def installation_profile(self) -> InstallationProfile:
        with self._sessions.begin() as session:
            profile = SqlInstallationProfileRepository(session).current_or_default(self._clock())
            return self._to_schema(session, profile)

    def put_installation(self, body: InstallationProfileIn) -> InstallationProfile:
        now = self._clock()
        with self._sessions.begin() as session:
            repo = SqlInstallationProfileRepository(session)
            current = repo.current_or_default(now)
            if body.revision != current.id:
                raise ProblemError(
                    409,
                    "Installatieprofiel is intussen gewijzigd",
                    "Herlaad om de nieuwste gegevens te zien.",
                )
            new = self._build(session, body, current, now)
            if _signature(new) == _signature(current):
                return self._to_schema(session, current)
            repo.save_new_version(new)
            result = self._to_schema(session, new)
        self._recompute(now, None, "installation_changed")
        return result

    def _build(
        self, session: Session, body: InstallationProfileIn, current: ProfileRow, now: int
    ) -> ProfileRow:
        circuit_keys = [c.id for c in body.circuits]
        room_keys = [r.key for r in body.rooms]
        if len(set(circuit_keys)) != len(circuit_keys):
            raise _invalid("Circuit-id's moeten uniek zijn.")
        if len(set(room_keys)) != len(room_keys):
            raise _invalid("Ruimtesleutels moeten uniek zijn.")
        room_circuit: dict[str, str] = {}
        for circuit in body.circuits:
            if circuit.kind is CircuitKind.MIXING_MANIFOLD and circuit.loops is None:
                raise _invalid(f"Mengverdeler '{circuit.id}' heeft een aantal groepen nodig.")
            for room in circuit.rooms:
                if room not in room_keys:
                    raise _invalid(f"Circuit '{circuit.id}' verwijst naar onbekende ruimte '{room}'.")
                if room in room_circuit:
                    raise _invalid(f"Ruimte '{room}' hangt aan meerdere circuits.")
                room_circuit[room] = circuit.id
        old_rooms = {r.key: r for r in current.rooms}
        return ProfileRow(
            valid_from_ts=now,
            created_at_ts=now,
            note=None,
            details={
                "boiler": body.boiler.model_dump(),
                "circuits": {
                    c.id: {"loops": c.loops, "note": c.note} for c in body.circuits
                },
                "rooms": {
                    r.key: {
                        "has_sensor": r.has_sensor,
                        "schedule_text": r.schedule_text,
                        "setpoint": r.setpoint,
                        "night_setpoint": r.night_setpoint,
                    }
                    for r in body.rooms
                },
            },
            circuits=[
                ProfileCircuit(
                    key=c.id,
                    name=c.name,
                    kind=c.kind,
                    emitter=c.emitter,
                )
                for c in body.circuits
            ],
            zones=[
                ProfileZone(key=z.key, name=z.name, circuit_key=z.circuit_key)
                for z in current.zones
            ],
            rooms=[
                ProfileRoom(
                    key=r.key,
                    name=r.name,
                    circuit_key=room_circuit.get(r.key),
                    zone_key=old_rooms[r.key].zone_key if r.key in old_rooms else None,
                    has_thermostat=r.is_thermostat,
                    is_demand_source=old_rooms[r.key].is_demand_source
                    if r.key in old_rooms and r.is_thermostat
                    else False,
                )
                for r in body.rooms
            ],
            specs=self._specs(session, body.specifications),
        )

    @staticmethod
    def _specs(session: Session, specs: list[Specification]) -> list[InstallationSpec]:
        if len({s.key for s in specs}) != len(specs):
            raise _invalid("Specificatiesleutels moeten uniek zijn.")
        rows: list[InstallationSpec] = []
        for spec in specs:
            info = SPEC_BY_KEY.get(spec.key)
            if info is None:
                raise _invalid(f"Onbekende specificatie '{spec.key}'.")
            if spec.status is SpecStatus.KNOWN:
                if spec.value is None:
                    raise _invalid(f"'{spec.key}' is bekend maar heeft geen waarde.")
                if spec.key == MODULATION_TO_KW and (
                    isinstance(spec.value, str) or spec.value <= 0
                ):
                    raise _invalid("Modulatie → kW vraagt een positieve numerieke omrekening.")
            elif spec.value is not None:
                raise _invalid(f"'{spec.key}' is {spec.status.value}; een waarde is niet toegestaan.")
            change_pk: int | None = None
            if spec.change_id is not None:
                change_pk = session.scalar(
                    select(Change.id).where(Change.human_id == spec.change_id)
                )
                if change_pk is None:
                    raise _invalid(f"Onbekende wijziging '{spec.change_id}'.")
            is_text = isinstance(spec.value, str)
            rows.append(
                InstallationSpec(
                    scope_key="",
                    key=spec.key,
                    status=spec.status,
                    value_num=None if is_text or spec.value is None else float(spec.value),
                    value_text=spec.value if isinstance(spec.value, str) else None,
                    unit=spec.unit if spec.unit is not None else info.unit,
                    note=spec.note or None,
                    change_id=change_pk,
                )
            )
        return rows

    @staticmethod
    def _to_schema(session: Session, profile: ProfileRow) -> InstallationProfile:
        details: dict[str, Any] = profile.details
        boiler = BoilerInfo.model_validate(details["boiler"])
        circuit_details = details.get("circuits", {})
        room_details = details.get("rooms", {})
        circuits = [
            Circuit(
                id=c.key,
                name=c.name,
                kind=c.kind,
                emitter=c.emitter,
                loops=circuit_details.get(c.key, {}).get("loops"),
                rooms=[r.key for r in profile.rooms if r.circuit_key == c.key],
                note=circuit_details.get(c.key, {}).get("note", ""),
            )
            for c in profile.circuits
        ]
        rooms = [
            Room(
                key=r.key,
                name=r.name,
                has_sensor=room_details.get(r.key, {}).get("has_sensor", False),
                is_thermostat=r.has_thermostat,
                schedule_text=room_details.get(r.key, {}).get("schedule_text"),
                setpoint=room_details.get(r.key, {}).get("setpoint"),
                night_setpoint=room_details.get(r.key, {}).get("night_setpoint"),
            )
            for r in profile.rooms
        ]
        specs: list[Specification] = []
        for s in profile.specs:
            human = (
                session.scalar(select(Change.human_id).where(Change.id == s.change_id))
                if s.change_id is not None
                else None
            )
            info = SPEC_BY_KEY.get(s.key)
            specs.append(
                Specification(
                    key=s.key,
                    label=info.label if info else s.key,
                    status=s.status,
                    value=s.value_num if s.value_num is not None else s.value_text,
                    unit=s.unit,
                    note=s.note or "",
                    since=_dt(profile.valid_from_ts) if human is not None else None,
                    change_id=human,
                )
            )
        order = {key: i for i, key in enumerate(SPEC_BY_KEY)}
        specs.sort(key=lambda s: order.get(s.key, len(order)))
        summary = ", ".join(
            f"{_EMITTER_TEXT[c.emitter]} {c.name.lower()}" for c in circuits
        )
        return InstallationProfile(
            boiler=boiler,
            circuits=circuits,
            rooms=rooms,
            specifications=specs,
            revision=profile.id,
            summary=summary[:1].upper() + summary[1:],
            updated_at=_dt(profile.created_at_ts),
        )

    # ----------------------------------------------------------------- periods

    def period_list(self) -> SpecialPeriodList:
        with self._sessions() as session:
            rows = SqlSpecialPeriodRepository(session).in_range()
            return SpecialPeriodList(items=[_period_schema(r) for r in rows])

    def create_period(self, body: SpecialPeriodIn) -> SpecialPeriod:
        _check_period(body)
        now = self._clock()
        with self._sessions.begin() as session:
            row = SqlSpecialPeriodRepository(session).add(_period_row(PeriodRow(), body, now))
            result = _period_schema(row)
        self._recompute(_ms(body.start), None if body.end is None else _ms(body.end), "period_added")
        return result

    def update_period(self, period_id: str, body: SpecialPeriodIn) -> SpecialPeriod:
        _check_period(body)
        now = self._clock()
        with self._sessions.begin() as session:
            repo = SqlSpecialPeriodRepository(session)
            row = repo.get(_parse_period_id(period_id))
            if row is None:
                raise not_found("Periode", period_id)
            old_start = row.start_ts
            _period_row(row, body, now)
            repo.update(row, now)
            result = _period_schema(row)
        self._recompute(min(old_start, _ms(body.start)), None, "period_changed")
        return result

    def delete_period(self, period_id: str) -> None:
        with self._sessions.begin() as session:
            repo = SqlSpecialPeriodRepository(session)
            row = repo.get(_parse_period_id(period_id))
            if row is None:
                raise not_found("Periode", period_id)
            start = row.start_ts
            repo.delete(row.id)
        self._recompute(start, None, "period_removed")


def _signature(profile: ProfileRow) -> dict[str, Any]:
    """Content of a version without identity/time, to skip no-op saves."""
    return {
        "details": profile.details,
        "circuits": sorted((c.key, c.name, c.kind, c.emitter) for c in profile.circuits),
        "rooms": sorted(
            (r.key, r.name, r.circuit_key, r.has_thermostat) for r in profile.rooms
        ),
        "specs": sorted(
            (s.key, s.status, s.value_num, s.value_text, s.unit, s.note or "", s.change_id)
            for s in profile.specs
        ),
    }


def _check_period(body: SpecialPeriodIn) -> None:
    if body.end is not None and body.end <= body.start:
        raise ProblemError(422, "Ongeldige periode", "De eindtijd moet na de begintijd liggen.")


def _parse_period_id(period_id: str) -> int:
    match = _PERIOD_ID.match(period_id)
    if match is None:
        raise not_found("Periode", period_id)
    return int(match.group(1))


def _period_row(row: PeriodRow, body: SpecialPeriodIn, now: int) -> PeriodRow:
    row.kind = body.kind
    row.start_ts = _ms(body.start)
    row.end_ts = None if body.end is None else _ms(body.end)
    row.description = body.description or None
    row.exclude_from_baseline = body.excluded_from.normal_behaviour
    row.exclude_from_comparisons = body.excluded_from.comparisons
    row.exclude_from_ch_conclusions = body.excluded_from.ch_conclusions
    if row.id is None:
        row.created_at_ts = now
    row.updated_at_ts = now
    return row


def _period_schema(row: PeriodRow) -> SpecialPeriod:
    return SpecialPeriod(
        id=f"P-{row.id:03d}",
        kind=row.kind,
        start=_dt(row.start_ts),
        end=None if row.end_ts is None else _dt(row.end_ts),
        description=row.description or "",
        excluded_from=PeriodExclusions(
            normal_behaviour=row.exclude_from_baseline,
            comparisons=row.exclude_from_comparisons,
            ch_conclusions=row.exclude_from_ch_conclusions,
        ),
        created_at=_dt(row.created_at_ts),
    )
