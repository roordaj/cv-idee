"""Shared route dependencies and query parameters."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Annotated, Protocol

from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session, sessionmaker

from cvidee.api.findings_read import FindingsReadModel
from cvidee.api.problems import ProblemError
from cvidee.api.schemas.common import UtcDateTime
from cvidee.api.schemas.findings import FindingDetail, FindingList
from cvidee.api.stubs.store import StubStore


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


def get_findings(request: Request) -> Iterator[FindingsBackend]:
    stub: StubStore | None = getattr(request.app.state, "stub_store", None)
    if stub is not None:
        yield stub
        return
    factory: sessionmaker[Session] | None = getattr(request.app.state, "session_factory", None)
    if factory is None:
        get_stub_store(request)  # raises the 501 problem
        return
    with factory() as session:
        yield FindingsReadModel(session, lambda: int(time.time() * 1000))


Findings = Annotated[FindingsBackend, Depends(get_findings)]
Store = Annotated[StubStore, Depends(get_stub_store)]
From = Annotated[
    UtcDateTime | None, Query(alias="from", description="Start (ISO 8601); default: latest.")
]
To = Annotated[UtcDateTime | None, Query(alias="to", description="End (ISO 8601); default: now.")]
Limit = Annotated[int, Query(ge=1, le=500, description="Page size.")]
Offset = Annotated[int, Query(ge=0, description="Items to skip.")]
