from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ParameterOut(BaseModel):
    name: str
    type: str
    label: str
    description: str
    value: Any
    default: Any
    minimum: float | None
    maximum: float | None
    unit: str | None


class StepDefOut(BaseModel):
    key: str
    label: str
    action: str
    action_label: str
    action_description: str
    advisory: bool
    condition: str | None
    on_error: str


class WorkflowStats(BaseModel):
    window_hours: int
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    running: int = 0
    pending: int = 0
    cancelled: int = 0
    last_execution_id: uuid.UUID | None = None
    last_status: str | None = None
    last_finished_at: datetime | None = None
    avg_duration_ms: int | None = None


class WorkflowOut(BaseModel):
    key: str
    name: str
    description: str
    category: str
    version: int
    is_enabled: bool
    is_registered: bool
    event_types: list[str]
    schedule_minutes: int | None
    timeout_seconds: int
    max_attempts: int
    next_run_at: datetime | None
    last_run_at: datetime | None
    stats: WorkflowStats


class WorkflowDetail(WorkflowOut):
    conditions: list[str]
    steps: list[StepDefOut]
    parameters: list[ParameterOut]
    can_manage: bool
    can_operate: bool


class WorkflowUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_enabled: bool | None = None
    parameters: dict[str, Any] | None = None
    timeout_seconds: int | None = Field(default=None, ge=5, le=3600)
    max_attempts: int | None = Field(default=None, ge=1, le=10)


class ExecutionOut(BaseModel):
    id: uuid.UUID
    workflow_key: str
    workflow_name: str
    workflow_version: int
    trigger_type: str
    event_type: str | None
    entity_type: str | None
    entity_id: str | None
    entity_label: str | None
    status: str
    attempt: int
    max_attempts: int
    available_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    error_code: str | None
    error_message: str | None
    lease_owner: str | None
    lease_expires_at: datetime | None
    created_at: datetime


class StepRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    step_key: str
    step_index: int
    action_key: str
    attempt: int
    status: str
    input: dict[str, Any] | None
    output: dict[str, Any] | None
    error_code: str | None
    error_message: str | None
    started_at: datetime
    finished_at: datetime
    duration_ms: int


class LogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    attempt: int
    level: str
    step_key: str | None
    message: str
    data: dict[str, Any] | None
    created_at: datetime


class ExecutionDetail(ExecutionOut):
    context: dict[str, Any]
    result: dict[str, Any] | None
    triggered_by: str | None
    steps: list[StepRunOut]
    planned_steps: list[StepDefOut]
    logs: list[LogOut]
    allowed_actions: list[str]


class WorkerOut(BaseModel):
    worker_id: str
    hostname: str
    pid: int
    started_at: datetime
    last_seen_at: datetime
    executions_completed: int
    online: bool


class Overview(BaseModel):
    window_hours: int
    executions: int
    succeeded: int
    failed: int
    skipped: int
    in_progress: int
    success_rate: float | None
    queued_events: int
    queued_executions: int
    retry_scheduled: int
    workers: list[WorkerOut]
    workers_online: int


class RunNowOut(BaseModel):
    execution_id: uuid.UUID


ExecStatus = Literal["pending", "running", "succeeded", "failed", "skipped", "cancelled"]
