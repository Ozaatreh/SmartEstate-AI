from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.codes import next_code
from app.common.listing import ListParams, apply_sort, paginate
from app.core.errors import BusinessRuleViolation, Conflict, NotFound
from app.core.permissions import Perm
from app.modules.audit.service import AuditService
from app.modules.hr.models import Department, Employee
from app.modules.hr.repository import HRRepository
from app.modules.hr.schemas import (
    DepartmentCreate,
    DepartmentOut,
    DepartmentRef,
    DepartmentUpdate,
    EmployeeCreate,
    EmployeeDetail,
    EmployeeOut,
    EmployeeRef,
    EmployeeUpdate,
    LinkedUser,
)
from app.modules.identity.models import User
from app.modules.identity.principal import Principal, ensure_permission

EMPLOYEE_SORT = {
    "full_name": Employee.full_name,
    "employee_no": Employee.employee_no,
    "job_title": Employee.job_title,
    "hire_date": Employee.hire_date,
    "department": Department.name,
}
MAX_CHAIN = 50


def employee_out(e: Employee, reports: int = 0) -> EmployeeOut:
    return EmployeeOut(
        id=e.id,
        employee_no=e.employee_no,
        full_name=e.full_name,
        job_title=e.job_title,
        email=e.email,
        phone=e.phone,
        location=e.location,
        hire_date=e.hire_date,
        is_active=e.is_active,
        department=DepartmentRef.model_validate(e.department),
        manager=EmployeeRef.model_validate(e.manager) if e.manager else None,
        user=LinkedUser(id=e.user.id, email=e.user.email, roles=[r.name for r in e.user.roles]) if e.user else None,
        direct_reports_count=reports,
    )


class HRService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = HRRepository(session)
        self.audit = AuditService(session)

    # --- departments --------------------------------------------------------------------------
    def list_departments(self, principal: Principal, *, include_inactive: bool = False) -> list[DepartmentOut]:
        ensure_permission(principal, Perm.HR_EMPLOYEES_READ)
        return [
            DepartmentOut(
                id=d.id,
                code=d.code,
                name=d.name,
                description=d.description,
                is_active=d.is_active,
                manager=EmployeeRef.model_validate(d.manager) if d.manager else None,
                headcount=n,
            )
            for d, n in self.repo.departments_with_headcount(include_inactive=include_inactive)
        ]

    def get_department(self, principal: Principal, department_id: uuid.UUID) -> Department:
        ensure_permission(principal, Perm.HR_EMPLOYEES_READ)
        dept = self.repo.get_department(department_id)
        if dept is None:
            raise NotFound("Department not found.")
        return dept

    def create_department(self, principal: Principal, data: DepartmentCreate) -> Department:
        ensure_permission(principal, Perm.HR_DEPARTMENTS_MANAGE)
        if self.repo.department_by_code(data.code) or self.repo.department_by_name(data.name):
            raise Conflict("A department with this code or name already exists.", code="department_exists")
        dept = Department(code=data.code, name=data.name.strip(), description=data.description)
        if data.manager_employee_id:
            dept.manager_employee_id = self._active_employee(data.manager_employee_id, "manager_employee_id").id
        self.session.add(dept)
        self._flush_unique("A department with this code or name already exists.")
        self.audit.record(
            "hr.department_created",
            actor_user_id=principal.user_id,
            entity_type="department",
            entity_id=dept.id,
            summary=f"{dept.code} · {dept.name}",
        )
        self.session.commit()
        return dept

    def update_department(self, principal: Principal, department_id: uuid.UUID, data: DepartmentUpdate) -> Department:
        ensure_permission(principal, Perm.HR_DEPARTMENTS_MANAGE)
        dept = self.repo.get_department(department_id)
        if dept is None:
            raise NotFound("Department not found.")
        changes: dict[str, object] = {}
        fields = data.model_fields_set
        if "name" in fields and data.name and data.name.strip() != dept.name:
            other = self.repo.department_by_name(data.name)
            if other and other.id != dept.id:
                raise Conflict("Another department already uses this name.", code="department_exists")
            changes["name"] = [dept.name, data.name.strip()]
            dept.name = data.name.strip()
        if "description" in fields:
            dept.description = data.description
        if "manager_employee_id" in fields:
            new = self._active_employee(data.manager_employee_id, "manager_employee_id").id if data.manager_employee_id else None
            if new != dept.manager_employee_id:
                changes["manager_employee_id"] = [
                    str(dept.manager_employee_id) if dept.manager_employee_id else None,
                    str(new) if new else None,
                ]
                dept.manager_employee_id = new
        if "is_active" in fields and data.is_active is not None and data.is_active != dept.is_active:
            if not data.is_active and any(n for d, n in self.repo.departments_with_headcount(include_inactive=True) if d.id == dept.id):
                raise BusinessRuleViolation("Move or deactivate the department's active employees first.", code="department_has_employees")
            changes["is_active"] = [dept.is_active, data.is_active]
            dept.is_active = data.is_active
        self.audit.record(
            "hr.department_updated",
            actor_user_id=principal.user_id,
            entity_type="department",
            entity_id=dept.id,
            summary=f"{dept.code} · {dept.name}",
            changes=changes or None,
        )
        self.session.commit()
        self.session.refresh(dept)
        return dept

    # --- employees ------------------------------------------------------------------------------
    def list_employees(
        self,
        principal: Principal,
        params: ListParams,
        *,
        department_id: uuid.UUID | None = None,
        manager_id: uuid.UUID | None = None,
        status: str | None = "active",
    ) -> tuple[list[EmployeeOut], int, int]:
        ensure_permission(principal, Perm.HR_EMPLOYEES_READ)
        stmt = self.repo.employee_query(q=params.q, department_id=department_id, manager_id=manager_id, status=status)
        stmt = apply_sort(stmt, params.sort, EMPLOYEE_SORT, "full_name")
        rows, total, pages = paginate(self.session, stmt, params)
        counts = self.repo.report_counts([e.id for e in rows])
        return [employee_out(e, counts.get(e.id, 0)) for e in rows], total, pages

    def get_employee(self, principal: Principal, employee_id: uuid.UUID) -> EmployeeDetail:
        ensure_permission(principal, Perm.HR_EMPLOYEES_READ)
        e = self.repo.get_employee(employee_id)
        if e is None:
            raise NotFound("Employee not found.")
        reports = self.repo.direct_reports(e.id)
        base = employee_out(e, len(reports))
        return EmployeeDetail(
            **base.model_dump(),
            reporting_line=[EmployeeRef.model_validate(m) for m in self.reporting_line(e)],
            direct_reports=[EmployeeRef.model_validate(r) for r in reports],
            manages_departments=[DepartmentRef.model_validate(d) for d in self.repo.departments_managed_by(e.id)],
        )

    def reporting_line(self, employee: Employee) -> list[Employee]:
        chain: list[Employee] = []
        seen = {employee.id}
        current = employee.manager
        while current is not None and current.id not in seen and len(chain) < MAX_CHAIN:
            chain.append(current)
            seen.add(current.id)
            current = current.manager
        return chain

    def create_employee(self, principal: Principal, data: EmployeeCreate) -> Employee:
        ensure_permission(principal, Perm.HR_EMPLOYEES_MANAGE)
        dept = self._active_department(data.department_id)
        if data.email and self.repo.employee_by_email(str(data.email)):
            raise Conflict(
                "Another employee already uses this email.",
                code="employee_email_exists",
                details={"fields": [{"field": "email", "message": "Already in use."}]},
            )
        e = Employee(
            employee_no=next_code(self.session, "employee"),
            full_name=data.full_name.strip(),
            job_title=data.job_title.strip(),
            department_id=dept.id,
            email=str(data.email) if data.email else None,
            phone=data.phone,
            location=data.location,
            hire_date=data.hire_date,
        )
        if data.manager_id:
            e.manager_id = self._active_employee(data.manager_id, "manager_id").id
        if data.user_id:
            e.user_id = self._linkable_user(data.user_id, None)
        self.session.add(e)
        self._flush_unique("This employee conflicts with an existing record (email or user account).")
        self.audit.record(
            "hr.employee_created",
            actor_user_id=principal.user_id,
            entity_type="employee",
            entity_id=e.id,
            summary=f"{e.employee_no} · {e.full_name}",
        )
        self.session.commit()
        self.session.refresh(e)
        return e

    def update_employee(self, principal: Principal, employee_id: uuid.UUID, data: EmployeeUpdate) -> Employee:
        ensure_permission(principal, Perm.HR_EMPLOYEES_MANAGE)
        e = self.repo.get_employee(employee_id)
        if e is None:
            raise NotFound("Employee not found.")
        fields = data.model_fields_set
        changes: dict[str, object] = {}
        for name in ("full_name", "job_title", "phone", "location", "hire_date"):
            if name in fields:
                value = getattr(data, name)
                if name in ("full_name", "job_title"):
                    if not value:
                        raise BusinessRuleViolation(f"{name.replace('_', ' ').capitalize()} is required.")
                    value = value.strip()
                if value != getattr(e, name):
                    changes[name] = [
                        str(getattr(e, name)) if getattr(e, name) is not None else None,
                        str(value) if value is not None else None,
                    ]
                    setattr(e, name, value)
        if "email" in fields:
            email = str(data.email) if data.email else None
            if email and (other := self.repo.employee_by_email(email)) and other.id != e.id:
                raise Conflict("Another employee already uses this email.", code="employee_email_exists")
            e.email = email
        if "department_id" in fields and data.department_id and data.department_id != e.department_id:
            dept = self._active_department(data.department_id)
            changes["department_id"] = [str(e.department_id), str(dept.id)]
            e.department_id = dept.id
        if "manager_id" in fields and data.manager_id != e.manager_id:
            if data.manager_id is not None:
                manager = self._active_employee(data.manager_id, "manager_id")
                self._ensure_no_cycle(e, manager)
            changes["manager_id"] = [str(e.manager_id) if e.manager_id else None, str(data.manager_id) if data.manager_id else None]
            e.manager_id = data.manager_id
        if "is_active" in fields and data.is_active is not None and data.is_active != e.is_active:
            if not data.is_active and self.repo.departments_managed_by(e.id):
                raise BusinessRuleViolation(
                    "Assign a new manager to the departments this employee manages first.", code="employee_manages_department"
                )
            changes["is_active"] = [e.is_active, data.is_active]
            e.is_active = data.is_active
        self._flush_unique("This change conflicts with an existing employee record.")
        self.audit.record(
            "hr.employee_updated",
            actor_user_id=principal.user_id,
            entity_type="employee",
            entity_id=e.id,
            summary=f"{e.employee_no} · {e.full_name}",
            changes=changes or None,
        )
        self.session.commit()
        self.session.expire(e)
        return self.repo.get_employee(e.id)  # type: ignore[return-value]

    # --- helpers -----------------------------------------------------------------------------------
    def _ensure_no_cycle(self, employee: Employee, manager: Employee) -> None:
        if manager.id == employee.id:
            raise BusinessRuleViolation("An employee cannot be their own manager.", code="reporting_cycle")
        current: Employee | None = manager
        steps = 0
        while current is not None and steps < MAX_CHAIN:
            if current.manager_id == employee.id:
                raise BusinessRuleViolation(
                    f"{manager.full_name} already reports to {employee.full_name}; this would create a reporting loop.",
                    code="reporting_cycle",
                )
            current = current.manager
            steps += 1

    def _active_department(self, department_id: uuid.UUID) -> Department:
        dept = self.repo.get_department(department_id)
        if dept is None or not dept.is_active:
            raise BusinessRuleViolation(
                "Choose an active department.",
                code="invalid_department",
                details={"fields": [{"field": "department_id", "message": "Choose an active department."}]},
            )
        return dept

    def _active_employee(self, employee_id: uuid.UUID, field: str) -> Employee:
        e = self.repo.get_employee(employee_id)
        if e is None or not e.is_active:
            raise BusinessRuleViolation(
                "Choose an active employee.",
                code="invalid_employee",
                details={"fields": [{"field": field, "message": "Choose an active employee."}]},
            )
        return e

    def _linkable_user(self, user_id: uuid.UUID, employee_id: uuid.UUID | None) -> uuid.UUID:
        user = self.session.get(User, user_id)
        if user is None:
            raise BusinessRuleViolation("User account not found.", code="invalid_user")
        linked = self.repo.employee_for_user(user_id)
        if linked and linked.id != employee_id:
            raise Conflict("This user account is already linked to another employee.", code="user_already_linked")
        return user.id

    def _flush_unique(self, message: str) -> None:
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise Conflict(message) from exc
