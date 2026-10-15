"""Shared route dependencies and query parameters."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Annotated, Protocol

from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session, sessionmaker

from cvidee.api.config_backend import ConfigBackend
from cvidee.api.findings_read import FindingsReadModel
from cvidee.api.problems import ProblemError
from cvidee.api.schemas.common import UtcDateTime
from cvidee.api.schemas.data import SpecialPeriod, SpecialPeriodIn, SpecialPeriodList
from cvidee.api.schemas.findings import (
    FindingDetail,
    FindingList,
    FindingNote,
    FindingNoteCreate,
    FindingStatusUpdate,
)
from cvidee.api.schemas.installation import InstallationProfile, InstallationProfileIn
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
