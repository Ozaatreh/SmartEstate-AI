from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class User(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (Index("uq_users_email_lower", func.lower(text("email")), unique=True),)

    email: Mapped[str] = mapped_column(String(254), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    job_title: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"), default=True)
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"), default=0)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"), default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    roles: Mapped[list[Role]] = relationship(secondary="user_roles", lazy="selectin", order_by="Role.name")


class Role(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"), default=False)

    permissions: Mapped[list[Permission]] = relationship(secondary="role_permissions", lazy="selectin")


class Permission(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    module: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
