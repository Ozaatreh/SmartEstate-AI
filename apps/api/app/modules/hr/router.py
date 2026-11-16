from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentPrincipal, SessionDep
from app.common.listing import ListParams, Page, list_params
from app.modules.hr.schemas import (
    DepartmentCreate,
    DepartmentOut,
    DepartmentUpdate,
    EmployeeCreate,
    EmployeeDetail,
    EmployeeOut,
    EmployeeRef,
    EmployeeUpdate,
)
from app.modules.hr.service import HRService

router = APIRouter(prefix="/hr", tags=["hr"])


def _dept_out(svc: HRService, principal, dept_id: uuid.UUID) -> DepartmentOut:
    return next(d for d in svc.list_departments(principal, include_inactive=True) if d.id == dept_id)


@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(principal: CurrentPrincipal, session: SessionDep, include_inactive: bool = False) -> list[DepartmentOut]:
    return HRService(session).list_departments(principal, include_inactive=include_inactive)


@router.post("/departments", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
def create_department(body: DepartmentCreate, principal: CurrentPrincipal, session: SessionDep) -> DepartmentOut:
    svc = HRService(session)
    return _dept_out(svc, principal, svc.create_department(principal, body).id)


@router.get("/departments/{department_id}", response_model=DepartmentOut)
def get_department(department_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> DepartmentOut:
    svc = HRService(session)
    svc.get_department(principal, department_id)
    return _dept_out(svc, principal, department_id)


@router.patch("/departments/{department_id}", response_model=DepartmentOut)
def update_department(department_id: uuid.UUID, body: DepartmentUpdate, principal: CurrentPrincipal, session: SessionDep) -> DepartmentOut:
    svc = HRService(session)
    svc.update_department(principal, department_id, body)
    return _dept_out(svc, principal, department_id)


@router.get("/employees", response_model=Page[EmployeeOut])
def list_employees(
    principal: CurrentPrincipal,
    session: SessionDep,
    params: ListParams = Depends(list_params),
    department_id: uuid.UUID | None = None,
    manager_id: uuid.UUID | None = None,
    status: Literal["active", "inactive", "all"] = "active",
) -> Page[EmployeeOut]:
    items, total, pages = HRService(session).list_employees(
        principal, params, department_id=department_id, manager_id=manager_id, status=None if status == "all" else status
    )
    return Page(items=items, total=total, page=params.page, page_size=params.page_size, pages=pages)


@router.post("/employees", response_model=EmployeeDetail, status_code=status.HTTP_201_CREATED)
def create_employee(body: EmployeeCreate, principal: CurrentPrincipal, session: SessionDep) -> EmployeeDetail:
    svc = HRService(session)
    return svc.get_employee(principal, svc.create_employee(principal, body).id)


@router.get("/employees/{employee_id}", response_model=EmployeeDetail)
def get_employee(employee_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> EmployeeDetail:
    return HRService(session).get_employee(principal, employee_id)


@router.patch("/employees/{employee_id}", response_model=EmployeeDetail)
def update_employee(employee_id: uuid.UUID, body: EmployeeUpdate, principal: CurrentPrincipal, session: SessionDep) -> EmployeeDetail:
    svc = HRService(session)
    svc.update_employee(principal, employee_id, body)
    return svc.get_employee(principal, employee_id)


__all__ = ["router", "EmployeeRef"]
