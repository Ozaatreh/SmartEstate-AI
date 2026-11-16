"""Engine contracts (AUTOMATION_ENGINE.md § 3). Workflows are Python classes; their enablement and
parameters are data (wf_definitions), so they can be tuned without a deploy."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.automation.logs import ExecutionLogger


# --- triggers ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class EventTrigger:
    event_types: tuple[str, ...]
    kind: Literal["event"] = "event"


@dataclass(frozen=True)
class ScheduleTrigger:
    every_minutes: int
    kind: Literal["schedule"] = "schedule"


Trigger = EventTrigger | ScheduleTrigger


# --- parameters ----------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ParamSpec:
    type: Literal["int", "number", "bool"]
    default: Any
    label: str
    description: str = ""
    minimum: float | None = None
    maximum: float | None = None
    unit: str | None = None


# --- execution context ------------------------------------------------------------------------------------
@dataclass
class ExecutionContext:
    execution_id: uuid.UUID
    workflow_key: str
    trigger_type: str
    trigger: dict[str, Any]  # event row (type, entity, payload) or schedule slot
    parameters: dict[str, Any]
    data: dict[str, dict[str, Any]] = field(default_factory=dict)  # step outputs by step key
    now: datetime | None = None

    @property
    def payload(self) -> dict[str, Any]:
        return self.trigger.get("payload") or {}

    @property
    def entity_id(self) -> str | None:
        return self.trigger.get("entity_id")


@dataclass
class ActionContext:
    """What an action receives: the step's own transaction, the execution context and a logger."""

    session: Session
    execution: ExecutionContext
    step_key: str
    idempotency_key: str  # "<execution_id>:<step_key>" — pass to services / dedupe keys
    log: ExecutionLogger


# --- conditions -----------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ConditionResult:
    passed: bool
    reason: str


@dataclass(frozen=True)
class Condition:
    name: str
    check: Callable[[Session, ExecutionContext], ConditionResult]
    description: str = ""


# --- steps & workflows ------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Step:
    key: str
    action: str
    label: str
    build_input: Callable[[ExecutionContext], BaseModel | dict[str, Any]] = lambda ctx: {}
    when: Condition | None = None
    on_error: Literal["fail", "continue"] = "fail"


class Workflow:
    key: str
    version: int = 1
    name: str
    description: str
    category: str
    triggers: tuple[Trigger, ...]
    conditions: tuple[Condition, ...] = ()
    steps: tuple[Step, ...]
    parameters: dict[str, ParamSpec] = {}
    timeout_seconds: int = 60
    max_attempts: int = 3
    entity_type: str | None = None  # what the trigger's entity_id refers to (for links)

    def idempotency_key(self, trigger_type: str, ref: str) -> str:
        return f"{self.key}:v{self.version}:{trigger_type}:{ref}"

    @classmethod
    def event_types(cls) -> tuple[str, ...]:
        return tuple(t for trig in cls.triggers if isinstance(trig, EventTrigger) for t in trig.event_types)

    @classmethod
    def schedule(cls) -> ScheduleTrigger | None:
        return next((t for t in cls.triggers if isinstance(t, ScheduleTrigger)), None)
