"""``ai_usage``: one append-only row per gateway call (operational metadata only).

Never stored: prompts, responses, system prompts, API keys or other credentials. The row says who asked
(user id or system), for which capability, on which model, how it ended, how long it took and what it cost.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey, enum_check

USAGE_STATUSES = ("succeeded", "failed", "rejected")
ACTOR_TYPES = ("user", "system")


class AIUsage(UUIDPrimaryKey, Base):
    __tablename__ = "ai_usage"
    __table_args__ = (
        enum_check("status", USAGE_STATUSES),
        enum_check("actor_type", ACTOR_TYPES),
        CheckConstraint(
            "coalesce(input_tokens, 0) >= 0 AND coalesce(output_tokens, 0) >= 0 "
            "AND coalesce(cache_read_tokens, 0) >= 0 AND coalesce(cache_write_tokens, 0) >= 0",
            name="tokens_non_negative",
        ),
        CheckConstraint("duration_ms >= 0", name="duration_non_negative"),
        CheckConstraint("status = 'succeeded' OR error_category IS NOT NULL", name="failure_has_category"),
        Index("ix_ai_usage_created", "created_at"),
        Index("ix_ai_usage_capability_created", "capability", "created_at"),
        Index("ix_ai_usage_status_created", "status", "created_at"),
    )

    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(100))
    actor_type: Mapped[str] = mapped_column(String(10), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    capability: Mapped[str] = mapped_column(String(40), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str | None] = mapped_column(String(80))
    served_model: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    error_category: Mapped[str | None] = mapped_column(String(30))
    provider_status: Mapped[int | None] = mapped_column(Integer)
    stop_reason: Mapped[str | None] = mapped_column(String(30))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_read_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_write_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


# --- Phase 6C: assistant conversations and tool-call records -------------------------------------------------
CONVERSATION_FEATURES = ("bi_agent", "property_assistant")
CONVERSATION_STATUSES = ("active", "closed")
MESSAGE_ROLES = ("user", "assistant")
TOOL_CALL_STATUSES = ("ok", "denied", "error")


class AIConversation(UUIDPrimaryKey, Base):
    """A chat thread. Internal threads belong to a user; public ones to a hashed visitor session cookie."""

    __tablename__ = "ai_conversations"
    __table_args__ = (
        enum_check("feature", CONVERSATION_FEATURES),
        enum_check("status", CONVERSATION_STATUSES),
        CheckConstraint("user_id IS NOT NULL OR visitor_session_id IS NOT NULL", name="has_owner"),
        Index("ix_ai_conversations_user_updated", "user_id", "updated_at"),
        Index("ix_ai_conversations_visitor", "visitor_session_id"),
    )

    feature: Mapped[str] = mapped_column(String(20), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    visitor_session_id: Mapped[str | None] = mapped_column(String(64))  # sha256 of the visitor cookie, never the cookie
    lead_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL"))
    # Set from the visitor's own request (the consent checkbox), never from model output.
    contact_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="active", server_default="active")
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AIMessage(UUIDPrimaryKey, Base):
    """Append-only. ``content`` holds the API content blocks exactly as exchanged (thinking blocks are replayed unchanged)."""

    __tablename__ = "ai_messages"
    __table_args__ = (
        enum_check("role", MESSAGE_ROLES),
        Index("uq_ai_messages_conversation_seq", "conversation_id", "seq", unique=True),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_conversations.id", ondelete="RESTRICT"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AIToolCall(UUIDPrimaryKey, Base):
    """One row per tool the model asked to run, including refused ones. Contact fields are redacted from ``input``."""

    __tablename__ = "ai_tool_calls"
    __table_args__ = (enum_check("status", TOOL_CALL_STATUSES), Index("ix_ai_tool_calls_tool_created", "tool_name", "created_at"))

    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_conversations.id", ondelete="SET NULL"))
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_messages.id", ondelete="SET NULL"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    audience: Mapped[str] = mapped_column(String(10), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(60), nullable=False)
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    result_summary: Mapped[str | None] = mapped_column(String(500))
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
