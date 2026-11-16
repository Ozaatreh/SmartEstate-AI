"""Test-only workflows and actions for engine behaviour (registered when this module is imported)."""

from __future__ import annotations

import time
import uuid
from collections import defaultdict

from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from app.automation.contracts import ActionContext, EventTrigger, ParamSpec, Step, Workflow
from app.automation.errors import PermanentError, TransientError
from app.automation.registry import ACTIONS, WORKFLOWS, action, register_workflow
from app.modules.notifications.service import NotificationService

CALLS: dict[str, int] = defaultdict(int)


class UserIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    tag: str


def _note(ctx: ActionContext, data: UserIn) -> None:
    NotificationService(ctx.session).notify(
        data.user_id, type="test", title=f"{data.tag} {ctx.execution.execution_id}", dedupe_key=f"{ctx.idempotency_key}:{data.tag}"
    )


if "test.record" not in ACTIONS:

    @action("test.record", label="Record", input_model=UserIn)
    def record(ctx: ActionContext, data: UserIn) -> dict:
        CALLS[f"record:{ctx.execution.execution_id}:{data.tag}"] += 1
        _note(ctx, data)
        return {"recorded": data.tag}

    @action("test.flaky", label="Flaky", input_model=UserIn)
    def flaky(ctx: ActionContext, data: UserIn) -> dict:
        n = CALLS[f"flaky:{ctx.execution.execution_id}"] = CALLS[f"flaky:{ctx.execution.execution_id}"] + 1
        _note(ctx, data)  # rolled back when we fail below
        if n == 1:
            raise TransientError("Upstream briefly unavailable")
        return {"succeeded_on_call": n}

    @action("test.always_transient", label="Always transient", input_model=UserIn)
    def always_transient(ctx: ActionContext, data: UserIn) -> dict:
        raise TransientError("Still unavailable")

    @action("test.permanent", label="Permanent", input_model=UserIn)
    def permanent(ctx: ActionContext, data: UserIn) -> dict:
        raise PermanentError("Bad data", code="bad_data")

    @action("test.slow", label="Slow", input_model=UserIn)
    def slow(ctx: ActionContext, data: UserIn) -> dict:
        _note(ctx, data)
        time.sleep(1.3)
        return {"slept": True}

    @action("test.pg_sleep", label="Long query", input_model=UserIn)
    def pg_sleep(ctx: ActionContext, data: UserIn) -> dict:
        ctx.session.execute(text("SELECT pg_sleep(5)"))
        return {}

    @action("test.noop", label="No-op", input_model=UserIn)
    def noop(ctx: ActionContext, data: UserIn) -> dict:
        CALLS[f"noop:{ctx.execution.execution_id}"] += 1
        return {"ok": True}


def _wf(key: str, steps: tuple[Step, ...], **extra) -> None:
    if key in WORKFLOWS:
        return
    attrs = {
        "key": key,
        "name": key,
        "description": "test",
        "category": "Test",
        "triggers": (EventTrigger((key,)),),
        "steps": steps,
        "parameters": {"unused": ParamSpec("int", 1, "Unused")},
        **extra,
    }
    register_workflow(type(key.replace(".", "_"), (Workflow,), attrs))


def _in(tag: str):
    return lambda c: {"user_id": c.payload["user_id"], "tag": tag}


_wf(
    "test.flaky",
    (
        Step("before", "test.record", "Before", _in("before")),
        Step("flaky", "test.flaky", "Flaky", _in("flaky")),
        Step("after", "test.record", "After", _in("after")),
    ),
)
_wf("test.exhaust", (Step("x", "test.always_transient", "X", _in("x")),), max_attempts=2)
_wf("test.permanent", (Step("x", "test.permanent", "X", _in("x")),))
_wf("test.optional", (Step("x", "test.permanent", "X", _in("x"), on_error="continue"), Step("y", "test.record", "Y", _in("y"))))
_wf("test.slow", (Step("x", "test.slow", "X", _in("x")),), timeout_seconds=1)
_wf("test.pg_sleep", (Step("x", "test.pg_sleep", "X", _in("x")),), timeout_seconds=1)
_wf("test.noop", (Step("x", "test.noop", "X", _in("x")),))
