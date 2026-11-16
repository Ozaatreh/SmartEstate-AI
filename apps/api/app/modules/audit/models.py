from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, String, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKey
from app.modules.identity.models import User


class AuditLog(UUIDPrimaryKey, Base):
    """Append-only record of security- and business-relevant commands."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id", "created_at"),
        Index("ix_audit_logs_actor_created", "actor_user_id", "created_at"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[str | None] = mapped_column(String(300))
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    request_id: Mapped[str | None] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(INET)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Insertion order: events written in one transaction share created_at (transaction time).
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False, unique=True)

    actor: Mapped[User | None] = relationship(lazy="joined")
