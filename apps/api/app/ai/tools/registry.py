"""Tool registry — the only way an assistant reaches application data.

Each tool is a fixed Python function with a strict Pydantic input model, an audience (``internal`` tools for signed-in
staff, ``public`` tools for anonymous visitors) and, for internal tools, the permission it needs. The registry:

1. refuses tools that don't exist or belong to another audience;
2. validates the model's input with Pydantic (``extra="forbid"``) before anything runs;
3. checks the caller's permission — identity comes from the authenticated session (or the fixed visitor context),
   never from model output or prompt text;
4. runs the handler, which calls services; and
5. writes one ``ai_tool_calls`` row per request (contact fields redacted), whatever the outcome.

Tool results go back to the model as JSON *data*. Nothing here gives the model SQL, a database session or
credentials, and no registered tool approves, rejects, posts, pays or changes financial data.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.orm import Session

from app.ai.models import AIToolCall
from app.ai.provider import ToolSpec
from app.core.errors import AppError, PermissionDenied
from app.modules.identity.principal import Principal

log = logging.getLogger(__name__)
Audience = Literal["internal", "public"]
Status = Literal["ok", "denied", "error"]
REDACTED = "[redacted]"
MAX_RESULT_CHARS = 20_000


class ToolInput(BaseModel):
    """Base for every tool input: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")


@dataclass
class ToolContext:
    session: Session
    audience: Audience
    principal: Principal | None = None  # None only for the public (visitor) audience
    conversation_id: uuid.UUID | None = None
    visitor: Any = None  # public features attach their visitor context here


@dataclass(frozen=True)
class ToolResult:
    data: Any
    summary: str  # short, human-readable, no personal data (shown in "tools used" and stored)
    cards: list[dict[str, Any]] | None = None  # optional structured cards for the UI (e.g. unit cards)


@dataclass(frozen=True)
class Tool:
    name: str
    label: str  # UI wording, e.g. "Checked budget positions"
    description: str
    input_model: type[ToolInput]
    audience: Audience
    handler: Callable[[ToolContext, Any], ToolResult]
    permission: str | None = None
    redact_fields: frozenset[str] = frozenset()

    def spec(self) -> ToolSpec:
        return ToolSpec(self.name, self.description, self.input_model.model_json_schema())


@dataclass(frozen=True)
class ToolOutcome:
    tool_use_id: str
    name: str
    label: str
    status: Status
    summary: str
    content: str  # JSON text handed back to the model as the tool_result
    cards: list[dict[str, Any]] | None = None
    duration_ms: int = 0
    record: AIToolCall | None = field(default=None, compare=False)

    @property
    def is_error(self) -> bool:
        return self.status != "ok"


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None):
        self._tools: dict[str, Tool] = {}
        for t in tools or []:
            self.register(t)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool {tool.name!r}")
        if tool.audience == "internal" and not tool.permission:
            raise ValueError(f"Internal tool {tool.name!r} must declare a permission")
        self._tools[tool.name] = tool

    def tools(self, audience: Audience) -> list[Tool]:
        return [t for t in self._tools.values() if t.audience == audience]

    def specs(self, audience: Audience) -> list[ToolSpec]:
        return [t.spec() for t in self.tools(audience)]

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def run(self, ctx: ToolContext, tool_use_id: str, name: str, raw_input: Any) -> ToolOutcome:
        started = time.monotonic()
        tool = self._tools.get(name)
        stored_input = raw_input if isinstance(raw_input, dict) else {"_raw": str(raw_input)[:200]}
        if tool is None or tool.audience != ctx.audience:
            return self._finish(ctx, tool_use_id, name, name, stored_input, "denied", "This tool is not available here.", None, started)
        stored_input = _redact(stored_input, tool.redact_fields)
        try:
            data = tool.input_model.model_validate(raw_input)
        except ValidationError as exc:
            fields = sorted({".".join(str(p) for p in e["loc"]) or "input" for e in exc.errors()})
            return self._finish(
                ctx, tool_use_id, name, tool.label, stored_input, "error", f"Invalid input: {', '.join(fields)}", None, started
            )
        if tool.audience == "internal" and (ctx.principal is None or not ctx.principal.has(tool.permission or "")):
            msg = f"Permission denied: this needs {tool.permission}."
            return self._finish(ctx, tool_use_id, name, tool.label, stored_input, "denied", msg, None, started)
        try:
            result = tool.handler(ctx, data)
        except PermissionDenied:
            return self._finish(ctx, tool_use_id, name, tool.label, stored_input, "denied", "Permission denied.", None, started)
        except AppError as exc:  # NotFound, BusinessRuleViolation…: safe, user-facing messages
            return self._finish(ctx, tool_use_id, name, tool.label, stored_input, "error", exc.message, None, started)
        except Exception:
            log.exception("AI tool failed", extra={"ai_tool": name})
            return self._finish(ctx, tool_use_id, name, tool.label, stored_input, "error", "The tool failed unexpectedly.", None, started)
        return self._finish(ctx, tool_use_id, name, tool.label, stored_input, "ok", result.summary, result, started)

    def _finish(
        self,
        ctx: ToolContext,
        tool_use_id: str,
        name: str,
        label: str,
        stored_input: dict[str, Any],
        status: Status,
        summary: str,
        result: ToolResult | None,
        started: float,
    ) -> ToolOutcome:
        duration = max(0, int((time.monotonic() - started) * 1000))
        payload = {"status": status, "data": result.data} if result else {"status": status, "error": summary}
        content = json.dumps(payload, default=str, ensure_ascii=False)
        if len(content) > MAX_RESULT_CHARS:
            content = json.dumps({"status": "error", "error": "The result was too large; narrow the question."})
        record = AIToolCall(
            conversation_id=ctx.conversation_id,
            actor_user_id=ctx.principal.user_id if ctx.principal else None,
            audience=ctx.audience,
            tool_name=name[:60],
            input=stored_input,
            status=status,
            result_summary=summary[:500],
            duration_ms=duration,
        )
        return ToolOutcome(tool_use_id, name, label, status, summary, content, result.cards if result else None, duration, record)


def _redact(value: dict[str, Any], fields: frozenset[str]) -> dict[str, Any]:
    return {k: (REDACTED if k in fields and v not in (None, "") else v) for k, v in value.items()}
