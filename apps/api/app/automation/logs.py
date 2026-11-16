"""Execution logs: written in their own short transactions so they survive a failed step."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.automation.models import WorkflowExecutionLog
from app.core.logging import redact

log = logging.getLogger("app.automation")
_PY_LEVEL = {"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}


class ExecutionLogger:
    def __init__(self, session_factory: Callable[[], Session], execution_id: uuid.UUID, workflow_key: str, attempt: int):
        self._factory = session_factory
        self.execution_id = execution_id
        self.workflow_key = workflow_key
        self.attempt = attempt
        self.step_key: str | None = None

    def _write(self, level: str, message: str, data: dict[str, Any] | None) -> None:
        safe = redact(data) if data else None
        log.log(
            _PY_LEVEL[level],
            message,
            extra={"execution_id": str(self.execution_id), "workflow": self.workflow_key, "step": self.step_key, "attempt": self.attempt},
        )
        with self._factory() as s:
            s.add(
                WorkflowExecutionLog(
                    execution_id=self.execution_id,
                    attempt=self.attempt,
                    level=level,
                    step_key=self.step_key,
                    message=message[:1000],
                    data=safe,
                )
            )  # type: ignore[arg-type]
            s.commit()

    def debug(self, message: str, **data: Any) -> None:
        self._write("debug", message, data or None)

    def info(self, message: str, **data: Any) -> None:
        self._write("info", message, data or None)

    def warning(self, message: str, **data: Any) -> None:
        self._write("warning", message, data or None)

    def error(self, message: str, **data: Any) -> None:
        self._write("error", message, data or None)
