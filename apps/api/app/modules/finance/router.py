from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentPrincipal, SessionDep
from app.common.listing import ListParams, Page, list_params
from app.modules.finance.schemas import (
    BudgetCreate,
    BudgetDetail,
    BudgetOut,
    BudgetSummary,
    BudgetUpdate,
    CategoryOut,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
)
from app.modules.finance.service import FinanceService

router = APIRouter(prefix="/finance", tags=["finance"])


@router.get("/categories", response_model=list[CategoryOut])
def categories(principal: CurrentPrincipal, session: SessionDep) -> list[CategoryOut]:
    return FinanceService(session).categories(principal)


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(
    principal: CurrentPrincipal,
    session: SessionDep,
    status: Literal["planned", "active", "on_hold", "completed", "cancelled"] | None = None,
) -> list[ProjectOut]:
    return FinanceService(session).list_projects(principal, status=status)


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, principal: CurrentPrincipal, session: SessionDep) -> ProjectOut:
    svc = FinanceService(session)
    return svc.get_project(principal, svc.create_project(principal, body).id)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> ProjectOut:
    return FinanceService(session).get_project(principal, project_id)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: uuid.UUID, body: ProjectUpdate, principal: CurrentPrincipal, session: SessionDep) -> ProjectOut:
    svc = FinanceService(session)
    svc.update_project(principal, project_id, body)
    return svc.get_project(principal, project_id)


@router.get("/budgets/summary", response_model=BudgetSummary)
def budget_summary(
    principal: CurrentPrincipal, session: SessionDep, fiscal_year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100)
) -> BudgetSummary:
    return FinanceService(session).summary(principal, fiscal_year)


@router.get("/budgets", response_model=Page[BudgetOut])
def list_budgets(
    principal: CurrentPrincipal,
    session: SessionDep,
    params: ListParams = Depends(list_params),
    fiscal_year: int | None = Query(default=None, ge=2000, le=2100),
    scope: Literal["department", "project"] | None = None,
    department_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    status: Literal["active", "closed"] | None = None,
) -> Page[BudgetOut]:
    items, total, pages = FinanceService(session).list_budgets(
        principal,
        params,
        fiscal_year=fiscal_year,
        scope=scope,
        department_id=department_id,
        project_id=project_id,
        category_id=category_id,
        status=status,
    )
    return Page(items=items, total=total, page=params.page, page_size=params.page_size, pages=pages)


@router.post("/budgets", response_model=BudgetDetail, status_code=status.HTTP_201_CREATED)
def create_budget(body: BudgetCreate, principal: CurrentPrincipal, session: SessionDep) -> BudgetDetail:
    svc = FinanceService(session)
    return svc.get_budget(principal, svc.create_budget(principal, body).id)


@router.get("/budgets/{budget_id}", response_model=BudgetDetail)
def get_budget(budget_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> BudgetDetail:
    return FinanceService(session).get_budget(principal, budget_id)


@router.patch("/budgets/{budget_id}", response_model=BudgetDetail)
def update_budget(budget_id: uuid.UUID, body: BudgetUpdate, principal: CurrentPrincipal, session: SessionDep) -> BudgetDetail:
    svc = FinanceService(session)
    svc.update_budget(principal, budget_id, body)
    return svc.get_budget(principal, budget_id)
