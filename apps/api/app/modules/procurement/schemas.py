from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.approvals.schemas import ApprovalDetail, PersonRef
from app.modules.finance.schemas import BudgetPositionOut, CategoryOut, ProjectRef
from app.modules.hr.schemas import DepartmentRef

MAX_MONEY = Decimal("9999999999999999.99")
Priority = Literal["low", "normal", "high", "urgent"]


# --- suppliers ------------------------------------------------------------------------------------
class SupplierRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str


class SupplierOut(SupplierRef):
    category: str
    contact_name: str | None
    email: str | None
    phone: str | None
    vat_number: str | None
    city: str | None
    rating: Decimal | None
    status: str
    notes: str | None
    quotation_count: int = 0
    selected_count: int = 0


class SupplierIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=150)
    category: str = Field(min_length=2, max_length=60)
    contact_name: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    vat_number: str | None = Field(default=None, max_length=30, pattern=r"^[0-9A-Za-z\-]*$")
    city: str | None = Field(default=None, max_length=80)
    rating: Decimal | None = Field(default=None, ge=0, le=5, decimal_places=1)
    notes: str | None = Field(default=None, max_length=2000)


class SupplierUpdate(SupplierIn):
    name: str | None = Field(default=None, min_length=2, max_length=150)  # type: ignore[assignment]
    category: str | None = Field(default=None, min_length=2, max_length=60)  # type: ignore[assignment]
    status: Literal["active", "inactive", "blocked"] | None = None


# --- purchase requests ----------------------------------------------------------------------------
class ItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=2, max_length=300)
    quantity: Decimal = Field(gt=0, le=Decimal("99999999999.999"), decimal_places=3)
    unit: str = Field(default="unit", min_length=1, max_length=20)
    estimated_unit_price: Decimal = Field(ge=0, le=MAX_MONEY, decimal_places=2)

    @field_validator("description", "unit")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class RequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=200)
    justification: str = Field(min_length=10, max_length=4000)
    department_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    category_id: uuid.UUID
    fiscal_year: int | None = Field(default=None, ge=2000, le=2100)
    needed_by: date | None = None
    priority: Priority = "normal"
    items: list[ItemIn] = Field(min_length=1, max_length=50)


class RequestUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=3, max_length=200)
    justification: str | None = Field(default=None, min_length=10, max_length=4000)
    department_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    fiscal_year: int | None = Field(default=None, ge=2000, le=2100)
    needed_by: date | None = None
    priority: Priority | None = None
    items: list[ItemIn] | None = Field(default=None, min_length=1, max_length=50)


class CancelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=500)


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_no: int
    description: str
    quantity: Decimal
    unit: str
    estimated_unit_price: Decimal
    line_total: Decimal


class QuotationItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_item_id: uuid.UUID
    unit_price: Decimal = Field(ge=0, le=MAX_MONEY, decimal_places=2)


class QuotationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: uuid.UUID
    reference: str | None = Field(default=None, max_length=60)
    valid_until: date | None = None
    delivery_days: int | None = Field(default=None, ge=0, le=3650)
    payment_terms: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)
    items: list[QuotationItemIn] = Field(min_length=1, max_length=50)


class QuotationItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_item_id: uuid.UUID
    unit_price: Decimal
    line_total: Decimal


class QuotationOut(BaseModel):
    id: uuid.UUID
    supplier: SupplierRef
    supplier_rating: Decimal | None
    reference: str | None
    valid_until: date | None
    delivery_days: int | None
    payment_terms: str | None
    notes: str | None
    total_amount: Decimal
    status: str
    items: list[QuotationItemOut]
    is_lowest: bool
    difference_from_lowest: Decimal
    created_at: datetime


class ComparisonCell(BaseModel):
    quotation_id: uuid.UUID
    unit_price: Decimal
    line_total: Decimal
    is_lowest: bool


class ComparisonRow(BaseModel):
    request_item_id: uuid.UUID
    line_no: int
    description: str
    quantity: Decimal
    unit: str
    estimated_unit_price: Decimal
    cells: list[ComparisonCell]


class Comparison(BaseModel):
    rows: list[ComparisonRow]
    lowest_quotation_id: uuid.UUID | None
    fastest_quotation_id: uuid.UUID | None
    savings_vs_estimate: Decimal | None  # estimate − lowest total (positive = cheaper than estimated)


class BudgetImpact(BaseModel):
    found: bool
    budget_id: uuid.UUID | None
    scope_label: str
    category: str
    fiscal_year: int
    position: BudgetPositionOut | None
    amount: Decimal
    available_after: Decimal | None
    over_budget: bool
    committed_by_this_request: bool = False
    approval_levels: list[str]


class BudgetPreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department_id: uuid.UUID
    project_id: uuid.UUID | None = None
    category_id: uuid.UUID
    fiscal_year: int = Field(ge=2000, le=2100)
    amount: Decimal = Field(ge=0, le=MAX_MONEY, decimal_places=2)


class RequestOut(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    status: str
    priority: str
    requester: PersonRef
    department: DepartmentRef
    project: ProjectRef | None
    category: str
    estimated_total: Decimal
    approved_total: Decimal | None
    over_budget: bool
    quotation_count: int
    needed_by: date | None
    created_at: datetime
    submitted_at: datetime | None
    decided_at: datetime | None
    waiting_on: str | None = None


class RequestDetail(RequestOut):
    purchase_orders: list[OrderSummary] = []
    justification: str
    fiscal_year: int
    category_detail: CategoryOut
    items: list[ItemOut]
    quotations: list[QuotationOut]
    comparison: Comparison
    selected_quotation_id: uuid.UUID | None
    budget_impact: BudgetImpact
    approval: ApprovalDetail | None
    allowed_actions: list[str]
    cancel_reason: str | None
    sent_for_approval_at: datetime | None


class RequestStats(BaseModel):
    draft: int
    sourcing: int
    pending_approval: int
    approved: int
    rejected: int
    cancelled: int
    closed: int = 0
    approved_value: Decimal
    in_approval_value: Decimal


# --- purchase orders (Phase 4) ----------------------------------------------------------------------
class OrderRef(BaseModel):
    id: uuid.UUID
    code: str


class OrderSummary(OrderRef):
    status: str
    supplier: str
    total_amount: Decimal
    issued_at: datetime | None
    budget_released: bool


class OrderLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_no: int
    description: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    line_total: Decimal


class OrderOut(BaseModel):
    id: uuid.UUID
    code: str
    status: str
    total_amount: Decimal
    supplier: SupplierRef
    request_id: uuid.UUID
    request_code: str
    request_title: str
    request_status: str
    expected_delivery_date: date | None
    issued_at: datetime | None
    cancelled_at: datetime | None
    budget_released: bool
    created_at: datetime


class OrderDetail(OrderOut):
    payment_terms: str | None
    delivery_address: str | None
    notes: str | None
    lines: list[OrderLineOut]
    cancel_reason: str | None
    created_by: str | None
    issued_by: str | None
    cancelled_by: str | None
    replaces: OrderRef | None
    replaced_by: OrderRef | None
    committed_amount: Decimal | None
    released_amount: Decimal | None
    allowed_actions: list[str]


class OrderCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_delivery_date: date | None = None
    delivery_address: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=2000)


class OrderUpdateIn(OrderCreateIn):
    payment_terms: str | None = Field(default=None, max_length=120)


class OrderCancelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=500)
    release_budget: bool


RequestDetail.model_rebuild()
