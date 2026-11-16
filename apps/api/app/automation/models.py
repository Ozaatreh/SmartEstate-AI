"""Persistent automation state (PostgreSQL is the queue)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Identity, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey, enum_check

EVENT_STATUSES = ("pending", "dispatched", "failed")
EXECUTION_STATUSES = ("pending", "running", "succeeded", "failed", "skipped", "cancelled")
STEP_STATUSES = ("succeeded", "failed", "skipped")
LOG_LEVELS = ("debug", "info", "warning", "error")
TRIGGER_TYPES = ("event", "schedule", "manual")


class WorkflowDefinition(UUIDPrimaryKey, Timestamps, Base):
    """Registry mirror of a code-defined workflow; enablement, parameters and limits are editable data."""

    __tablename__ = "wf_definitions"

    key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    event_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    schedule_minutes: Mapped[int | None] = mapped_column(Integer)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_registered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))


class AutomationEvent(UUIDPrimaryKey, Base):
    """Transactional outbox: written by business services in their own transaction."""

    __tablename__ = "automation_events"
    __table_args__ = (
        enum_check("status", EVENT_STATUSES),
        Index("ix_automation_events_pending", "available_at", postgresql_where=text("status = 'pending'")),
        Index("ix_automation_events_entity", "entity_type", "entity_id"),
        Index("ix_automation_events_created", "created_at"),
    )

    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending", server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executions_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WorkflowExecution(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "wf_executions"
    __table_args__ = (
        enum_check("status", EXECUTION_STATUSES),
        enum_check("trigger_type", TRIGGER_TYPES),
        Index("ix_wf_executions_claim", "available_at", postgresql_where=text("status = 'pending'")),
        Index("ix_wf_executions_lease", "lease_expires_at", postgresql_where=text("status = 'running'")),
        Index("ix_wf_executions_workflow_created", "workflow_key", "created_at"),
        Index("ix_wf_executions_status_created", "status", "created_at"),
        Index("ix_wf_executions_entity", "entity_type", "entity_id"),
    )

    workflow_key: Mapped[str] = mapped_column(String(80), ForeignKey("wf_definitions.key", ondelete="RESTRICT"), nullable=False)
    workflow_version: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(10), nullable=False)
    event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("automation_events.id", ondelete="SET NULL"))
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    entity_type: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending", server_default="pending")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    lease_owner: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    error_code: Mapped[str | None] = mapped_column(String(60))
    error_message: Mapped[str | None] = mapped_column(String(1000))
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))


class WorkflowStepExecution(UUIDPrimaryKey, Base):
    """One row per step attempt. Append-only (DB trigger)."""

    __tablename__ = "wf_step_executions"
    __table_args__ = (
        UniqueConstraint("execution_id", "step_key", "attempt", name="uq_wf_step_executions_attempt"),
        enum_check("status", STEP_STATUSES),
        Index("ix_wf_step_executions_execution", "execution_id", "step_index"),
    )

    execution_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("wf_executions.id", ondelete="CASCADE"), nullable=False)
    step_key: Mapped[str] = mapped_column(String(60), nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    action_key: Mapped[str] = mapped_column(String(80), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    input: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    error_code: Mapped[str | None] = mapped_column(String(60))
    error_message: Mapped[str | None] = mapped_column(String(1000))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)


class WorkflowExecutionLog(Base):
    __tablename__ = "wf_execution_logs"
    __table_args__ = (enum_check("level", LOG_LEVELS), Index("ix_wf_execution_logs_execution", "execution_id", "seq"))

    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    execution_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("wf_executions.id", ondelete="CASCADE"), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    step_key: Mapped[str | None] = mapped_column(String(60))
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()"))


class WorkerHeartbeat(Base):
    __tablename__ = "wf_worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    hostname: Mapped[str] = mapped_column(String(120), nullable=False)
    pid: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    executions_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
