from __future__ import annotations

import uuid

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.common.listing import escape_like
from app.modules.hr.models import Department, Employee


class HRRepository:
    def __init__(self, session: Session):
        self.session = session

    # --- departments ------------------------------------------------------------------------
    def get_department(self, department_id: uuid.UUID) -> Department | None:
        return self.session.get(Department, department_id)

    def department_by_code(self, code: str) -> Department | None:
        return self.session.scalar(select(Department).where(func.upper(Department.code) == code.upper()))

    def department_by_name(self, name: str) -> Department | None:
        return self.session.scalar(select(Department).where(func.lower(Department.name) == name.strip().lower()))

    def departments_with_headcount(self, *, include_inactive: bool) -> list[tuple[Department, int]]:
        headcount = (
            select(func.count(Employee.id))
            .where(Employee.department_id == Department.id, Employee.is_active.is_(True))
            .correlate(Department)
            .scalar_subquery()
        )
        stmt = select(Department, headcount).order_by(Department.name)
        if not include_inactive:
            stmt = stmt.where(Department.is_active.is_(True))
        return [(d, int(c)) for d, c in self.session.execute(stmt).unique().all()]

    # --- employees ----------------------------------------------------------------------------
    def get_employee(self, employee_id: uuid.UUID) -> Employee | None:
        return self.session.get(Employee, employee_id)

    def employee_for_user(self, user_id: uuid.UUID) -> Employee | None:
        return self.session.scalar(select(Employee).where(Employee.user_id == user_id))

    def employee_by_email(self, email: str) -> Employee | None:
        return self.session.scalar(select(Employee).where(func.lower(Employee.email) == email.lower()))

    def direct_reports(self, employee_id: uuid.UUID) -> list[Employee]:
        return list(
            self.session.scalars(
                select(Employee).where(Employee.manager_id == employee_id, Employee.is_active.is_(True)).order_by(Employee.full_name)
            ).unique()
        )

    def departments_managed_by(self, employee_id: uuid.UUID) -> list[Department]:
        return list(self.session.scalars(select(Department).where(Department.manager_employee_id == employee_id)).unique())

    def report_counts(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not ids:
            return {}
        rows = self.session.execute(
            select(Employee.manager_id, func.count())
            .where(Employee.manager_id.in_(ids), Employee.is_active.is_(True))
            .group_by(Employee.manager_id)
        ).all()
        return {m: int(c) for m, c in rows}

    def employee_query(
        self, *, q: str | None, department_id: uuid.UUID | None, manager_id: uuid.UUID | None, status: str | None
    ) -> Select[tuple[Employee]]:
        mgr = aliased(Employee)
        stmt = select(Employee).join(Department, Employee.department_id == Department.id).outerjoin(mgr, Employee.manager_id == mgr.id)
        if department_id:
            stmt = stmt.where(Employee.department_id == department_id)
        if manager_id:
            stmt = stmt.where(Employee.manager_id == manager_id)
        if status == "active":
            stmt = stmt.where(Employee.is_active.is_(True))
        elif status == "inactive":
            stmt = stmt.where(Employee.is_active.is_(False))
        if q:
            term = f"%{escape_like(q)}%"
            stmt = stmt.where(
                or_(
                    Employee.full_name.ilike(term, escape="\\"),
                    Employee.job_title.ilike(term, escape="\\"),
                    Employee.email.ilike(term, escape="\\"),
                    Employee.employee_no.ilike(term, escape="\\"),
                    Department.name.ilike(term, escape="\\"),
                )
            )
        return stmt
