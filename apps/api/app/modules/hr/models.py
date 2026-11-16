from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.modules.identity.models import User


class Department(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "departments"

    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    manager_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL", use_alter=True, name="fk_departments_manager_employee_id_employees"),
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"), default=True)

    manager: Mapped[Employee | None] = relationship(foreign_keys=[manager_employee_id], lazy="joined", post_update=True)


class Employee(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint("manager_id IS NULL OR manager_id <> id", name="not_own_manager"),
        Index("uq_employees_email_lower", func.lower(text("email")), unique=True, postgresql_where=text("email IS NOT NULL")),
        Index("ix_employees_department_active", "department_id", "is_active"),
    )

    employee_no: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), unique=True)
    department_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False)
    manager_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    job_title: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(40))
    location: Mapped[str | None] = mapped_column(String(120))
    hire_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"), default=True)

    department: Mapped[Department] = relationship(foreign_keys=[department_id], lazy="joined")
    manager: Mapped[Employee | None] = relationship(remote_side="Employee.id", foreign_keys=[manager_id], lazy="joined", join_depth=1)
    user: Mapped[User | None] = relationship(lazy="joined")
