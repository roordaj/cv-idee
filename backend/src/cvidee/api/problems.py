"""RFC 7807 problem responses (``application/problem+json``) for every API error."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from cvidee.api.schemas.common import PROBLEM_MEDIA_TYPE, FieldError, Problem


class ProblemError(Exception):
    """Raise to answer with a problem document."""

    def __init__(
        self,
        status: int,
        title: str,
        detail: str | None = None,
        *,
        type_: str = "about:blank",
        errors: list[FieldError] | None = None,
    ) -> None:
        super().__init__(detail or title)
        self.problem = Problem(type=type_, title=title, status=status, detail=detail, errors=errors)


def not_found(what: str, ident: str) -> ProblemError:
    return ProblemError(404, "Niet gevonden", f"{what} '{ident}' bestaat niet (meer).")


def problem_response(problem: Problem, request: Request | None = None) -> JSONResponse:
    if request is not None and problem.instance is None:
        problem = problem.model_copy(update={"instance": request.url.path})
    return JSONResponse(
        problem.model_dump(mode="json", exclude_none=True),
        status_code=problem.status,
        media_type=PROBLEM_MEDIA_TYPE,
    )


async def _problem_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ProblemError)
    return problem_response(exc.problem, request)


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    try:
        title = HTTPStatus(exc.status_code).phrase
    except ValueError:
        title = "Error"
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail != title else None
    response = problem_response(
        Problem(title=title, status=exc.status_code, detail=detail), request
    )
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [
        FieldError(loc=list(err.get("loc", ())), msg=str(err.get("msg", "")), type=err["type"])
        for err in jsonable_encoder(exc.errors())
    ]
    count = len(errors)
    problem = Problem(
        title="Ongeldige invoer",
        status=422,
        detail=f"{count} waarde is ongeldig." if count == 1 else f"{count} waarden zijn ongeldig.",
        errors=errors,
    )
    return problem_response(problem, request)


def install_problem_handlers(app: FastAPI) -> None:
    """Register handlers so every error leaves the API as a problem document."""
    handlers: dict[Any, Any] = {
        ProblemError: _problem_error,
        StarletteHTTPException: _http_error,
        RequestValidationError: _validation_error,
    }
    for exc_class, handler in handlers.items():
        app.add_exception_handler(exc_class, handler)
