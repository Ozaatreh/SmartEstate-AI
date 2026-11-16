"""Domain exceptions. Services raise these; global handlers turn them into one error shape:

    {"error": {"code", "message", "request_id", "details"}}
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code = 400
    code = "bad_request"
    message = "The request could not be processed."

    def __init__(self, message: str | None = None, *, code: str | None = None, details: Any = None):
        super().__init__(message or self.message)
        self.message = message or self.message
        if code:
            self.code = code
        self.details = details


class ValidationFailed(AppError):
    status_code, code, message = 422, "validation_failed", "Some fields are invalid."


class NotAuthenticated(AppError):
    status_code, code, message = 401, "not_authenticated", "Sign in to continue."


class PermissionDenied(AppError):
    status_code, code, message = 403, "permission_denied", "You do not have permission to do this."


class NotFound(AppError):
    status_code, code, message = 404, "not_found", "The requested item was not found."


class Conflict(AppError):
    status_code, code, message = 409, "conflict", "The request conflicts with the current state."


class BusinessRuleViolation(AppError):
    status_code, code, message = 422, "business_rule_violation", "This action is not allowed."


class TooManyRequests(AppError):
    status_code, code, message = 429, "too_many_requests", "Too many attempts. Try again later."


class ExternalServiceUnavailable(AppError):
    status_code, code, message = 503, "service_unavailable", "An external service is unavailable."
