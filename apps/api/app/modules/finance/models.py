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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey, enum_check
from app.modules.hr.models import Department, Employee

PROJECT_STATUSES = ("planned", "active", "on_hold", "completed", "cancelled")
BUDGET_STATUSES = ("active", "closed")
LEDGER_TYPES = ("commitment", "release", "actual", "adjustment")


class BudgetCategory(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "budget_categories"

    code: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"), default=True)


class OperationalProject(UUIDPrimaryKey, Timestamps, Base):
    """Internal cost-tracking project (e.g. a construction phase or IT rollout) that can hold budgets."""

    __tablename__ = "operational_projects"
    __table_args__ = (
        enum_check("status", PROJECT_STATUSES),
        CheckConstraint("end_date IS NULL OR start_date IS NULL OR end_date >= start_date", name="dates_ordered"),
    )

    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    manager_employee_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)

    department: Mapped[Department] = relationship(lazy="joined")
    manager: Mapped[Employee | None] = relationship(lazy="joined")


class Budget(UUIDPrimaryKey, Timestamps, Base):
    """A yearly allocation for one category, scoped to exactly one department OR one operational project."""

    __tablename__ = "budgets"
    __table_args__ = (
        enum_check("status", BUDGET_STATUSES),
        CheckConstraint("allocated_amount >= 0", name="allocated_non_negative"),
        CheckConstraint("fiscal_year BETWEEN 2000 AND 2100", name="fiscal_year_range"),
        CheckConstraint("(department_id IS NULL) <> (project_id IS NULL)", name="exactly_one_scope"),
        Index(
            "uq_budgets_department_scope",
            "department_id",
            "category_id",
            "fiscal_year",
            unique=True,
            postgresql_where=text("department_id IS NOT NULL"),
        ),
        Index(
            "uq_budgets_project_scope",
            "project_id",
            "category_id",
            "fiscal_year",
            unique=True,
            postgresql_where=text("project_id IS NOT NULL"),
        ),
        Index("ix_budgets_year_status", "fiscal_year", "status"),
    )

    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budget_categories.id", ondelete="RESTRICT"), nullable=False
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_projects.id", ondelete="RESTRICT"))
    allocated_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="active", server_default="active")
    notes: Mapped[str | None] = mapped_column(Text)

    category: Mapped[BudgetCategory] = relationship(lazy="joined")
    department: Mapped[Department | None] = relationship(lazy="joined")
    project: Mapped[OperationalProject | None] = relationship(lazy="joined")


class BudgetLedgerEntry(UUIDPrimaryKey, Base):
    """Append-only (DB trigger). committed = commitments + releases; available = allocated + adjustments − committed − actual."""

    __tablename__ = "budget_ledger_entries"
    __table_args__ = (
        enum_check("entry_type", LEDGER_TYPES),
        CheckConstraint("amount <> 0", name="amount_non_zero"),
        Index("ix_budget_ledger_budget_type", "budget_id", "entry_type"),
        Index("ix_budget_ledger_source", "source_type", "source_id"),
    )

    budget_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="RESTRICT"), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_code: Mapped[str | None] = mapped_column(String(30))
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
