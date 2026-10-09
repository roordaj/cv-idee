"""In-memory stub backend: design-v3 data plus state for the mutating routes.

One :class:`StubStore` lives on ``app.state`` while ``CVIDEE_STUB_DATA=1``. The clock is
frozen at :data:`~cvidee.api.stubs.fixtures.NOW` so responses are deterministic.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

from cvidee.api.problems import ProblemError, not_found
from cvidee.api.schemas.changes import Change, ChangeCreate, ChangeEvaluation, ChangeList
from cvidee.api.schemas.common import Page, TimeRange
from cvidee.api.schemas.data import (
    ChangeMarker,
    ChangeRef,
    CycleList,
    ImportJob,
    ImportList,
    ImportRequest,
    ImportSignalProgress,
    PeriodBand,
    QualityResponse,
    SpecialPeriod,
    SpecialPeriodIn,
    SpecialPeriodList,
    TimelineResponse,
)
from cvidee.api.schemas.findings import (
    FindingDetail,
    FindingList,
    FindingNote,
    FindingNoteCreate,
    FindingStatusUpdate,
    FindingSummary,
    HistoryEntry,
)
from cvidee.api.schemas.installation import InstallationProfile, InstallationProfileIn
from cvidee.api.schemas.notifications import (
    HaExport,
    Notification,
    NotificationPolicy,
    NotificationPolicyIn,
)
from cvidee.api.schemas.settings import AnalysisSettings, SettingsIn, SettingsResponse
from cvidee.api.schemas.signals import (
    AnalysisList,
    Signal,
    SignalList,
    SignalMappingUpdate,
    SignalState,
)
from cvidee.api.schemas.system import (
    FindingsOverview,
    HaConnectionState,
    HaStatus,
    LiveState,
    LiveStatus,
    MqttStatus,
    OverviewResponse,
    SetupState,
    ShellCounts,
    StatusResponse,
    TodaySummary,
)
from cvidee.api.stubs import fixtures as fx
from cvidee.api.stubs.sim import GAP, at, build_sim
from cvidee.store.enums import (
    EvaluationVerdict,
    ImportStatus,
    Mode,
    RecommendationStatus,
    Severity,
)

_OPEN = (RecommendationStatus.OPEN, RecommendationStatus.ROLLBACK_TRIGGERED)
_ACTIVE_IMPORT = (ImportStatus.PENDING, ImportStatus.FETCHING, ImportStatus.ANALYSING)


def _revision(values: AnalysisSettings) -> str:
    payload = json.dumps(values.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def _summary(f: FindingDetail) -> FindingSummary:
    return FindingSummary.model_validate(f.model_dump(include=set(FindingSummary.model_fields)))


def _overlaps(a: TimeRange, start: datetime, end: datetime) -> bool:
    return a.start < end and (a.end is None or a.end > start)


class StubStore:
    """Design-v3 example data with in-memory state."""

    def __init__(self) -> None:
        self.now = fx.NOW
        self.findings = {f.id: f for f in fx.findings()}
        self.signals = {s.id: s for s in fx.signals()}
        self._entities = {s.entity_id: s for s in self.signals.values() if s.entity_id}
        self.periods = {p.id: p for p in fx.periods()}
        self.changes = fx.changes()
        self.evaluations = fx.evaluations()
        self.installation = fx.installation()
        self.policy = fx.notification_policy()
        self.settings_values = AnalysisSettings()
        self.settings_updated_at = fx.local(2026, 9, 24, 12, 0)
        self.onboarding_completed_at: datetime | None = fx.local(2026, 8, 14, 9, 0)
        self.imports: dict[str, ImportJob] = {}
        done = fx.finished_import()
        self.imports[done.id] = done
        self._seq = {"period": len(self.periods), "change": 8, "note": 0, "import": 1}

    def _next(self, kind: str, prefix: str, width: int = 3) -> str:
        self._seq[kind] += 1
        return f"{prefix}-{self._seq[kind]:0{width}d}"

    # --- status and overview ---------------------------------------------------------

    def open_findings(self) -> int:
        return sum(1 for f in self.findings.values() if f.status in _OPEN)

    def active_import(self) -> ImportJob | None:
        return next((j for j in self.imports.values() if j.status in _ACTIVE_IMPORT), None)

    def setup(self) -> SetupState:
        flame = self.signals[fx.FLAME].entity_id is not None
        imported = any(j.status is ImportStatus.DONE for j in self.imports.values())
        return SetupState(
            onboarding_done=self.onboarding_completed_at is not None,
            onboarding_completed_at=self.onboarding_completed_at,
            flame_mapped=flame,
            history_imported=imported,
            steps_done=1 + int(flame) + int(imported),
        )

    def status(self) -> StatusResponse:
        job = self.active_import()
        if job is None:
            live = LiveStatus(state=LiveState.LIVE, last_data_at=self.now)
        else:
            live = LiveStatus(
                state=LiveState.IMPORTING,
                last_data_at=self.now,
                since=job.started_at,
                progress_pct=round(job.blocks_done / job.blocks_total * 100, 1),
            )
        linked = sum(1 for s in self.signals.values() if s.entity_id)
        return StatusResponse(
            now=self.now,
            stub_data=True,
            live=live,
            source_text=fx.SOURCE_TEXT,
            operating_mode=Mode.STANDBY,
            operating_mode_since=at(320),
            coverage_today_pct=fx.TODAY_COVERAGE_PCT,
            counts=ShellCounts(
                open_findings=self.open_findings(),
                signals_linked=linked,
                signals_total=len(self.signals),
            ),
            setup=self.setup(),
            ha=HaStatus(
                state=HaConnectionState.CONNECTED,
                deployment="addon",
                version="2026.10.0",
                entity_count=len(self._entities),
                since=fx.local(2026, 10, 4, 6, 0),
            ),
            mqtt=MqttStatus(broker_found=True, connected=True, export_mode="mqtt"),
            active_import_id=None if job is None else job.id,
        )

    def overview(self) -> OverviewResponse:
        st = build_sim().stats
        items = [_summary(f) for f in self.findings.values()]
        action_required = sum(
            1
            for f in self.findings.values()
            if f.status is RecommendationStatus.ROLLBACK_TRIGGERED
            or (f.severity is Severity.HIGH and f.status is RecommendationStatus.OPEN)
        )
        return OverviewResponse(
            window=fx.WINDOW,
            assessment=fx.assessment(),
            setup=self.setup(),
            status_card=fx.status_card(),
            today=TodaySummary(
                range=fx.WINDOW, ch_cycles=st.ch_cycles, short_during_demand=st.short_cycles
            ),
            next_action=fx.next_action(),
            kpis=fx.kpis(),
            findings=FindingsOverview(
                open_count=self.open_findings(),
                action_required_count=action_required,
                items=items,
            ),
            data_quality=fx.data_quality(),
            analyses=fx.analyses(),
        )

    # --- signals, HA entities, analyses ----------------------------------------------

    def signal_list(self) -> SignalList:
        items = list(self.signals.values())
        return SignalList(
            items=items, linked=sum(1 for s in items if s.entity_id), total=len(items)
        )

    def update_signal(self, signal_id: str, update: SignalMappingUpdate) -> Signal:
        current = self.signals.get(signal_id)
        if current is None:
            raise not_found("Signaal", signal_id)
        if update.entity_id is not None and update.entity_id not in self._entities:
            raise ProblemError(
                422,
                "Onbekende entiteit",
                f"Home Assistant kent geen entiteit '{update.entity_id}'.",
            )
        changes = update.model_dump(exclude_unset=True)
        if update.entity_id is None:
            changes |= {
                "state": SignalState.MISSING,
                "age_s": None,
                "median_update_interval_s": None,
            }
        else:
            source = self._entities[update.entity_id]
            changes |= {"state": source.state, "age_s": source.age_s}
        updated = current.model_copy(update=changes)
        self.signals[signal_id] = Signal.model_validate(updated.model_dump())
        return self.signals[signal_id]

    def analyses(self) -> AnalysisList:
        return AnalysisList(items=fx.analyses())

    # --- installation and special periods --------------------------------------------

    def installation_profile(self) -> InstallationProfile:
        return self.installation

    def put_installation(self, body: InstallationProfileIn) -> InstallationProfile:
        if body.revision != self.installation.revision:
            raise ProblemError(
                409,
                "Installatieprofiel is intussen gewijzigd",
                "Herlaad om de nieuwste gegevens te zien.",
            )
        data = body.model_dump() | {
            "revision": body.revision + 1,
            "updated_at": self.now,
            "summary": self.installation.summary,
        }
        self.installation = InstallationProfile.model_validate(data)
        return self.installation

    @staticmethod
    def _check_period(body: SpecialPeriodIn) -> None:
        if body.end is not None and body.end <= body.start:
            raise ProblemError(422, "Ongeldige periode", "De eindtijd moet na de begintijd liggen.")

    def period_list(self) -> SpecialPeriodList:
        return SpecialPeriodList(items=sorted(self.periods.values(), key=lambda p: p.start))

    def create_period(self, body: SpecialPeriodIn) -> SpecialPeriod:
        self._check_period(body)
        period = SpecialPeriod(
            id=self._next("period", "P"), created_at=self.now, **body.model_dump()
        )
        self.periods[period.id] = period
        return period

    def update_period(self, period_id: str, body: SpecialPeriodIn) -> SpecialPeriod:
        current = self.periods.get(period_id)
        if current is None:
            raise not_found("Periode", period_id)
        self._check_period(body)
        updated = SpecialPeriod(id=period_id, created_at=current.created_at, **body.model_dump())
        self.periods[period_id] = updated
        return updated

    def delete_period(self, period_id: str) -> None:
        if self.periods.pop(period_id, None) is None:
            raise not_found("Periode", period_id)

    # --- quality, timeline, cycles ---------------------------------------------------

    def quality(self) -> QualityResponse:
        return QualityResponse(
            range=fx.QUALITY_RANGE,
            core_coverage_pct=96.8,
            coverage=fx.coverage(),
            events=fx.quality_events(),
            mode_share_range=fx.WINDOW,
            mode_share=fx.mode_share(),
            flame_resolution_s=4,
            flame_resolution_text="Resolutie vlamstatus: 4 s. Ruim voldoende om cycli korter "
            "dan 3 min betrouwbaar te detecteren.",
        )

    def timeline(self) -> TimelineResponse:
        start, end = fx.WINDOW.start, fx.WINDOW.end or self.now
        inside = [c for c in self.changes if start <= c.at < end]
        before = sorted((c for c in self.changes if c.at < start), key=lambda c: c.at)
        return TimelineResponse(
            range=fx.WINDOW,
            series=fx.series(),
            modes=fx.mode_segments(),
            heat_demand=fx.demand_segments(),
            cycles=fx.cycles(),
            gaps=[TimeRange(start=at(GAP[0]), end=at(GAP[1]))],
            changes=[
                ChangeMarker(
                    id=c.id,
                    at=c.at,
                    parameter=c.parameter,
                    old_value=c.old_value,
                    new_value=c.new_value,
                    actor=c.actor.value,
                    verdict=c.verdict,
                    verdict_text=c.verdict_text,
                )
                for c in sorted(inside, key=lambda c: c.at)
            ],
            last_change_before=(
                ChangeRef(id=before[-1].id, at=before[-1].at, parameter=before[-1].parameter)
                if before
                else None
            ),
            periods=[
                PeriodBand(id=p.id, kind=p.kind, start=p.start, end=p.end)
                for p in self.periods.values()
                if _overlaps(TimeRange(start=p.start, end=p.end), start, end)
            ],
        )

    def cycles(self, limit: int, offset: int) -> CycleList:
        items = fx.cycles()
        return CycleList(
            range=fx.WINDOW,
            summary=fx.cycle_summary(),
            items=items[offset : offset + limit],
            total=len(items),
            limit=limit,
            offset=offset,
        )

    # --- findings and history --------------------------------------------------------

    def finding_list(self) -> FindingList:
        return FindingList(
            items=[_summary(f) for f in self.findings.values()],
            open_count=self.open_findings(),
        )

    def finding(self, finding_id: str) -> FindingDetail:
        found = self.findings.get(finding_id)
        if found is None:
            raise not_found("Bevinding", finding_id)
        return found

    def set_finding_status(self, finding_id: str, body: FindingStatusUpdate) -> FindingDetail:
        current = self.finding(finding_id)
        status = RecommendationStatus(body.status)
        until = None
        if status is RecommendationStatus.POSTPONED:
            until = body.postponed_until or self.now + timedelta(
                days=self.settings_values.postpone_days
            )
            if until <= self.now:
                raise ProblemError(422, "Ongeldige datum", "Uitstellen kan alleen tot later.")
        updated = current.model_copy(
            update={
                "status": status,
                "postponed_until": until,
                "status_text": fx.status_text(status, until),
            }
        )
        self.findings[finding_id] = updated
        return updated

    def add_note(self, finding_id: str, body: FindingNoteCreate) -> FindingNote:
        current = self.finding(finding_id)
        note = FindingNote(id=self._next("note", "N"), text=body.text, created_at=self.now)
        self.findings[finding_id] = current.model_copy(update={"notes": [*current.notes, note]})
        return note

    def history(self, limit: int, offset: int) -> Page[HistoryEntry]:
        items = fx.history()
        return Page[HistoryEntry](
            items=items[offset : offset + limit], total=len(items), limit=limit, offset=offset
        )

    # --- changes ---------------------------------------------------------------------

    def change_list(self) -> ChangeList:
        return ChangeList(items=sorted(self.changes, key=lambda c: c.at, reverse=True))

    def create_change(self, body: ChangeCreate) -> Change:
        if body.finding_id is not None and body.finding_id not in self.findings:
            raise not_found("Bevinding", body.finding_id)
        change = Change(
            id=self._next("change", "W", 2),
            verdict=EvaluationVerdict.PENDING,
            verdict_text="Evaluatie loopt",
            rollback_advised=False,
            **body.model_dump(),
        )
        self.changes.append(change)
        days = self.settings_values.comparison_days
        due = change.at + timedelta(days=days)
        self.evaluations[change.id] = ChangeEvaluation(
            change_id=change.id,
            verdict=EvaluationVerdict.PENDING,
            verdict_text="Evaluatie loopt",
            summary=f"Evaluatie loopt — resultaat na {fx.day_month(due)} ({days} dagen na de "
            "wijziging).",
            before=TimeRange(start=change.at - timedelta(days=days), end=change.at),
            after=TimeRange(start=change.at, end=change.at + timedelta(days=days)),
            before_text="",
            after_text="",
            conditions=[],
            metrics=[],
            result_expected_at=due,
        )
        return change

    def evaluation(self, change_id: str) -> ChangeEvaluation:
        found = self.evaluations.get(change_id)
        if found is None:
            raise not_found("Wijziging", change_id)
        return found

    # --- notifications and export ----------------------------------------------------

    def put_policy(self, body: NotificationPolicyIn) -> NotificationPolicy:
        self.policy = NotificationPolicy(
            recovery_text=self.policy.recovery_text, **body.model_dump()
        )
        return self.policy

    def notifications(self, limit: int, offset: int) -> Page[Notification]:
        items = fx.notifications()
        return Page[Notification](
            items=items[offset : offset + limit], total=len(items), limit=limit, offset=offset
        )

    def ha_export(self) -> HaExport:
        return HaExport(
            transport="mqtt",
            connected=True,
            updated_at=self.now,
            entities=fx.ha_export(self.open_findings()),
        )

    # --- import ----------------------------------------------------------------------

    def import_list(self) -> ImportList:
        items = sorted(self.imports.values(), key=lambda j: j.started_at, reverse=True)
        return ImportList(items=items, earliest_available_at=fx.EARLIEST_AVAILABLE)

    def start_import(self, body: ImportRequest) -> ImportJob:
        if body.end <= body.start:
            raise ProblemError(422, "Ongeldige periode", "'from' moet vóór 'to' liggen.")
        if body.end > self.now:
            raise ProblemError(422, "Ongeldige periode", "'to' mag niet in de toekomst liggen.")
        if self.active_import() is not None:
            raise ProblemError(409, "Er loopt al een import", "Maximaal één import tegelijk.")
        mapped = [s.id for s in self.signals.values() if s.entity_id]
        chosen = body.signal_ids if body.signal_ids is not None else mapped
        unknown = sorted(set(chosen) - set(mapped))
        if unknown:
            raise ProblemError(422, "Onbekend signaal", f"Niet gekoppeld: {', '.join(unknown)}.")
        start = max(body.start, fx.EARLIEST_AVAILABLE)
        days = fx.import_days(start, body.end)
        job = ImportJob(
            id=self._next("import", "I"),
            status=ImportStatus.PENDING,
            range=TimeRange(start=start, end=body.end),
            blocks_done=0,
            blocks_total=len(days),
            current_block_day=days[0],
            observations_imported=0,
            duplicates_skipped=0,
            signals=[
                ImportSignalProgress(signal_id=sid, observations=0, first_at=None) for sid in chosen
            ],
            earliest_available_at=fx.EARLIEST_AVAILABLE,
            cycles_found=None,
            coverage_pct=None,
            warnings=[],
            errors=[],
            started_at=self.now,
            finished_at=None,
        )
        self.imports[job.id] = job
        return job

    def poll_import(self, import_id: str) -> ImportJob:
        """Return the job; every poll of an active job advances it one step."""
        job = self.imports.get(import_id)
        if job is None:
            raise not_found("Import", import_id)
        if job.status not in _ACTIVE_IMPORT:
            return job
        update: dict[str, object]
        if job.blocks_done < job.blocks_total:
            done = job.blocks_done + 1
            days = fx.import_days(job.range.start, job.range.end or self.now)
            per_signal = 14_188 // max(len(job.signals), 1)
            update = {
                "status": ImportStatus.FETCHING,
                "blocks_done": done,
                "current_block_day": days[min(done, len(days) - 1)],
                "observations_imported": done * 14_188,
                "duplicates_skipped": done * 130,
                "signals": [
                    s.model_copy(
                        update={"observations": done * per_signal, "first_at": job.range.start}
                    )
                    for s in job.signals
                ],
                "eta_s": float((job.blocks_total - done) * 20) if done >= 2 else None,
            }
            if done == job.blocks_total:
                update |= {"status": ImportStatus.ANALYSING, "eta_s": None}
        else:
            update = {
                "status": ImportStatus.DONE,
                "current_block_day": None,
                "cycles_found": job.blocks_total * 121,
                "coverage_pct": 97.4,
                "finished_at": self.now,
            }
        self.imports[import_id] = job.model_copy(update=update)
        return self.imports[import_id]

    def cancel_import(self, import_id: str) -> ImportJob:
        job = self.imports.get(import_id)
        if job is None:
            raise not_found("Import", import_id)
        if job.status not in _ACTIVE_IMPORT:
            raise ProblemError(409, "Import loopt niet", "Alleen een lopende import kan stoppen.")
        stopped = job.model_copy(
            update={"status": ImportStatus.CANCELLED, "finished_at": self.now, "eta_s": None}
        )
        self.imports[import_id] = stopped
        return stopped

    # --- settings --------------------------------------------------------------------

    def settings(self, *, recompute_started: bool = False) -> SettingsResponse:
        return SettingsResponse(
            revision=_revision(self.settings_values),
            updated_at=self.settings_updated_at,
            values=self.settings_values,
            onboarding_completed_at=self.onboarding_completed_at,
            recompute_started=recompute_started,
            json_schema=AnalysisSettings.model_json_schema(),
        )

    def put_settings(self, body: SettingsIn) -> SettingsResponse:
        if body.revision != _revision(self.settings_values):
            raise ProblemError(
                409,
                "Instellingen zijn intussen gewijzigd",
                "Sinds je deze pagina opende zijn de instellingen opgeslagen vanaf een ander "
                "venster. Herlaad om de nieuwste waarden te zien.",
            )
        changed = body.values != self.settings_values
        self.settings_values = body.values
        if "onboarding_completed_at" in body.model_fields_set:
            self.onboarding_completed_at = body.onboarding_completed_at
        if changed:
            self.settings_updated_at = self.now
        return self.settings(recompute_started=changed)
