from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.hr.schemas import DepartmentRef, EmployeeRef

Money = Decimal  # serialised as a JSON string by pydantic (exact)


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    description: str | None


class ProjectRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str


class ProjectOut(ProjectRef):
    description: str | None
    status: str
    start_date: date | None
    end_date: date | None
    department: DepartmentRef
    manager: EmployeeRef | None
    allocated_total: Money = Decimal("0.00")
    committed_total: Money = Decimal("0.00")
    available_total: Money = Decimal("0.00")


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    department_id: uuid.UUID
    manager_employee_id: uuid.UUID | None = None
    status: Literal["planned", "active", "on_hold", "completed", "cancelled"] = "active"
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def _dates(self) -> ProjectCreate:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("End date must be on or after the start date.")
        return self


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    manager_employee_id: uuid.UUID | None = None
    status: Literal["planned", "active", "on_hold", "completed", "cancelled"] | None = None
    start_date: date | None = None
    end_date: date | None = None


class BudgetPositionOut(BaseModel):
    allocated: Money
    adjustments: Money
    committed: Money
    actual: Money
    available: Money
    utilisation_pct: Decimal


class BudgetOut(BaseModel):
    id: uuid.UUID
    fiscal_year: int
    status: str
    scope: Literal["department", "project"]
    category: CategoryOut
    department: DepartmentRef | None
    project: ProjectRef | None
    owner_department: DepartmentRef
    notes: str | None
    position: BudgetPositionOut


class LedgerEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entry_type: str
    amount: Money
    source_type: str
    source_id: uuid.UUID
    source_code: str | None
    description: str | None
    created_at: datetime


class BudgetDetail(BudgetOut):
    ledger: list[LedgerEntryOut]


class BudgetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fiscal_year: int = Field(ge=2000, le=2100)
    category_id: uuid.UUID
    department_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    allocated_amount: Decimal = Field(ge=0, le=Decimal("9999999999999999.99"), decimal_places=2)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _one_scope(self) -> BudgetCreate:
        if (self.department_id is None) == (self.project_id is None):
            raise ValueError("Choose either a department or an operational project.")
        return self


class BudgetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allocated_amount: Decimal | None = Field(default=None, ge=0, le=Decimal("9999999999999999.99"), decimal_places=2)
    status: Literal["active", "closed"] | None = None
    notes: str | None = Field(default=None, max_length=2000)


class BudgetSummary(BaseModel):
    fiscal_year: int
    budget_count: int
    allocated: Money
    committed: Money
    actual: Money
    available: Money
    utilisation_pct: Decimal
    over_threshold_count: int  # budgets ≥ 80 % used
    by_department: list[DepartmentSpend]


class DepartmentSpend(BaseModel):
    department: DepartmentRef
    allocated: Money
    committed: Money
    available: Money


BudgetSummary.model_rebuild()
