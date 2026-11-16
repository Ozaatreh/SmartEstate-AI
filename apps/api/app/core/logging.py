"""Structured logging with request IDs and secret redaction."""

from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

SENSITIVE_KEY = re.compile(r"password|passwd|token|secret|api[_-]?key|authorization|cookie", re.I)
BEARERISH = re.compile(r"(sk-ant-[A-Za-z0-9_\-]{6})[A-Za-z0-9_\-]+")


def redact(value: object) -> object:
    """Recursively replace values whose key looks sensitive."""
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if SENSITIVE_KEY.search(str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return BEARERISH.sub(r"\1…[REDACTED]", value)
    return value


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        if isinstance(record.args, dict):
            record.args = redact(record.args)  # type: ignore[assignment]
        return True


class JsonFormatter(logging.Formatter):
    RESERVED = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "request_id"}

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": BEARERISH.sub(r"\1…[REDACTED]", record.getMessage()),
            "request_id": getattr(record, "request_id", None),
        }
        extra = {k: v for k, v in vars(record).items() if k not in self.RESERVED and not k.startswith("_")}
        if extra:
            payload.update(redact(extra))  # type: ignore[arg-type]
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO", json_logs: bool = True) -> None:
    # Windows consoles/redirects default to a legacy code page; logs are always UTF-8.
    if hasattr(sys.stdout, "reconfigure") and (sys.stdout.encoding or "").lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestContextFilter())
    handler.setFormatter(
        JsonFormatter() if json_logs else logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access",):
        logging.getLogger(noisy).setLevel(logging.WARNING)
