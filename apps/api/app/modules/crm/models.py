"""Minimal CRM foundation (leads) — enough for the Lead Registration workflow. Full CRM is Phase 5."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey, enum_check
from app.modules.identity.models import User

LEAD_SOURCES = ("website", "walk_in", "referral", "phone", "campaign", "property_assistant", "social")
LEAD_STAGES = ("new", "contacted", "qualified", "viewing", "negotiation", "won", "lost")
LEAD_GRADES = ("hot", "warm", "cold")
ACTIVITY_TYPES = ("note", "system", "assignment", "stage_change")


class Lead(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "leads"
    __table_args__ = (
        enum_check("source", LEAD_SOURCES),
        enum_check("stage", LEAD_STAGES),
        CheckConstraint("grade IS NULL OR grade IN ('hot', 'warm', 'cold')", name="grade_allowed"),
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 100", name="score_range"),
        CheckConstraint("phone IS NOT NULL OR email IS NOT NULL", name="contactable"),
        CheckConstraint("budget_max IS NULL OR budget_min IS NULL OR budget_max >= budget_min", name="budget_ordered"),
        Index("ix_leads_owner_stage", "owner_user_id", "stage"),
        Index("ix_leads_stage_follow_up", "stage", "next_follow_up_at"),
        Index("ix_leads_created", "created_at"),
    )

    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(254))
    preferred_language: Mapped[str] = mapped_column(String(5), nullable=False, default="en", server_default="en")
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    interest: Mapped[str | None] = mapped_column(String(300))
    budget_min: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    budget_max: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    bedrooms_wanted: Mapped[int | None] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(15), nullable=False, default="new", server_default="new")
    score: Mapped[int | None] = mapped_column(Integer)
    grade: Mapped[str | None] = mapped_column(String(5))
    score_reasons: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB(none_as_null=True))
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_given_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    owner: Mapped[User | None] = relationship(lazy="joined", foreign_keys=[owner_user_id])


class LeadActivity(UUIDPrimaryKey, Base):
    __tablename__ = "lead_activities"
    __table_args__ = (enum_check("type", ACTIVITY_TYPES), Index("ix_lead_activities_lead", "lead_id", "occurred_at"))

    lead_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(15), nullable=False)
    body: Mapped[str] = mapped_column(String(1000), nullable=False)
    performed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    dedupe_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SalesAssignmentState(Base):
    """Round-robin cursor, updated under a row lock."""

    __tablename__ = "sales_assignment_state"

    pool: Mapped[str] = mapped_column(String(40), primary_key=True)
    last_assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
