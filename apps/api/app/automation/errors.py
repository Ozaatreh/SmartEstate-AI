"""Error classification (AUTOMATION_ENGINE.md § 9): transient → retry with backoff, permanent → fail now."""

from __future__ import annotations

import random

from sqlalchemy.exc import DBAPIError, OperationalError

from app.core.errors import AppError, ExternalServiceUnavailable


class AutomationError(Exception):
    code = "automation_error"
    transient = False

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


class TransientError(AutomationError):
    code, transient = "transient_error", True


class PermanentError(AutomationError):
    code, transient = "permanent_error", False


class StepTimeout(TransientError):
    code = "timeout"


class LeaseLost(AutomationError):
    """Another worker (or the reaper) took over this execution; this worker must stop touching it."""

    code, transient = "lease_lost", False


TRANSIENT_SQLSTATES = {
    "40001",
    "40P01",
    "57014",
    "55P03",
    "08000",
    "08003",
    "08006",
}  # serialization, deadlock, query cancel, lock n/a, connection


def classify(exc: BaseException) -> tuple[bool, str, str]:
    """Returns (transient, error_code, message) — the message never includes stack traces."""
    if isinstance(exc, AutomationError):
        return exc.transient, exc.code, str(exc)
    if isinstance(exc, ExternalServiceUnavailable):
        return True, exc.code, exc.message
    if isinstance(exc, AppError):
        return False, exc.code, exc.message
    if isinstance(exc, DBAPIError):
        state = getattr(getattr(exc, "orig", None), "sqlstate", None)
        if state == "57014":
            return True, "timeout", "The step exceeded its time limit (database statement cancelled)."
        if state in TRANSIENT_SQLSTATES or isinstance(exc, OperationalError):
            return True, "database_unavailable", f"Database error {state or ''}".strip()
        return False, "database_error", f"Database error {state or ''}".strip()
    return False, "unexpected_error", f"{type(exc).__name__}: {str(exc)[:300]}"


def backoff_seconds(attempt: int, base: int = 30, cap: int = 900, jitter: float = 0.2) -> int:
    """Exponential backoff: 30 s, 60 s, 120 s … capped, with ±20 % jitter (attempt is 1-based)."""
    raw = min(cap, base * (2 ** max(0, attempt - 1)))
    return max(1, int(raw * (1 + random.uniform(-jitter, jitter))))  # noqa: S311 - not security sensitive
