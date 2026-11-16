from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.common.listing import ListParams, apply_sort, escape_like, paginate
from app.core.errors import NotFound
from app.modules.identity.principal import Principal
from app.modules.notifications.models import Notification

SORTABLE = {"created_at": Notification.created_at, "title": Notification.title}


class NotificationService:
    """In-app notifications. Every user reads only their own."""

    def __init__(self, session: Session):
        self.session = session

    def notify(
        self,
        user_id: uuid.UUID,
        *,
        type: str,
        title: str,
        body: str | None = None,
        level: str = "info",
        link: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        dedupe_key: str | None = None,
    ) -> None:
        """Adds to the caller's transaction. With ``dedupe_key`` the call is idempotent (workflow retries)."""
        stmt = insert(Notification).values(
            id=uuid.uuid4(), user_id=user_id, type=type, title=title, body=body, level=level, link=link,
            entity_type=entity_type, entity_id=entity_id, dedupe_key=dedupe_key,
        )
        if dedupe_key:
            stmt = stmt.on_conflict_do_nothing(constraint="uq_notifications_user_dedupe")
        self.session.execute(stmt)

    def list(self, principal: Principal, params: ListParams, *, unread_only: bool = False) -> tuple[list[Notification], int, int]:
        stmt = select(Notification).where(Notification.user_id == principal.user_id)
        if unread_only:
            stmt = stmt.where(Notification.read_at.is_(None))
        if params.q:
            term = f"%{escape_like(params.q)}%"
            stmt = stmt.where(or_(Notification.title.ilike(term, escape="\\"), Notification.body.ilike(term, escape="\\")))
        stmt = apply_sort(stmt, params.sort, SORTABLE, "-created_at")
        return paginate(self.session, stmt, params)

    def unread_count(self, principal: Principal) -> int:
        return self.session.scalar(
            select(func.count()).where(Notification.user_id == principal.user_id, Notification.read_at.is_(None))
        ) or 0

    def mark_read(self, principal: Principal, notification_id: uuid.UUID) -> Notification:
        row = self.session.get(Notification, notification_id)
        if row is None or row.user_id != principal.user_id:
            raise NotFound("Notification not found.")
        if row.read_at is None:
            row.read_at = datetime.now(UTC)
            self.session.commit()
        return row

    def mark_all_read(self, principal: Principal) -> int:
        result = self.session.execute(
            update(Notification)
            .where(Notification.user_id == principal.user_id, Notification.read_at.is_(None))
            .values(read_at=datetime.now(UTC))
        )
        self.session.commit()
        return result.rowcount or 0
