from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PersonRef(BaseModel):
    id: uuid.UUID
    full_name: str


class DecisionOut(BaseModel):
    decision: str
    comment: str | None
    decided_by: PersonRef
    created_at: datetime


class StepOut(BaseModel):
    step_order: int
    level: str
    label: str
    status: str
    assignee: PersonRef | None
    pool_label: str | None  # e.g. "Finance approvers" when not assigned to one person
    escalation_reason: str | None
    activated_at: datetime | None
    decided_at: datetime | None
    decision: DecisionOut | None


class ApprovalOut(BaseModel):
    id: uuid.UUID
    entity_type: str
    entity_label: str
    entity_id: uuid.UUID
    entity_code: str
    title: str
    amount: Decimal
    status: str
    flags: dict[str, Any]
    requester: PersonRef
    current_step: int | None
    current_step_label: str | None
    waiting_on: str | None
    link: str
    created_at: datetime
    completed_at: datetime | None
    can_decide: bool = False


class ApprovalDetail(ApprovalOut):
    policy_name: str
    steps: list[StepOut]
    allowed_actions: list[str]
    blocked_reason: str | None = None


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(default=None, max_length=2000)


class RejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: str = Field(min_length=3, max_length=2000)


class PendingCount(BaseModel):
    pending: int


class PolicyStepOut(BaseModel):
    step_order: int
    level: str
    label: str


class PolicyOut(BaseModel):
    id: uuid.UUID
    entity_type: str
    name: str
    min_amount: Decimal
    max_amount: Decimal | None
    steps: list[PolicyStepOut]
