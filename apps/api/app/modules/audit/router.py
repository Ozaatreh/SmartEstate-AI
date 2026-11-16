from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import CurrentPrincipal, SessionDep
from app.common.listing import ListParams, Page, list_params
from app.modules.audit.models import AuditLog
from app.modules.audit.service import AuditService

router = APIRouter(prefix="/audit-logs", tags=["audit"])


class ActorOut(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str


class AuditLogOut(BaseModel):
    id: uuid.UUID
    action: str
    entity_type: str | None
    entity_id: str | None
    summary: str | None
    changes: dict[str, Any] | None
    request_id: str | None
    ip_address: str | None
    created_at: datetime
    actor: ActorOut | None

    @classmethod
    def of(cls, row: AuditLog) -> AuditLogOut:
        return cls(
            id=row.id, action=row.action, entity_type=row.entity_type, entity_id=row.entity_id, summary=row.summary,
            changes=row.changes, request_id=row.request_id, ip_address=str(row.ip_address) if row.ip_address else None,
            created_at=row.created_at,
            actor=ActorOut(id=row.actor.id, full_name=row.actor.full_name, email=row.actor.email) if row.actor else None,
        )


@router.get("", response_model=Page[AuditLogOut])
def list_audit_logs(
    principal: CurrentPrincipal,
    session: SessionDep,
    params: ListParams = Depends(list_params),
    action: str | None = Query(default=None, max_length=100),
    entity_type: str | None = Query(default=None, max_length=60),
    actor_user_id: uuid.UUID | None = None,
) -> Page[AuditLogOut]:
    rows, total, pages = AuditService(session).list(
        principal, params, action=action, entity_type=entity_type, actor_user_id=actor_user_id
    )
    return Page(items=[AuditLogOut.of(r) for r in rows], total=total, page=params.page, page_size=params.page_size, pages=pages)
