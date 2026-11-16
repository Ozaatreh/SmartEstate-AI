from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey, enum_check

NOTIFICATION_LEVELS = ("info", "success", "warning", "danger")


class Notification(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),
        Index("ix_notifications_user_read_created", "user_id", "read_at", "created_at"),
        enum_check("level", NOTIFICATION_LEVELS),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(60), nullable=False)
    level: Mapped[str] = mapped_column(String(10), nullable=False, default="info", server_default="info")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(300))
    entity_type: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    dedupe_key: Mapped[str | None] = mapped_column(String(200))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
