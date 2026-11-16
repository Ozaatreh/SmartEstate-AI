"""Declarative base, naming conventions and shared column mixins."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from sqlalchemy import CheckConstraint, DateTime, MetaData, Numeric, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Money = Annotated[Decimal, mapped_column(Numeric(18, 2))]


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


def enum_check(column: str, values: tuple[str, ...], name: str | None = None) -> CheckConstraint:
    """Status columns are VARCHAR + CHECK (not PostgreSQL ENUM types) for easy migrations."""
    allowed = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=name or f"{column}_allowed")
