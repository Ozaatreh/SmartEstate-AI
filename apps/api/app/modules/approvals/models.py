from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey, enum_check
from app.modules.identity.models import User

APPROVAL_LEVELS = ("department", "finance", "executive", "marketing")  # marketing: Phase 7B content review
REQUEST_STATUSES = ("pending", "approved", "rejected", "cancelled")
STEP_STATUSES = ("waiting", "pending", "approved", "rejected", "skipped")
DECISIONS = ("approved", "rejected")


class ApprovalPolicy(UUIDPrimaryKey, Timestamps, Base):
    """Amount band for an entity type: min_amount < amount ≤ max_amount (max NULL = no upper bound)."""

    __tablename__ = "approval_policies"
    __table_args__ = (
        CheckConstraint("min_amount >= 0", name="min_non_negative"),
        CheckConstraint("max_amount IS NULL OR max_amount > min_amount", name="band_ordered"),
        UniqueConstraint("entity_type", "min_amount", name="uq_approval_policies_band"),
    )

    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    min_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    max_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"), default=True)

    steps: Mapped[list[ApprovalPolicyStep]] = relationship(
        lazy="selectin", order_by="ApprovalPolicyStep.step_order", cascade="all, delete-orphan"
    )


class ApprovalPolicyStep(UUIDPrimaryKey, Base):
    __tablename__ = "approval_policy_steps"
    __table_args__ = (
        UniqueConstraint("policy_id", "step_order", name="uq_approval_policy_steps_order"),
        enum_check("level", APPROVAL_LEVELS),
    )

    policy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("approval_policies.id", ondelete="CASCADE"), nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)


class ApprovalRequest(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        enum_check("status", REQUEST_STATUSES),
        CheckConstraint("amount >= 0", name="amount_non_negative"),
        # At most one open approval per document.
        Index("uq_approval_requests_open_entity", "entity_type", "entity_id", unique=True, postgresql_where=text("status = 'pending'")),
        Index("ix_approval_requests_entity", "entity_type", "entity_id"),
        Index("ix_approval_requests_status_created", "status", "created_at"),
    )

    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    entity_code: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("approval_policies.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(15), nullable=False, default="pending", server_default="pending")
    current_step: Mapped[int | None] = mapped_column(Integer)
    flags: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    requester: Mapped[User] = relationship(lazy="joined", foreign_keys=[requested_by])
    policy: Mapped[ApprovalPolicy] = relationship(lazy="joined")
    steps: Mapped[list[ApprovalStep]] = relationship(
        back_populates="request", lazy="selectin", order_by="ApprovalStep.step_order", cascade="all, delete-orphan"
    )


class ApprovalStep(UUIDPrimaryKey, Base):
    __tablename__ = "approval_steps"
    __table_args__ = (
        UniqueConstraint("request_id", "step_order", name="uq_approval_steps_order"),
        enum_check("status", STEP_STATUSES),
        enum_check("level", APPROVAL_LEVELS),
        Index("ix_approval_steps_inbox", "status", "assigned_user_id"),
        Index("ix_approval_steps_inbox_pool", "status", "required_permission"),
    )

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    required_permission: Mapped[str] = mapped_column(String(100), nullable=False)
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    escalation_reason: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="waiting", server_default="waiting")
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    request: Mapped[ApprovalRequest] = relationship(back_populates="steps")
    assignee: Mapped[User | None] = relationship(lazy="joined", foreign_keys=[assigned_user_id])
    decision: Mapped[ApprovalDecision | None] = relationship(lazy="joined", uselist=False, back_populates="step")


class ApprovalDecision(UUIDPrimaryKey, Base):
    """Append-only (DB trigger). One decision per step; one decision per person per request (segregation of duties)."""

    __tablename__ = "approval_decisions"
    __table_args__ = (
        UniqueConstraint("step_id", name="uq_approval_decisions_step"),
        UniqueConstraint("request_id", "decided_by", name="uq_approval_decisions_request_decider"),
        enum_check("decision", DECISIONS),
        CheckConstraint("decision = 'approved' OR length(trim(coalesce(comment, ''))) > 0", name="reject_needs_comment"),
    )

    step_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("approval_steps.id", ondelete="RESTRICT"), nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("approval_requests.id", ondelete="RESTRICT"), nullable=False
    )
    decided_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    decision: Mapped[str] = mapped_column(String(10), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    step: Mapped[ApprovalStep] = relationship(back_populates="decision")
    decider: Mapped[User] = relationship(lazy="joined", foreign_keys=[decided_by])
