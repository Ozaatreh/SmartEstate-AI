from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class EmployeeRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_no: str
    full_name: str
    job_title: str


class DepartmentRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str


class DepartmentOut(DepartmentRef):
    description: str | None
    is_active: bool
    manager: EmployeeRef | None
    headcount: int = 0


class DepartmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=2, max_length=20, pattern=r"^[A-Za-z0-9\-]+$")
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    manager_employee_id: uuid.UUID | None = None

    @field_validator("code")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class DepartmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    manager_employee_id: uuid.UUID | None = None
    is_active: bool | None = None


class LinkedUser(BaseModel):
    id: uuid.UUID
    email: str
    roles: list[str]


class EmployeeOut(BaseModel):
    id: uuid.UUID
    employee_no: str
    full_name: str
    job_title: str
    email: str | None
    phone: str | None
    location: str | None
    hire_date: date | None
    is_active: bool
    department: DepartmentRef
    manager: EmployeeRef | None
    user: LinkedUser | None
    direct_reports_count: int = 0


class EmployeeDetail(EmployeeOut):
    reporting_line: list[EmployeeRef]  # manager → manager's manager → … (top last)
    direct_reports: list[EmployeeRef]
    manages_departments: list[DepartmentRef]


class EmployeeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=2, max_length=150)
    job_title: str = Field(min_length=2, max_length=120)
    department_id: uuid.UUID
    manager_id: uuid.UUID | None = None
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    location: str | None = Field(default=None, max_length=120)
    hire_date: date | None = None
    user_id: uuid.UUID | None = None


class EmployeeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    job_title: str | None = Field(default=None, min_length=2, max_length=120)
    department_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    location: str | None = Field(default=None, max_length=120)
    hire_date: date | None = None
    is_active: bool | None = None
