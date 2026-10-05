"""Shared API conventions: base model, time ranges, pagination and RFC 7807 problems.

Conventions (issue #11):

* Field names are English ``snake_case``; Dutch appears only in display texts
  (``label``, ``title``, ``text``, ``*_text``).
* Timestamps are ISO 8601 in UTC (``2026-10-04T10:00:00Z``); durations are seconds.
* Percentages are ``0-100`` and named ``*_pct``; unknown values are ``null``, never ``0``.
* Lists that can grow without bound are paginated with ``limit``/``offset`` (:class:`Page`).
* Errors use ``application/problem+json`` (:class:`Problem`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field

PROBLEM_MEDIA_TYPE = "application/problem+json"


def _to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


UtcDateTime = Annotated[
    AwareDatetime,
    AfterValidator(_to_utc),
    Field(description="ISO 8601 timestamp in UTC.", examples=["2026-10-04T10:00:00Z"]),
]
"""Timezone-aware timestamp, normalised to UTC (serialised with a ``Z`` suffix)."""


class ApiModel(BaseModel):
    """Base of all API schemas: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")


class TimeRange(ApiModel):
    """Half-open time range ``[start, end)``; ``end`` is ``null`` while still running."""

    start: UtcDateTime
    end: UtcDateTime | None = None


class Action(ApiModel):
    """A follow-up step shown next to a message (``LinkButton``)."""

    label: str = Field(description="Display text, e.g. 'Historie importeren'.")
    target: str = Field(description="Frontend route, e.g. '/kwaliteit#import'.")


class Page[T](ApiModel):
    """A page of a longer list (``?limit=&offset=``)."""

    items: list[T]
    total: int = Field(ge=0, description="Number of items over all pages.")
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class FieldError(ApiModel):
    """One validation error (``422``), shown on the matching form field."""

    loc: list[str | int] = Field(description="Path to the field, e.g. ['body', 'values', 'x'].")
    msg: str
    type: str


class Problem(ApiModel):
    """RFC 7807 problem details (``application/problem+json``)."""

    model_config = ConfigDict(extra="allow")

    type: str = Field(default="about:blank", description="URI identifying the problem type.")
    title: str = Field(description="Short summary (Dutch display text).")
    status: int = Field(ge=400, le=599)
    detail: str | None = None
    instance: str | None = None
    errors: list[FieldError] | None = Field(
        default=None, description="Field errors for validation problems (422)."
    )


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses`` entries documenting the problem format for ``statuses``."""
    descriptions = {
        400: "Bad request",
        404: "Not found",
        409: "Conflict",
        422: "Validation error",
        501: "Not implemented (start the backend with CVIDEE_STUB_DATA=1 for example data)",
    }
    return {
        status: {
            "model": Problem,
            "description": descriptions.get(status, "Error"),
            "content": {PROBLEM_MEDIA_TYPE: {"schema": {"$ref": "#/components/schemas/Problem"}}},
        }
        for status in statuses
    }
