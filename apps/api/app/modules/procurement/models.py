from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey, enum_check
from app.modules.finance.models import Budget, BudgetCategory, OperationalProject
from app.modules.hr.models import Department, Employee
from app.modules.identity.models import User

SUPPLIER_STATUSES = ("active", "inactive", "blocked")
PR_STATUSES = ("draft", "sourcing", "pending_approval", "approved", "rejected", "cancelled", "closed")
PO_STATUSES = ("draft", "issued", "cancelled")
PR_PRIORITIES = ("low", "normal", "high", "urgent")
QUOTATION_STATUSES = ("received", "selected", "not_selected")


class Supplier(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        enum_check("status", SUPPLIER_STATUSES),
        CheckConstraint("rating IS NULL OR rating BETWEEN 0 AND 5", name="rating_range"),
        Index("uq_suppliers_name_lower", func.lower(text("name")), unique=True),
        Index("ix_suppliers_category_status", "category", "status"),
    )

    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(40))
    vat_number: Mapped[str | None] = mapped_column(String(30))
    city: Mapped[str | None] = mapped_column(String(80))
    rating: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="active", server_default="active")
    notes: Mapped[str | None] = mapped_column(Text)


class PurchaseRequest(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "purchase_requests"
    __table_args__ = (
        enum_check("status", PR_STATUSES),
        enum_check("priority", PR_PRIORITIES),
        CheckConstraint("estimated_total >= 0", name="estimated_total_non_negative"),
        CheckConstraint("approved_total IS NULL OR approved_total >= 0", name="approved_total_non_negative"),
        CheckConstraint("fiscal_year BETWEEN 2000 AND 2100", name="fiscal_year_range"),
        Index("ix_purchase_requests_status_department", "status", "department_id"),
        Index("ix_purchase_requests_requester_created", "requester_user_id", "created_at"),
        Index("ix_purchase_requests_budget", "budget_id"),
        Index("ix_purchase_requests_project", "project_id"),
    )

    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    requester_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    requester_employee_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"))
    department_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_projects.id", ondelete="RESTRICT"))
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budget_categories.id", ondelete="RESTRICT"), nullable=False
    )
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    budget_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="RESTRICT"))
    needed_by: Mapped[date | None] = mapped_column(Date)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="normal", server_default="normal")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", server_default="draft")
    estimated_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")
    approved_total: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    over_budget: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    budget_available_at_check: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    budget_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    selected_quotation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("supplier_quotations.id", ondelete="SET NULL", use_alter=True, name="fk_purchase_requests_selected_quotation_id"),
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_for_approval_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(500))

    requester: Mapped[User] = relationship(lazy="joined", foreign_keys=[requester_user_id])
    department: Mapped[Department] = relationship(lazy="joined")
    project: Mapped[OperationalProject | None] = relationship(lazy="joined")
    category: Mapped[BudgetCategory] = relationship(lazy="joined")
    budget: Mapped[Budget | None] = relationship(lazy="joined")
    requester_employee: Mapped[Employee | None] = relationship(lazy="joined", foreign_keys=[requester_employee_id])
    items: Mapped[list[PurchaseRequestItem]] = relationship(
        back_populates="request", lazy="selectin", order_by="PurchaseRequestItem.line_no", cascade="all, delete-orphan"
    )
    quotations: Mapped[list[SupplierQuotation]] = relationship(
        back_populates="request",
        lazy="selectin",
        order_by="SupplierQuotation.created_at",
        cascade="all, delete-orphan",
        foreign_keys="SupplierQuotation.request_id",
    )


class PurchaseRequestItem(UUIDPrimaryKey, Base):
    __tablename__ = "purchase_request_items"
    __table_args__ = (
        UniqueConstraint("request_id", "line_no", name="uq_purchase_request_items_line"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("estimated_unit_price >= 0", name="unit_price_non_negative"),
        CheckConstraint("line_total = round(quantity * estimated_unit_price, 2)", name="line_total_matches"),
    )

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_requests.id", ondelete="CASCADE"), nullable=False
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="unit")
    estimated_unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    request: Mapped[PurchaseRequest] = relationship(back_populates="items")


class SupplierQuotation(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "supplier_quotations"
    __table_args__ = (
        UniqueConstraint("request_id", "supplier_id", name="uq_supplier_quotations_request_supplier"),
        enum_check("status", QUOTATION_STATUSES),
        CheckConstraint("total_amount >= 0", name="total_non_negative"),
        CheckConstraint("delivery_days IS NULL OR delivery_days >= 0", name="delivery_days_non_negative"),
        Index("uq_supplier_quotations_one_selected", "request_id", unique=True, postgresql_where=text("status = 'selected'")),
    )

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_requests.id", ondelete="CASCADE"), nullable=False
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    reference: Mapped[str | None] = mapped_column(String(60))
    valid_until: Mapped[date | None] = mapped_column(Date)
    delivery_days: Mapped[int | None] = mapped_column(Integer)
    payment_terms: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(15), nullable=False, default="received", server_default="received")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    request: Mapped[PurchaseRequest] = relationship(back_populates="quotations", foreign_keys=[request_id])
    supplier: Mapped[Supplier] = relationship(lazy="joined")
    items: Mapped[list[QuotationItem]] = relationship(back_populates="quotation", lazy="selectin", cascade="all, delete-orphan")


class QuotationItem(UUIDPrimaryKey, Base):
    __tablename__ = "quotation_items"
    __table_args__ = (
        UniqueConstraint("quotation_id", "request_item_id", name="uq_quotation_items_item"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
    )

    quotation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("supplier_quotations.id", ondelete="CASCADE"), nullable=False
    )
    request_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_request_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    quotation: Mapped[SupplierQuotation] = relationship(back_populates="items")


class PurchaseOrder(UUIDPrimaryKey, Timestamps, Base):
    """Issued against a fully approved purchase request. It carries no budget effect of its own: the
    commitment was written at the request's final approval (deliberate deviation from the roadmap,
    see DATABASE_DESIGN.md). Cancelling with release writes the request's single release entry."""

    __tablename__ = "purchase_orders"
    __table_args__ = (
        enum_check("status", PO_STATUSES),
        CheckConstraint("total_amount >= 0", name="total_non_negative"),
        # At most one active (draft or issued) purchase order per request.
        Index("uq_purchase_orders_active_request", "request_id", unique=True, postgresql_where=text("status <> 'cancelled'")),
        Index("ix_purchase_orders_status_created", "status", "created_at"),
        Index("ix_purchase_orders_supplier", "supplier_id"),
        CheckConstraint("status <> 'issued' OR issued_at IS NOT NULL", name="issued_has_timestamp"),
        CheckConstraint("status <> 'cancelled' OR (cancelled_at IS NOT NULL AND cancel_reason IS NOT NULL)", name="cancelled_has_reason"),
    )

    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_requests.id", ondelete="RESTRICT"), nullable=False
    )
    quotation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("supplier_quotations.id", ondelete="RESTRICT"), nullable=False
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False)
    budget_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="RESTRICT"), nullable=False)
    replaces_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="draft", server_default="draft")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    payment_terms: Mapped[str | None] = mapped_column(String(120))
    expected_delivery_date: Mapped[date | None] = mapped_column(Date)
    delivery_address: Mapped[str | None] = mapped_column(String(300))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issued_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    cancel_reason: Mapped[str | None] = mapped_column(String(500))
    budget_released: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))

    request: Mapped[PurchaseRequest] = relationship(lazy="joined")
    supplier: Mapped[Supplier] = relationship(lazy="joined")
    lines: Mapped[list[PurchaseOrderLine]] = relationship(
        back_populates="order", lazy="selectin", order_by="PurchaseOrderLine.line_no", cascade="all, delete-orphan"
    )


class PurchaseOrderLine(UUIDPrimaryKey, Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        UniqueConstraint("order_id", "line_no", name="uq_purchase_order_lines_line"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        CheckConstraint("line_total = round(quantity * unit_price, 2)", name="line_total_matches"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False)
    request_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_request_items.id", ondelete="RESTRICT"), nullable=False
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    order: Mapped[PurchaseOrder] = relationship(back_populates="lines")
