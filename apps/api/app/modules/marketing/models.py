"""Marketing Studio (Phase 7B): campaigns, content items and their append-only version history.

Approval history is not duplicated here: each submission opens an ``approval_requests`` row
(entity_type ``marketing_content``) through the shared approval engine, with its steps and decisions.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey, enum_check
from app.modules.identity.models import User
from app.modules.realestate.models import ReProject

CHANNELS = ("instagram", "x", "linkedin", "email", "website", "whatsapp")
LANGUAGES = ("en", "ar")
CAMPAIGN_STATUSES = ("draft", "active", "completed", "archived")
CONTENT_STATUSES = ("draft", "pending_approval", "approved", "rejected", "archived")


class MarketingCampaign(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "marketing_campaigns"
    __table_args__ = (
        enum_check("status", CAMPAIGN_STATUSES),
        CheckConstraint("end_date IS NULL OR start_date IS NULL OR end_date >= start_date", name="dates_ordered"),
        CheckConstraint("jsonb_typeof(channels) = 'array' AND jsonb_array_length(channels) > 0", name="has_channels"),
        Index("ix_marketing_campaigns_status", "status"),
        Index("ix_marketing_campaigns_project", "project_id"),
    )

    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    objective: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("re_projects.id", ondelete="RESTRICT"), nullable=False)
    channels: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="draft", server_default="draft")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped[ReProject] = relationship(lazy="joined")
    creator: Mapped[User | None] = relationship(lazy="joined", foreign_keys=[created_by])


class MarketingContent(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "marketing_contents"
    __table_args__ = (
        enum_check("channel", CHANNELS),
        enum_check("language", LANGUAGES),
        enum_check("status", CONTENT_STATUSES),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_marketing_contents_campaign_status", "campaign_id", "status"),
        Index("ix_marketing_contents_status_updated", "status", "updated_at"),
    )

    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketing_campaigns.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("re_projects.id", ondelete="RESTRICT"), nullable=False)
    channel: Mapped[str] = mapped_column(String(12), nullable=False)
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    headline: Mapped[str | None] = mapped_column(String(150))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    call_to_action: Mapped[str | None] = mapped_column(String(120))
    hashtags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", server_default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    generated_by_ai: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    rejection_comment: Mapped[str | None] = mapped_column(String(1000))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    campaign: Mapped[MarketingCampaign] = relationship(lazy="joined")
    creator: Mapped[User | None] = relationship(lazy="joined", foreign_keys=[created_by])


class MarketingContentVersion(UUIDPrimaryKey, Base):
    """One immutable snapshot per saved version (append-only trigger). Who wrote what, and when."""

    __tablename__ = "marketing_content_versions"
    __table_args__ = (UniqueConstraint("content_id", "version", name="uq_marketing_content_versions_content_version"),)

    content_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketing_contents.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[str] = mapped_column(String(12), nullable=False)
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    headline: Mapped[str | None] = mapped_column(String(150))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    call_to_action: Mapped[str | None] = mapped_column(String(120))
    hashtags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    note: Mapped[str] = mapped_column(String(200), nullable=False)
    edited_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    editor: Mapped[User | None] = relationship(lazy="joined", foreign_keys=[edited_by])

    def snapshot(self) -> dict[str, Any]:
        return {"headline": self.headline, "body": self.body, "call_to_action": self.call_to_action, "hashtags": list(self.hashtags or [])}
