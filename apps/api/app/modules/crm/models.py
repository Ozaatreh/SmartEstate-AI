"""CRM: leads, activities, round-robin state (Phase 3 foundation) and reservations (Phase 5)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey, enum_check
from app.modules.identity.models import User
from app.modules.realestate.models import ReProject, ReUnit

LEAD_SOURCES = ("website", "walk_in", "referral", "phone", "campaign", "property_assistant", "social")
LEAD_STAGES = ("new", "contacted", "qualified", "viewing", "negotiation", "won", "lost")
LEAD_GRADES = ("hot", "warm", "cold")
ACTIVITY_TYPES = ("note", "call", "email", "whatsapp", "viewing", "system", "assignment", "stage_change")
LOGGABLE_ACTIVITY_TYPES = ("note", "call", "email", "whatsapp", "viewing")
TIMELINES = ("immediate", "within_3_months", "within_6_months", "over_6_months")
OPEN_STAGES = ("new", "contacted", "qualified", "viewing", "negotiation")
RESERVATION_STATUSES = ("active", "expired", "cancelled", "converted")


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
        Index("ix_leads_project_stage", "project_id", "stage"),
        CheckConstraint(
            "timeline IS NULL OR timeline IN ('immediate', 'within_3_months', 'within_6_months', 'over_6_months')",
            name="timeline_allowed",
        ),
        CheckConstraint("stage NOT IN ('won', 'lost') OR close_reason IS NOT NULL", name="closed_has_reason"),
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
    # Phase 5
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("re_projects.id", ondelete="SET NULL"))
    interested_unit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("re_units.id", ondelete="SET NULL"))
    timeline: Mapped[str | None] = mapped_column(String(20))
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stage_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_reason: Mapped[str | None] = mapped_column(String(500))

    owner: Mapped[User | None] = relationship(lazy="joined", foreign_keys=[owner_user_id])
    project: Mapped[ReProject | None] = relationship(lazy="joined")
    interested_unit: Mapped[ReUnit | None] = relationship(lazy="joined")


class LeadActivity(UUIDPrimaryKey, Base):
    __tablename__ = "lead_activities"
    __table_args__ = (enum_check("type", ACTIVITY_TYPES), Index("ix_lead_activities_lead", "lead_id", "occurred_at"))

    lead_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(15), nullable=False)
    body: Mapped[str] = mapped_column(String(1000), nullable=False)
    performed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    dedupe_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("unit_reservations.id", ondelete="SET NULL"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SalesAssignmentState(Base):
    """Round-robin cursor, updated under a row lock."""

    __tablename__ = "sales_assignment_state"

    pool: Mapped[str] = mapped_column(String(40), primary_key=True)
    last_assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class UnitReservation(UUIDPrimaryKey, Timestamps, Base):
    """At most one active reservation per unit (partial unique index). Deposits are informational only —
    nothing is posted to any ledger."""

    __tablename__ = "unit_reservations"
    __table_args__ = (
        enum_check("status", RESERVATION_STATUSES),
        Index("uq_unit_reservations_active_unit", "unit_id", unique=True, postgresql_where=text("status = 'active'")),
        Index("ix_unit_reservations_status_expires", "status", "expires_at"),
        Index("ix_unit_reservations_lead", "lead_id"),
        CheckConstraint("expires_at > reserved_at", name="expires_after_start"),
        CheckConstraint("deposit_amount IS NULL OR deposit_amount >= 0", name="deposit_non_negative"),
        CheckConstraint("status <> 'cancelled' OR (cancelled_at IS NOT NULL AND cancel_reason IS NOT NULL)", name="cancelled_has_reason"),
        CheckConstraint("status <> 'converted' OR converted_at IS NOT NULL", name="converted_has_timestamp"),
        CheckConstraint("status <> 'expired' OR expired_at IS NOT NULL", name="expired_has_timestamp"),
    )

    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    unit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("re_units.id", ondelete="RESTRICT"), nullable=False)
    lead_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="RESTRICT"), nullable=False)
    reserved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="active", server_default="active")
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deposit_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    notes: Mapped[str | None] = mapped_column(String(1000))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    cancel_reason: Mapped[str | None] = mapped_column(String(500))
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    converted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    unit: Mapped[ReUnit] = relationship(lazy="joined")
    lead: Mapped[Lead] = relationship(lazy="joined")
    reserver: Mapped[User | None] = relationship(lazy="joined", foreign_keys=[reserved_by])
