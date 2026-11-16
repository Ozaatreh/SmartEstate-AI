"""Condition Evaluator: small, named, deterministic checks. Conditions read state; they never write.

Conditions never depend on advisory (AI / recommendation) output — they decide whether the
deterministic steps run.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.automation.contracts import Condition, ConditionResult, ExecutionContext


def evaluate(session: Session, ctx: ExecutionContext, conditions: tuple[Condition, ...]) -> tuple[bool, list[dict[str, Any]]]:
    """All conditions must pass. Stops at the first failure; returns (passed, trace)."""
    trace: list[dict[str, Any]] = []
    for c in conditions:
        r = c.check(session, ctx)
        trace.append({"condition": c.name, "passed": r.passed, "reason": r.reason})
        if not r.passed:
            return False, trace
    return True, trace


# --- library -------------------------------------------------------------------------------------------
def entity_status_in(entity_label: str, loader: Callable[[Session, str], str | None], statuses: tuple[str, ...]) -> Condition:
    def check(session: Session, ctx: ExecutionContext) -> ConditionResult:
        if not ctx.entity_id:
            return ConditionResult(False, f"No {entity_label} on the trigger.")
        status = loader(session, ctx.entity_id)
        if status is None:
            return ConditionResult(False, f"The {entity_label} no longer exists.")
        ok = status in statuses
        return ConditionResult(ok, f"{entity_label.capitalize()} is {status}" + ("" if ok else f" (needs {' / '.join(statuses)})"))

    return Condition(name=f"{entity_label}_status_in", check=check, description=f"{entity_label} status is one of {', '.join(statuses)}")


def step_output_truthy(step_key: str, field: str, description: str) -> Condition:
    """Gate a step on a deterministic earlier step's output field."""

    def check(_: Session, ctx: ExecutionContext) -> ConditionResult:
        value = (ctx.data.get(step_key) or {}).get(field)
        return ConditionResult(bool(value), f"{step_key}.{field} = {value!r}")

    return Condition(name=f"{step_key}_{field}", check=check, description=description)


def step_output_at_least(step_key: str, field: str, param: str, description: str) -> Condition:
    def check(_: Session, ctx: ExecutionContext) -> ConditionResult:
        value = (ctx.data.get(step_key) or {}).get(field) or 0
        minimum = ctx.parameters[param]
        return ConditionResult(float(value) >= float(minimum), f"{step_key}.{field} = {value} (minimum {minimum})")

    return Condition(name=f"{step_key}_{field}_min", check=check, description=description)


def parameter_enabled(param: str, description: str) -> Condition:
    def check(_: Session, ctx: ExecutionContext) -> ConditionResult:
        on = bool(ctx.parameters.get(param))
        return ConditionResult(on, f"{param} is {'on' if on else 'off'}")

    return Condition(name=f"param_{param}", check=check, description=description)
