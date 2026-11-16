from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.common.listing import ListParams, apply_sort, escape_like, paginate
from app.core.logging import redact, request_id_var
from app.core.permissions import Perm
from app.modules.audit.models import AuditLog
from app.modules.identity.models import User
from app.modules.identity.principal import Principal, ensure_permission

SORTABLE = {"created_at": AuditLog.seq, "action": AuditLog.action, "entity_type": AuditLog.entity_type}


class AuditService:
    def __init__(self, session: Session):
        self.session = session

    def record(
        self,
        action: str,
        *,
        actor_user_id: uuid.UUID | None,
        entity_type: str | None = None,
        entity_id: str | uuid.UUID | None = None,
        summary: str | None = None,
        changes: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        """Add an audit row to the caller's transaction (the caller commits)."""
        row = AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            summary=summary,
            changes=redact(changes) if changes else None,  # type: ignore[arg-type]
            request_id=request_id_var.get(),
            ip_address=ip_address,
        )
        self.session.add(row)
        return row

    def for_entity(self, entity_type: str, entity_id: uuid.UUID, limit: int = 200) -> list[AuditLog]:
        """Timeline for one record. Callers must check the viewer may see that record."""
        return list(self.session.scalars(
            select(AuditLog).where(AuditLog.entity_type == entity_type, AuditLog.entity_id == str(entity_id))
            .order_by(AuditLog.created_at.desc(), AuditLog.seq.desc()).limit(limit)
        ).unique())

    def list(
        self,
        principal: Principal,
        params: ListParams,
        *,
        action: str | None = None,
        entity_type: str | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> tuple[list[AuditLog], int, int]:
        ensure_permission(principal, Perm.AUDIT_LOGS_READ)
        stmt = select(AuditLog).outerjoin(User, AuditLog.actor_user_id == User.id)
        if action:
            stmt = stmt.where(AuditLog.action.startswith(action))
        if entity_type:
            stmt = stmt.where(AuditLog.entity_type == entity_type)
        if actor_user_id:
            stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
        if params.q:
            term = f"%{escape_like(params.q)}%"
            stmt = stmt.where(
                or_(
                    AuditLog.action.ilike(term, escape="\\"),
                    AuditLog.summary.ilike(term, escape="\\"),
                    AuditLog.entity_id.ilike(term, escape="\\"),
                    User.full_name.ilike(term, escape="\\"),
                    User.email.ilike(term, escape="\\"),
                )
            )
        stmt = apply_sort(stmt, params.sort, SORTABLE, "-created_at")
        return paginate(self.session, stmt, params)
