"""Read measured cumulative gas-meter deltas without normalizing or allocating end uses."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from itertools import pairwise

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from cvidee.analysis.types import Role
from cvidee.api.schemas.common import TimeRange
from cvidee.api.schemas.consumption import (
    ConsumptionAvailability,
    ConsumptionEvent,
    ConsumptionEventKind,
    ConsumptionReason,
    ConsumptionResponse,
    ConsumptionSegment,
    GasMeterScope,
)
from cvidee.installation.specs import GAS_METER_SCOPE
from cvidee.runner.sources import MappedSignal, load_mapped_signals
from cvidee.settings.repository import effective_values
from cvidee.store.enums import SpecStatus
from cvidee.store.models import InstallationProfile, Observation, SettingsRevision, SourceEntity

_HOUR_MS = 3_600_000
_DAY_MS = 86_400_000


def _dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts / 1000, UTC)


class ConsumptionReadModel:
    """Read gas counters and their versioned meter/settings context from the database."""

    def __init__(
        self, sessions: sessionmaker[Session], clock: Callable[[], int] | None = None
    ) -> None:
        self._sessions = sessions
        self._clock = clock or (lambda: int(time.time() * 1000))

    def consumption(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> ConsumptionResponse:
        end = end or _dt(self._clock())
        start = start or end - timedelta(days=7)
        lo, hi = round(start.timestamp() * 1000), round(end.timestamp() * 1000)
        if lo >= hi or hi - lo > 366 * _DAY_MS:
            from cvidee.api.problems import ProblemError

            raise ProblemError(
                422,
                "Ongeldig tijdvak",
                "Kies een tijdvak van maximaal 366 dagen met begin vóór einde.",
            )
        with self._sessions() as session:
            return self._read(session, start, end, lo, hi)

    def _read(
        self, session: Session, start: datetime, end: datetime, lo: int, hi: int
    ) -> ConsumptionResponse:
        mappings = [
            mapping
            for mapping in load_mapped_signals(session)
            if mapping.signal.role is Role.GAS_CUMULATIVE
            and mapping.valid_from < hi
            and (mapping.valid_to is None or mapping.valid_to > lo)
        ]
        profile_rows = list(
            session.scalars(
                select(InstallationProfile)
                .where(
                    InstallationProfile.valid_from_ts < hi,
                    (InstallationProfile.valid_to_ts.is_(None))
                    | (InstallationProfile.valid_to_ts > lo),
                )
                .options(selectinload(InstallationProfile.specs))
                .order_by(InstallationProfile.valid_from_ts)
            )
        )
        scopes: list[GasMeterScope] = []
        for profile in profile_rows:
            spec = next((s for s in profile.specs if s.key == GAS_METER_SCOPE), None)
            value = (
                spec.value_text if spec is not None and spec.status is SpecStatus.KNOWN else None
            )
            try:
                scopes.append(GasMeterScope(value or GasMeterScope.UNKNOWN))
            except ValueError:
                scopes.append(GasMeterScope.UNKNOWN)
        scope = scopes[0] if scopes and len(set(scopes)) == 1 else GasMeterScope.UNKNOWN
        scope_changed = bool(scopes and len(set(scopes)) > 1)

        reasons: set[ConsumptionReason] = set()
        events: list[ConsumptionEvent] = []
        if not mappings:
            reasons.add(ConsumptionReason.NO_METER)
        if scope is GasMeterScope.UNKNOWN:
            reasons.add(ConsumptionReason.UNKNOWN_METER_SCOPE)
        if scope_changed:
            reasons.add(ConsumptionReason.PROFILE_SCOPE_CHANGED)

        entity_ids = {mapping.entity_id for mapping in mappings}
        entities = (
            {
                entity.entity_id: entity
                for entity in session.scalars(
                    select(SourceEntity).where(SourceEntity.entity_id.in_(entity_ids))
                )
            }
            if entity_ids
            else {}
        )
        mapping_by_entity: dict[str, list[MappedSignal]] = {}
        for mapping in mappings:
            mapping_by_entity.setdefault(mapping.entity_id, []).append(mapping)
        rows = (
            list(
                session.execute(
                    select(Observation, SourceEntity.entity_id)
                    .join(SourceEntity, SourceEntity.id == Observation.source_entity_id)
                    .where(
                        SourceEntity.entity_id.in_(entity_ids),
                        Observation.ts >= lo,
                        Observation.ts < hi,
                        Observation.value_num.is_not(None),
                    )
                    .order_by(Observation.ts, Observation.id)
                )
            )
            if entity_ids
            else []
        )
        readings: list[tuple[int, float, str, int, int, str | None]] = []
        unsupported_unit = False
        for observation, source_entity_id in rows:
            active_mapping = next(
                (
                    item
                    for item in mapping_by_entity[source_entity_id]
                    if item.valid_at(observation.ts)
                ),
                None,
            )
            if active_mapping is None or observation.value_num is None:
                continue
            entity = entities[source_entity_id]
            unit = active_mapping.unit or entity.unit
            if unit not in ("m³", "m3"):
                unsupported_unit = True
            readings.append(
                (
                    observation.ts,
                    float(observation.value_num),
                    source_entity_id,
                    int(active_mapping.mapping_id or 0),
                    int(active_mapping.max_age_ms),
                    unit,
                )
            )
        if unsupported_unit:
            reasons.add(ConsumptionReason.UNSUPPORTED_UNIT)

        settings_rows = list(
            session.scalars(
                select(SettingsRevision)
                .where(SettingsRevision.created_at_ts < hi)
                .order_by(SettingsRevision.created_at_ts, SettingsRevision.id)
            )
        )

        def settings_at(ts: int) -> tuple[int | None, float | None]:
            row = next((item for item in reversed(settings_rows) if item.created_at_ts <= ts), None)
            value = effective_values(row).gas_price_eur_per_m3
            return (None if row is None else row.id), value

        segments: list[ConsumptionSegment] = []
        covered: list[tuple[int, int]] = []
        total = 0.0
        all_costs_available = True
        cost_total = 0.0
        seen_entities: set[str] = set()
        seen_mappings: set[int] = set()
        for previous, current in pairwise(readings):
            prev_ts, prev_value, prev_entity, prev_mapping, max_age, prev_unit = previous
            curr_ts, curr_value, curr_entity, curr_mapping, curr_max_age, curr_unit = current
            if curr_ts <= prev_ts:
                continue
            if prev_entity != curr_entity or prev_mapping != curr_mapping:
                reasons.add(ConsumptionReason.MAPPING_CHANGED)
                events.append(
                    ConsumptionEvent(
                        kind=ConsumptionEventKind.MAPPING_CHANGED,
                        start=_dt(prev_ts),
                        end=_dt(curr_ts),
                        detail="De gasmeterkoppeling is gewijzigd; dit interval is niet opgeteld.",
                    )
                )
                continue
            gap_ms = curr_ts - prev_ts
            if gap_ms > max(max_age, curr_max_age, _HOUR_MS):
                reasons.add(ConsumptionReason.DATA_GAP)
                events.append(
                    ConsumptionEvent(
                        kind=ConsumptionEventKind.DATA_GAP,
                        start=_dt(prev_ts),
                        end=_dt(curr_ts),
                        detail=(
                            "Tussen deze tellerstanden zit een datagat; "
                            "het interval is niet opgeteld."
                        ),
                    )
                )
                continue
            if curr_value < prev_value:
                reasons.add(ConsumptionReason.COUNTER_RESET)
                events.append(
                    ConsumptionEvent(
                        kind=ConsumptionEventKind.COUNTER_RESET,
                        start=_dt(prev_ts),
                        end=_dt(curr_ts),
                        detail=(
                            "De tellerstand is gedaald; de overgang is uitgesloten van "
                            "verbruik en dekking."
                        ),
                    )
                )
                continue
            if prev_unit not in ("m³", "m3") or curr_unit not in ("m³", "m3"):
                continue
            delta = curr_value - prev_value
            settings_revision, price = settings_at(prev_ts)
            changed_during_interval = any(
                prev_ts < row.created_at_ts < curr_ts for row in settings_rows
            )
            segment_cost = (
                None if price is None or changed_during_interval else round(delta * price, 4)
            )
            if segment_cost is None:
                all_costs_available = False
            else:
                cost_total += segment_cost
            segments.append(
                ConsumptionSegment(
                    start=_dt(prev_ts),
                    end=_dt(curr_ts),
                    start_reading=prev_value,
                    end_reading=curr_value,
                    consumption_m3=delta,
                    meter_entity_id=curr_entity,
                    mapping_revision=curr_mapping,
                    settings_revision=settings_revision,
                    gas_price_eur_per_m3=price,
                    cost_eur=segment_cost,
                )
            )
            covered.append((prev_ts, curr_ts))
            total += delta
            seen_entities.add(curr_entity)
            seen_mappings.add(curr_mapping)

        if readings and readings[0][0] > lo:
            reasons.add(ConsumptionReason.DATA_GAP)
            events.append(
                ConsumptionEvent(
                    kind=ConsumptionEventKind.DATA_GAP,
                    start=_dt(lo),
                    end=_dt(readings[0][0]),
                    detail="Voor de eerste tellerstand in dit tijdvak ontbreekt meetdekking.",
                )
            )
        if readings and readings[-1][0] < hi - 1:
            reasons.add(ConsumptionReason.DATA_GAP)
            events.append(
                ConsumptionEvent(
                    kind=ConsumptionEventKind.DATA_GAP,
                    start=_dt(readings[-1][0]),
                    end=_dt(hi),
                    detail="Na de laatste tellerstand in dit tijdvak ontbreekt meetdekking.",
                )
            )
        if mappings and not readings:
            reasons.add(ConsumptionReason.DATA_GAP)
            events.append(
                ConsumptionEvent(
                    kind=ConsumptionEventKind.DATA_GAP,
                    start=_dt(lo),
                    end=_dt(hi),
                    detail="In dit tijdvak zijn geen numerieke tellerstanden opgeslagen.",
                )
            )
        if len(seen_entities) > 1 or len(seen_mappings) > 1:
            reasons.add(ConsumptionReason.MAPPING_CHANGED)
            total_value: float | None = None
        else:
            total_value = total if segments else None
        if not segments:
            reasons.add(ConsumptionReason.NO_VALID_INTERVALS)
        if not readings and mappings:
            reasons.add(ConsumptionReason.NO_VALID_INTERVALS)
        covered_ms = sum(right - left for left, right in covered)
        coverage = min(100.0, 100.0 * covered_ms / (hi - lo)) if mappings else None
        if (
            reasons
            & {
                ConsumptionReason.DATA_GAP,
                ConsumptionReason.COUNTER_RESET,
                ConsumptionReason.MAPPING_CHANGED,
                ConsumptionReason.PROFILE_SCOPE_CHANGED,
                ConsumptionReason.UNSUPPORTED_UNIT,
            }
            and segments
        ):
            availability = ConsumptionAvailability.LIMITED
        elif not segments:
            availability = ConsumptionAvailability.UNAVAILABLE
        elif scope is GasMeterScope.UNKNOWN:
            availability = ConsumptionAvailability.LIMITED
        else:
            availability = ConsumptionAvailability.AVAILABLE
        complete = (
            coverage is not None
            and coverage >= 100.0
            and availability is ConsumptionAvailability.AVAILABLE
        )
        cost = round(cost_total, 2) if complete and all_costs_available else None
        meter_entity_id = next(iter(seen_entities)) if len(seen_entities) == 1 else None
        has_reset = ConsumptionReason.COUNTER_RESET in reasons
        start_reading = segments[0].start_reading if segments and not has_reset else None
        end_reading = segments[-1].end_reading if segments and not has_reset else None
        unit = next((reading[5] for reading in readings if reading[5]), None)
        return ConsumptionResponse(
            range=TimeRange(start=start, end=end),
            availability=availability,
            reasons=sorted(reasons, key=lambda reason: reason.value),
            meter_scope=scope,
            meter_entity_id=meter_entity_id,
            unit=unit,
            coverage_pct=round(coverage, 2) if coverage is not None else None,
            counter_start=start_reading,
            counter_end=end_reading,
            consumption_m3=round(total_value, 3) if total_value is not None else None,
            cost_eur=cost,
            segments=segments,
            events=events,
        )
