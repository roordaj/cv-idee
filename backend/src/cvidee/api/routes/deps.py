"""Shared route dependencies and query parameters."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query, Request

from cvidee.api.problems import ProblemError
from cvidee.api.schemas.common import UtcDateTime
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


Store = Annotated[StubStore, Depends(get_stub_store)]
From = Annotated[
    UtcDateTime | None, Query(alias="from", description="Start (ISO 8601); default: latest.")
]
To = Annotated[UtcDateTime | None, Query(alias="to", description="End (ISO 8601); default: now.")]
Limit = Annotated[int, Query(ge=1, le=500, description="Page size.")]
Offset = Annotated[int, Query(ge=0, description="Items to skip.")]
