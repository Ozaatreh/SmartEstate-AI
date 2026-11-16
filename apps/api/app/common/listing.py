"""Shared list contract: ``?q=&sort=&page=&page_size=`` → ``{items, total, page, page_size, pages}``.

Every list endpoint uses this so the frontend DataTable behaves the same across modules.
Sorting is limited to a per-endpoint whitelist (``sort=field`` or ``sort=-field``).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.core.errors import ValidationFailed

T = TypeVar("T")
MAX_PAGE_SIZE = 100


class ListParams(BaseModel):
    q: str | None = None
    sort: str | None = None
    page: int = 1
    page_size: int = 25


def list_params(
    q: str | None = Query(default=None, max_length=100, description="Free-text search"),
    sort: str | None = Query(default=None, max_length=60, description="Field name, prefix with - for descending"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=MAX_PAGE_SIZE),
) -> ListParams:
    return ListParams(q=q.strip() or None if q else None, sort=sort, page=page, page_size=page_size)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


def apply_sort(stmt: Select[Any], sort: str | None, allowed: Mapping[str, ColumnElement[Any]], default: str) -> Select[Any]:
    key = sort or default
    desc = key.startswith("-")
    field = key.lstrip("-")
    if field not in allowed:
        raise ValidationFailed(f"Cannot sort by '{field}'.", code="invalid_sort", details={"allowed": sorted(allowed)})
    col = allowed[field]
    return stmt.order_by(col.desc().nulls_last() if desc else col.asc().nulls_last())


def paginate(session: Session, stmt: Select[Any], params: ListParams) -> tuple[list[Any], int, int]:
    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = list(session.scalars(stmt.limit(params.page_size).offset((params.page - 1) * params.page_size)).unique())
    pages = max(1, math.ceil(total / params.page_size))
    return rows, total, pages


def escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
