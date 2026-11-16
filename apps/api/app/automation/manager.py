"""Workflow Manager: mirrors the code registry into wf_definitions and validates configuration."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.automation.contracts import Workflow
from app.automation.models import WorkflowDefinition
from app.automation.registry import load_catalog
from app.core.errors import ValidationFailed


def sync_definitions(session: Session) -> int:
    """Upserts every registered workflow. Keeps admin-edited enablement, parameters and limits;
    adds defaults for new parameters, drops unknown ones, and flags definitions no longer in code."""
    workflows = load_catalog()
    existing = {d.key: d for d in session.scalars(select(WorkflowDefinition))}
    for key, wf in workflows.items():
        schedule = wf.schedule()
        d = existing.get(key)
        params = {k: spec.default for k, spec in wf.parameters.items()}
        if d is None:
            d = WorkflowDefinition(
                key=key,
                timeout_seconds=wf.timeout_seconds,
                max_attempts=wf.max_attempts,
                is_enabled=True,
                parameters=params,
                next_run_at=datetime.now(UTC) if schedule else None,
            )
            session.add(d)
        else:
            params.update({k: v for k, v in (d.parameters or {}).items() if k in wf.parameters})
            d.parameters = params
        d.version, d.name, d.description, d.category = wf.version, wf.name, wf.description, wf.category
        d.event_types = list(wf.event_types())
        d.schedule_minutes = schedule.every_minutes if schedule else None
        d.is_registered = True
    for key, d in existing.items():
        if key not in workflows:
            d.is_registered = False
    session.flush()
    return len(workflows)


def validate_parameters(wf: type[Workflow], values: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    clean: dict[str, Any] = {}
    for name, value in values.items():
        spec = wf.parameters.get(name)
        if spec is None:
            errors.append({"field": f"parameters.{name}", "message": "Unknown parameter."})
            continue
        if spec.type == "bool":
            if not isinstance(value, bool):
                errors.append({"field": f"parameters.{name}", "message": "Must be true or false."})
                continue
        else:
            if isinstance(value, bool) or not isinstance(value, int | float) or (spec.type == "int" and not float(value).is_integer()):
                errors.append(
                    {"field": f"parameters.{name}", "message": "Must be a whole number." if spec.type == "int" else "Must be a number."}
                )
                continue
            if spec.minimum is not None and value < spec.minimum or spec.maximum is not None and value > spec.maximum:
                errors.append({"field": f"parameters.{name}", "message": f"Must be between {spec.minimum:g} and {spec.maximum:g}."})
                continue
            value = int(value) if spec.type == "int" else float(value)
        clean[name] = value
    if errors:
        raise ValidationFailed("Some parameters are invalid.", details={"fields": errors})
    return clean
