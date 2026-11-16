from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class RoleSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    job_title: str | None
    initials: str
    roles: list[RoleSummary]
    permissions: list[str]
    is_super_admin: bool
    last_login_at: datetime | None
    session_expires_at: datetime | None = None
