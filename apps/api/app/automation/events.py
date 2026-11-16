"""EventBus — the only thing business modules import from automation.

``emit`` adds an outbox row to the caller's transaction, so an event exists if and only if the
business change committed. The worker dispatches events to subscribed workflows later.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.automation.models import AutomationEvent


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_safe(v) for v in value]
    if isinstance(value, Decimal | uuid.UUID):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def emit(
    session: Session,
    event_type: str,
    *,
    entity_type: str | None = None,
    entity_id: str | uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> AutomationEvent:
    event = AutomationEvent(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        payload=_json_safe(payload or {}),
        actor_user_id=actor_user_id if actor_user_id and actor_user_id.int != 0 else None,
    )
    session.add(event)
    return event
