"""Civic Pulse — Structured exception hierarchy and FastAPI exception handlers.

All API errors are returned in a uniform envelope that the React client
consumes via a single ``onError`` interceptor::

    {
        "success": false,
        "error": {
            "code": "NOT_FOUND",
            "message": "Grievance not found.",
            "field_errors": {},
            "request_id": "abc-123"
        }
    }
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


# ========================================================================== #
# Base exception
# ========================================================================== #

class AppException(Exception):
    """Base Civic Pulse application exception.

    Sub-classes only need to override ``status_code`` and ``code``.

    Parameters
    ----------
    status_code:
        HTTP status code.
    code:
        Machine-readable error code (e.g. ``"NOT_FOUND"``).
    message:
        Human-readable description.
    field_errors:
        Optional mapping of field names → validation messages.
    """

    def __init__(
        self,
        status_code: int = 500,
        code: str = "INTERNAL_ERROR",
        message: str = "An unexpected error occurred.",
        field_errors: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.field_errors = field_errors or {}


# ========================================================================== #
# Concrete sub-classes
# ========================================================================== #

class NotFoundException(AppException):
    """HTTP 404 — resource not found."""

    def __init__(
        self,
        message: str = "The requested resource was not found.",
        code: str = "NOT_FOUND",
        field_errors: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            status_code=404,
            code=code,
            message=message,
            field_errors=field_errors,
        )


class UnauthorizedException(AppException):
    """HTTP 401 — missing or invalid credentials."""

    def __init__(
        self,
        message: str = "Authentication credentials are missing or invalid.",
        code: str = "UNAUTHORIZED",
        field_errors: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            status_code=401,
            code=code,
            message=message,
            field_errors=field_errors,
        )


class ForbiddenException(AppException):
    """HTTP 403 — authenticated but insufficient permissions."""

    def __init__(
        self,
        message: str = "You do not have permission to perform this action.",
        code: str = "FORBIDDEN",
        field_errors: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            status_code=403,
            code=code,
            message=message,
            field_errors=field_errors,
        )


class ValidationException(AppException):
    """HTTP 422 — business-rule or schema validation failure."""

    def __init__(
        self,
        message: str = "Validation failed.",
        code: str = "VALIDATION_ERROR",
        field_errors: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            status_code=422,
            code=code,
            message=message,
            field_errors=field_errors,
        )


class ConflictException(AppException):
    """HTTP 409 — duplicate / conflict (e.g. email already registered)."""

    def __init__(
        self,
        message: str = "A resource conflict occurred.",
        code: str = "CONFLICT",
        field_errors: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            status_code=409,
            code=code,
            message=message,
            field_errors=field_errors,
        )


# ========================================================================== #
# Envelope builder
# ========================================================================== #

def _error_envelope(
    code: str,
    message: str,
    field_errors: dict[str, Any],
    request_id: str,
) -> dict[str, Any]:
    """Build the standard error JSON body."""
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "field_errors": field_errors,
            "request_id": request_id,
        },
    }


# ========================================================================== #
# Handler registration
# ========================================================================== #

def register_exception_handlers(app: FastAPI) -> None:
    """Attach exception handlers to *app* so every error response conforms to
    the shared contract envelope.
    """

    @app.exception_handler(AppException)
    async def _handle_app_exception(
        request: Request,
        exc: AppException,
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        logger.warning(
            "AppException [%s] %s — request_id=%s",
            exc.code,
            exc.message,
            request_id,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_envelope(
                code=exc.code,
                message=exc.message,
                field_errors=exc.field_errors,
                request_id=request_id,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        code_map = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            409: "CONFLICT",
            422: "UNPROCESSABLE_ENTITY",
            429: "TOO_MANY_REQUESTS",
        }
        code = code_map.get(exc.status_code, f"HTTP_{exc.status_code}")
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_envelope(
                code=code,
                message=str(exc.detail) if exc.detail else "An HTTP error occurred.",
                field_errors={},
                request_id=request_id,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """Convert Pydantic / FastAPI validation errors into the contract envelope."""
        request_id = getattr(request.state, "request_id", "unknown")
        field_errors: dict[str, Any] = {}
        for err in exc.errors():
            loc = ".".join(str(l) for l in err.get("loc", []))
            field_errors[loc] = err.get("msg", "Invalid value")
        return JSONResponse(
            status_code=422,
            content=_error_envelope(
                code="VALIDATION_ERROR",
                message="Request validation failed.",
                field_errors=field_errors,
                request_id=request_id,
            ),
        )

    @app.exception_handler(Exception)
    async def _handle_unhandled(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """Catch-all for unexpected errors — never leak stack traces to clients."""
        request_id = getattr(request.state, "request_id", "unknown")
        logger.exception(
            "Unhandled exception — request_id=%s",
            request_id,
        )
        return JSONResponse(
            status_code=500,
            content=_error_envelope(
                code="INTERNAL_ERROR",
                message="An unexpected internal error occurred.",
                field_errors={},
                request_id=request_id,
            ),
        )

