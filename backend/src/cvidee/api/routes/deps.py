"""Shared route dependencies and query parameters."""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import datetime
from typing import Annotated, Protocol

from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session, sessionmaker

from cvidee.analysis.types import MetricName
from cvidee.api.config_backend import ConfigBackend
from cvidee.api.findings_read import FindingsReadModel
from cvidee.api.problems import ProblemError
from cvidee.api.schemas.changes import Change, ChangeCreate, ChangeEvaluation, ChangeList
from cvidee.api.schemas.common import Page, UtcDateTime
from cvidee.api.schemas.consumption import (
    ConsumptionCandidatesResponse,
    ConsumptionComparisonRequest,
    ConsumptionComparisonResponse,
    ConsumptionResponse,
)
from cvidee.api.schemas.data import (
    CycleList,
    ImportJob,
    ImportList,
    ImportRequest,
    QualityResponse,
    SpecialPeriod,
    SpecialPeriodIn,
    SpecialPeriodList,
    TimelineResponse,
)
from cvidee.api.schemas.experiments import ExperimentCreate, ExperimentList, ExperimentOut
from cvidee.api.schemas.findings import (
    FindingDetail,
    FindingList,
    FindingNote,
    FindingNoteCreate,
    FindingStatusUpdate,
    HistoryEntry,
)
from cvidee.api.schemas.installation import InstallationProfile, InstallationProfileIn
from cvidee.api.schemas.normal_behavior import (
    NormalBehaviorModelList,
    NormalBehaviorModelOut,
    NormalBehaviorNewVersion,
    NormalBehaviorReason,
)
from cvidee.api.schemas.notifications import Notification, NotificationPolicy, NotificationPolicyIn
from cvidee.api.schemas.system import OverviewResponse, StatusResponse
from cvidee.api.stubs.store import StubStore


def get_stub_store_problem() -> ProblemError:
    return ProblemError(
        501,
        "Nog niet geïmplementeerd",
        "Deze route heeft nog geen implementatie. Start de backend met "
        "CVIDEE_STUB_DATA=1 voor voorbeeldgegevens.",
    )


def get_stub_store(request: Request) -> StubStore:
    """The stub backend, or ``501`` while the real implementation does not exist yet."""
    store: StubStore | None = getattr(request.app.state, "stub_store", None)
    if store is None:
        raise ProblemError(
            501,
            "Nog niet geïmplementeerd",
            "Deze route heeft nog geen implementatie. Start de backend met "
            "CVIDEE_STUB_DATA=1 voor voorbeeldgegevens.",
        )
    return store


class FindingsBackend(Protocol):
    """Read side of the findings routes: the database, or the stub with CVIDEE_STUB_DATA."""

    def finding_list(self) -> FindingList: ...

    def finding(self, finding_id: str) -> FindingDetail: ...

    def set_finding_status(self, finding_id: str, body: FindingStatusUpdate) -> FindingDetail: ...

    def add_note(self, finding_id: str, body: FindingNoteCreate) -> FindingNote: ...


def get_findings(request: Request) -> Iterator[FindingsBackend]:
    stub: StubStore | None = getattr(request.app.state, "stub_store", None)
    if stub is not None:
        yield stub
        return
    factory: sessionmaker[Session] | None = getattr(request.app.state, "session_factory", None)
    if factory is None:
        get_stub_store(request)  # raises the 501 problem
        return
    with factory.begin() as session:
        yield FindingsReadModel(session, lambda: int(time.time() * 1000))


class ConfigBackendProtocol(Protocol):
    """Installation profile and special periods: the database, or the stub."""

    def installation_profile(self) -> InstallationProfile: ...

    def put_installation(self, body: InstallationProfileIn) -> InstallationProfile: ...

    def period_list(self) -> SpecialPeriodList: ...

    def create_period(self, body: SpecialPeriodIn) -> SpecialPeriod: ...

    def update_period(self, period_id: str, body: SpecialPeriodIn) -> SpecialPeriod: ...

    def delete_period(self, period_id: str) -> None: ...


def get_config(request: Request) -> ConfigBackendProtocol:
    stub: StubStore | None = getattr(request.app.state, "stub_store", None)
    if stub is not None:
        return stub
    factory: sessionmaker[Session] | None = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise get_stub_store_problem()
    return ConfigBackend(factory, getattr(request.app.state, "runner", None))


Config = Annotated[ConfigBackendProtocol, Depends(get_config)]
Findings = Annotated[FindingsBackend, Depends(get_findings)]
Store = Annotated[StubStore, Depends(get_stub_store)]
From = Annotated[
    UtcDateTime | None, Query(alias="from", description="Start (ISO 8601); default: latest.")
]
To = Annotated[UtcDateTime | None, Query(alias="to", description="End (ISO 8601); default: now.")]
Limit = Annotated[int, Query(ge=1, le=500, description="Page size.")]
Offset = Annotated[int, Query(ge=0, description="Items to skip.")]
CandidateFrom = Annotated[UtcDateTime, Query(alias="from", description="Observation start.")]
CandidateTo = Annotated[UtcDateTime, Query(alias="to", description="Observation end.")]
CandidateLimit = Annotated[int, Query(ge=1, le=100, description="Maximum historical periods.")]
CandidateOffset = Annotated[int, Query(ge=0, description="Historical periods to skip.")]


class HistoryBackend(Protocol):
    def history(self, limit: int, offset: int) -> Page[HistoryEntry]: ...


def get_history(request: Request) -> Iterator[HistoryBackend]:
    from cvidee.findings.history import HistoryReadModel
    from cvidee.rules.registry import default_registry

    stub: StubStore | None = getattr(request.app.state, "stub_store", None)
    if stub is not None:
        yield stub
        return
    factory: sessionmaker[Session] | None = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise get_stub_store_problem()
    runner = getattr(request.app.state, "runner", None)
    registry = default_registry() if runner is None else runner.registry
    with factory() as session:
        yield HistoryReadModel(session, registry)


History = Annotated[HistoryBackend, Depends(get_history)]


class ChangesBackend(Protocol):
    def change_list(self) -> ChangeList: ...
    def create_change(self, body: ChangeCreate) -> Change: ...
    def evaluation(self, change_id: str) -> ChangeEvaluation: ...


def get_changes(request: Request) -> Iterator[ChangesBackend]:
    from cvidee.changes.log import ChangeLog

    stub: StubStore | None = getattr(request.app.state, "stub_store", None)
    if stub is not None:
        yield stub
        return
    factory: sessionmaker[Session] | None = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise get_stub_store_problem()
    with factory.begin() as session:
        yield ChangeLog(session, lambda: int(time.time() * 1000))


class TimelineBackend(Protocol):
    def timeline(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> TimelineResponse: ...


def get_timeline(request: Request) -> Iterator[TimelineBackend]:
    from cvidee.api.timeline_read import TimelineReadModel

    stub: StubStore | None = getattr(request.app.state, "stub_store", None)
    if stub is not None:
        yield stub
        return
    factory: sessionmaker[Session] | None = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise get_stub_store_problem()
    with factory() as session:
        yield TimelineReadModel(session, lambda: int(time.time() * 1000))


Changes = Annotated[ChangesBackend, Depends(get_changes)]


class ExperimentsBackend(Protocol):
    def list(self, limit: int, offset: int) -> ExperimentList: ...
    def get(self, change_id: str) -> ExperimentOut: ...
    def create(self, body: ExperimentCreate) -> ExperimentOut: ...
    def end(self, change_id: str) -> ExperimentOut: ...


def get_experiments(request: Request) -> Iterator[ExperimentsBackend]:
    from cvidee.experiments.backend import ExperimentBackend

    stub: StubStore | None = getattr(request.app.state, "stub_store", None)
    if stub is not None:
        yield stub
        return
    factory: sessionmaker[Session] | None = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise get_stub_store_problem()
    with factory.begin() as session:
        yield ExperimentBackend(session, lambda: int(time.time() * 1000))


Experiments = Annotated[ExperimentsBackend, Depends(get_experiments)]
Timeline = Annotated[TimelineBackend, Depends(get_timeline)]


class NormalBehaviorBackendProtocol(Protocol):
    def list(self, limit: int, offset: int) -> NormalBehaviorModelList: ...

    def pause(
        self, metric_name: MetricName, body: NormalBehaviorReason
    ) -> NormalBehaviorModelOut: ...

    def resume(self, metric_name: MetricName) -> NormalBehaviorModelOut: ...

    def start_version(
        self, metric_name: MetricName, body: NormalBehaviorNewVersion
    ) -> NormalBehaviorModelOut: ...


def get_normal_behavior(request: Request) -> Iterator[NormalBehaviorBackendProtocol]:
    from cvidee.normal_behavior.backend import NormalBehaviorBackend

    if getattr(request.app.state, "stub_store", None) is not None:
        raise get_stub_store_problem()
    factory: sessionmaker[Session] | None = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise get_stub_store_problem()
    with factory.begin() as session:
        yield NormalBehaviorBackend(session, lambda: int(time.time() * 1000))


NormalBehavior = Annotated[NormalBehaviorBackendProtocol, Depends(get_normal_behavior)]


class ImportsBackend(Protocol):
    def import_list(self) -> ImportList: ...
    def start_import(self, body: ImportRequest) -> ImportJob: ...
    def poll_import(self, ident: str) -> ImportJob: ...
    def cancel_import(self, ident: str) -> ImportJob: ...


def get_imports(request: Request) -> ImportsBackend:
    from cvidee.ingest.history_import import HistoryImport
    from cvidee.runner.service import AnalysisRunner

    stub: StubStore | None = getattr(request.app.state, "stub_store", None)
    if stub is not None:
        return stub
    service: HistoryImport | None = getattr(request.app.state, "history_import", None)
    if service is None:
        factory: sessionmaker[Session] | None = getattr(request.app.state, "session_factory", None)
        if factory is None:
            raise get_stub_store_problem()
        service = HistoryImport(
            factory,
            getattr(request.app.state, "ha_client", None),
            getattr(request.app.state, "runner", None) or AnalysisRunner(factory),
        )
        request.app.state.history_import = service
    return service


Imports = Annotated[ImportsBackend, Depends(get_imports)]


class NotificationsBackend(Protocol):
    @property
    def policy(self) -> NotificationPolicy: ...
    def put_policy(self, body: NotificationPolicyIn) -> NotificationPolicy: ...
    def notifications(self, limit: int, offset: int) -> Page[Notification]: ...


def get_notifications(request: Request) -> NotificationsBackend:
    from cvidee.notify.backend import NotificationBackend

    stub: StubStore | None = getattr(request.app.state, "stub_store", None)
    if stub is not None:
        return stub
    factory: sessionmaker[Session] | None = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise get_stub_store_problem()
    return NotificationBackend(factory)


Notifications = Annotated[NotificationsBackend, Depends(get_notifications)]


class MonitoringBackend(Protocol):
    def status(self) -> StatusResponse: ...
    def overview(self) -> OverviewResponse: ...
    def quality(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> QualityResponse: ...
    def cycles(
        self, limit: int, offset: int, start: datetime | None = None, end: datetime | None = None
    ) -> CycleList: ...


class ConsumptionBackend(Protocol):
    def consumption(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> ConsumptionResponse: ...


def get_consumption(request: Request) -> ConsumptionBackend:
    from cvidee.api.consumption_read import ConsumptionReadModel

    stub: StubStore | None = getattr(request.app.state, "stub_store", None)
    if stub is not None:
        return stub
    factory: sessionmaker[Session] | None = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise get_stub_store_problem()
    return ConsumptionReadModel(factory)


class ConsumptionComparisonBackend(Protocol):
    def candidates(
        self, start: datetime, end: datetime, limit: int = 30, offset: int = 0
    ) -> ConsumptionCandidatesResponse: ...

    def compare(self, request: ConsumptionComparisonRequest) -> ConsumptionComparisonResponse: ...


def get_consumption_comparison(request: Request) -> ConsumptionComparisonBackend:
    from cvidee.api.consumption_comparison import ConsumptionComparisonReadModel

    stub: StubStore | None = getattr(request.app.state, "stub_store", None)
    if stub is not None:
        return stub
    factory: sessionmaker[Session] | None = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise get_stub_store_problem()
    return ConsumptionComparisonReadModel(factory, lambda: int(time.time() * 1000))


ConsumptionComparison = Annotated[ConsumptionComparisonBackend, Depends(get_consumption_comparison)]


def get_monitoring(request: Request) -> MonitoringBackend:
    from cvidee.api.live_read import LiveReadModel

    stub: StubStore | None = getattr(request.app.state, "stub_store", None)
    if stub is not None:
        return StubMonitoring(stub)
    factory: sessionmaker[Session] | None = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise get_stub_store_problem()
    return LiveReadModel(
        factory,
        request.app.state.settings,
        getattr(request.app.state, "ha_client", None),
        getattr(request.app.state, "ha_export", None),
    )


class StubMonitoring:
    """Adapt the existing fixed example range without changing its contract."""

    def __init__(self, store: StubStore) -> None:
        self.store = store

    def status(self) -> StatusResponse:
        return self.store.status()

    def overview(self) -> OverviewResponse:
        return self.store.overview()

    def quality(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> QualityResponse:
        return self.store.quality()

    def cycles(
        self, limit: int, offset: int, start: datetime | None = None, end: datetime | None = None
    ) -> CycleList:
        return self.store.cycles(limit, offset)


Monitoring = Annotated[MonitoringBackend, Depends(get_monitoring)]
Consumption = Annotated[ConsumptionBackend, Depends(get_consumption)]
