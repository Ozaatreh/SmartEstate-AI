"""Global exception handlers: every error leaves the API in one shape."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError
from app.core.logging import request_id_var

log = logging.getLogger(__name__)

HTTP_CODES = {400: "bad_request", 401: "not_authenticated", 403: "permission_denied", 404: "not_found",
              405: "method_not_allowed", 409: "conflict", 429: "too_many_requests"}


def error_response(status: int, code: str, message: str, details: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "request_id": request_id_var.get(), "details": details}},
    )


def _field_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    out = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
        out.append({"field": ".".join(loc) or None, "message": err.get("msg", "Invalid value"), "type": err.get("type")})
    return out


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            log.warning("Service error: %s", exc.code)
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(422, "validation_failed", "Some fields are invalid.", {"fields": _field_errors(exc)})

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = HTTP_CODES.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return error_response(exc.status_code, code, message)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled error")
        return error_response(500, "internal_error", "Something went wrong on our side. Try again in a moment.")
