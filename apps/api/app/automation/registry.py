"""Workflow and action registries (code-defined; mirrored to wf_definitions by the Workflow Manager)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.automation.contracts import ActionContext, Workflow


class NoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class ActionSpec:
    key: str
    label: str
    description: str
    input_model: type[BaseModel]
    func: Callable[[ActionContext, Any], dict[str, Any]]
    advisory: bool = False  # produces recommendations only; never changes approvals, budgets or permissions


ACTIONS: dict[str, ActionSpec] = {}
WORKFLOWS: dict[str, type[Workflow]] = {}


def action(key: str, *, label: str, description: str = "", input_model: type[BaseModel] = NoInput, advisory: bool = False):
    def register(func: Callable[[ActionContext, Any], dict[str, Any]]) -> Callable[[ActionContext, Any], dict[str, Any]]:
        if key in ACTIONS:
            raise RuntimeError(f"Duplicate action key {key!r}")
        ACTIONS[key] = ActionSpec(key=key, label=label, description=description, input_model=input_model, func=func, advisory=advisory)
        return func

    return register


def register_workflow(cls: type[Workflow]) -> type[Workflow]:
    if cls.key in WORKFLOWS:
        raise RuntimeError(f"Duplicate workflow key {cls.key!r}")
    for step in cls.steps:
        if step.action not in ACTIONS:
            raise RuntimeError(f"Workflow {cls.key} step {step.key} uses unknown action {step.action!r}")
    if len({s.key for s in cls.steps}) != len(cls.steps):
        raise RuntimeError(f"Workflow {cls.key} has duplicate step keys")
    WORKFLOWS[cls.key] = cls
    return cls


def load_catalog() -> dict[str, type[Workflow]]:
    """Imports every action and workflow module (registration happens at import time)."""
    import app.automation.actions  # noqa: F401
    import app.automation.workflows  # noqa: F401

    return WORKFLOWS
