from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.automation import events
from app.common.codes import next_code
from app.common.listing import ListParams, apply_sort, escape_like, paginate
from app.common.money import ZERO, q2
from app.core.errors import BusinessRuleViolation, Conflict, NotFound
from app.core.permissions import Perm
from app.modules.audit.service import AuditService
from app.modules.finance.models import Budget, BudgetCategory, BudgetLedgerEntry, OperationalProject
from app.modules.finance.schemas import (
    BudgetCreate,
    BudgetDetail,
    BudgetOut,
    BudgetPositionOut,
    BudgetSummary,
    BudgetUpdate,
    CategoryOut,
    DepartmentSpend,
    LedgerEntryOut,
    ProjectCreate,
    ProjectOut,
    ProjectRef,
    ProjectUpdate,
)
from app.modules.hr.models import Department, Employee
from app.modules.hr.schemas import DepartmentRef, EmployeeRef
from app.modules.identity.principal import Principal, ensure_permission

ALERT_THRESHOLD = Decimal("80")


@dataclass(frozen=True)
class BudgetPosition:
    allocated: Decimal
    adjustments: Decimal
    committed: Decimal
    actual: Decimal

    @property
    def capacity(self) -> Decimal:
        return q2(self.allocated + self.adjustments)

    @property
    def available(self) -> Decimal:
        return q2(self.capacity - self.committed - self.actual)

    @property
    def used(self) -> Decimal:
        return q2(self.committed + self.actual)

    @property
    def utilisation_pct(self) -> Decimal:
        if self.capacity <= 0:
            return Decimal("0.0") if self.used == 0 else Decimal("100.0")
        return (self.used * 100 / self.capacity).quantize(Decimal("0.1"))

    def out(self) -> BudgetPositionOut:
        return BudgetPositionOut(
            allocated=q2(self.allocated),
            adjustments=q2(self.adjustments),
            committed=q2(self.committed),
            actual=q2(self.actual),
            available=self.available,
            utilisation_pct=self.utilisation_pct,
        )


@dataclass(frozen=True)
class BudgetCheck:
    budget_id: uuid.UUID | None
    position: BudgetPosition | None
    amount: Decimal

    @property
    def found(self) -> bool:
        return self.budget_id is not None

    @property
    def available_after(self) -> Decimal | None:
        return q2(self.position.available - self.amount) if self.position else None

    @property
    def over_budget(self) -> bool:
        return self.position is None or self.position.available < self.amount


def _sums():
    """Per-budget ledger aggregates (one row per budget that has entries)."""
    e = BudgetLedgerEntry
    return (
        select(
            e.budget_id.label("budget_id"),
            func.coalesce(func.sum(case((e.entry_type.in_(("commitment", "release")), e.amount))), 0).label("committed"),
            func.coalesce(func.sum(case((e.entry_type == "actual", e.amount))), 0).label("actual"),
            func.coalesce(func.sum(case((e.entry_type == "adjustment", e.amount))), 0).label("adjustments"),
        )
        .group_by(e.budget_id)
        .subquery()
    )


BUDGET_SORT = {"fiscal_year": Budget.fiscal_year, "allocated": Budget.allocated_amount, "category": BudgetCategory.name}


class FinanceService:
    def __init__(self, session: Session):
        self.session = session
        self.audit = AuditService(session)

    # --- positions (used by other modules) ----------------------------------------------------------
    def position(self, budget_id: uuid.UUID) -> BudgetPosition:
        s = _sums()
        row = self.session.execute(
            select(Budget.allocated_amount, s.c.adjustments, s.c.committed, s.c.actual)
            .outerjoin(s, s.c.budget_id == Budget.id)
            .where(Budget.id == budget_id)
        ).one_or_none()
        if row is None:
            raise NotFound("Budget not found.")
        return BudgetPosition(Decimal(row[0]), Decimal(row[1] or 0), Decimal(row[2] or 0), Decimal(row[3] or 0))

    def resolve_budget(
        self, *, department_id: uuid.UUID, project_id: uuid.UUID | None, category_id: uuid.UUID, fiscal_year: int
    ) -> Budget | None:
        """Project requests draw on the project's budget; others on the department's budget."""
        stmt = select(Budget).where(Budget.category_id == category_id, Budget.fiscal_year == fiscal_year, Budget.status == "active")
        stmt = stmt.where(Budget.project_id == project_id) if project_id else stmt.where(Budget.department_id == department_id)
        return self.session.scalar(stmt)

    def check(
        self, *, department_id: uuid.UUID, project_id: uuid.UUID | None, category_id: uuid.UUID, fiscal_year: int, amount: Decimal
    ) -> BudgetCheck:
        budget = self.resolve_budget(department_id=department_id, project_id=project_id, category_id=category_id, fiscal_year=fiscal_year)
        if budget is None:
            return BudgetCheck(None, None, q2(amount))
        return BudgetCheck(budget.id, self.position(budget.id), q2(amount))

    def commit(
        self,
        *,
        budget_id: uuid.UUID,
        amount: Decimal,
        source_type: str,
        source_id: uuid.UUID,
        source_code: str,
        actor_user_id: uuid.UUID | None,
        description: str,
    ) -> BudgetLedgerEntry:
        """Records a commitment inside the caller's transaction. Idempotent per source; the budget row is
        locked so concurrent commitments are serialised."""
        return self._post(
            budget_id,
            "commitment",
            q2(amount),
            source_type,
            source_id,
            source_code,
            actor_user_id,
            description,
            key=f"{source_type}:{source_id}:commitment",
        )

    def release(
        self,
        *,
        budget_id: uuid.UUID,
        amount: Decimal,
        source_type: str,
        source_id: uuid.UUID,
        source_code: str,
        actor_user_id: uuid.UUID | None,
        description: str,
    ) -> BudgetLedgerEntry:
        return self._post(
            budget_id,
            "release",
            -q2(amount),
            source_type,
            source_id,
            source_code,
            actor_user_id,
            description,
            key=f"{source_type}:{source_id}:release",
        )

    def lock_budget(self, budget_id: uuid.UUID) -> Budget:
        budget = self.session.scalar(
            select(Budget).where(Budget.id == budget_id).with_for_update(of=Budget).execution_options(populate_existing=True)
        )
        if budget is None:
            raise NotFound("Budget not found.")
        return budget

    def _post(
        self,
        budget_id: uuid.UUID,
        entry_type: str,
        amount: Decimal,
        source_type: str,
        source_id: uuid.UUID,
        source_code: str,
        actor_user_id: uuid.UUID | None,
        description: str,
        *,
        key: str,
    ) -> BudgetLedgerEntry:
        if amount == 0:
            raise BusinessRuleViolation("A ledger entry needs a non-zero amount.")
        self.lock_budget(budget_id)
        existing = self.session.scalar(select(BudgetLedgerEntry).where(BudgetLedgerEntry.idempotency_key == key))
        if existing is not None:
            return existing  # duplicate posting attempt → no second financial effect
        entry = BudgetLedgerEntry(
            budget_id=budget_id,
            entry_type=entry_type,
            amount=amount,
            source_type=source_type,
            source_id=source_id,
            source_code=source_code,
            idempotency_key=key,
            description=description,
            created_by=actor_user_id,
        )
        self.session.add(entry)
        self.session.flush()
        events.emit(self.session, "budget.ledger_changed", entity_type="budget", entity_id=budget_id, actor_user_id=actor_user_id,
                    payload={"budget_id": str(budget_id), "entry_type": entry_type, "amount": str(amount), "source_code": source_code})
        return entry

    # --- categories & projects -------------------------------------------------------------------------
    def categories(self, principal: Principal) -> list[CategoryOut]:
        return [
            CategoryOut.model_validate(c)
            for c in self.session.scalars(select(BudgetCategory).where(BudgetCategory.is_active.is_(True)).order_by(BudgetCategory.name))
        ]

    def list_projects(self, principal: Principal, *, status: str | None = None) -> list[ProjectOut]:
        stmt = select(OperationalProject).order_by(OperationalProject.code)
        if status:
            stmt = stmt.where(OperationalProject.status == status)
        projects = list(self.session.scalars(stmt).unique())
        totals = self._project_totals([p.id for p in projects]) if principal.has(Perm.FINANCE_BUDGETS_READ) else {}
        return [self._project_out(p, totals.get(p.id)) for p in projects]

    def get_project(self, principal: Principal, project_id: uuid.UUID) -> ProjectOut:
        p = self.session.get(OperationalProject, project_id)
        if p is None:
            raise NotFound("Project not found.")
        totals = self._project_totals([p.id]) if principal.has(Perm.FINANCE_BUDGETS_READ) else {}
        return self._project_out(p, totals.get(p.id))

    def create_project(self, principal: Principal, data: ProjectCreate) -> OperationalProject:
        ensure_permission(principal, Perm.FINANCE_PROJECTS_MANAGE)
        self._active_department(data.department_id)
        p = OperationalProject(
            code=next_code(self.session, "operational_project"),
            name=data.name.strip(),
            description=data.description,
            department_id=data.department_id,
            status=data.status,
            start_date=data.start_date,
            end_date=data.end_date,
        )
        if data.manager_employee_id:
            p.manager_employee_id = self._active_employee(data.manager_employee_id)
        self.session.add(p)
        self.session.flush()
        self.audit.record(
            "finance.project_created",
            actor_user_id=principal.user_id,
            entity_type="operational_project",
            entity_id=p.id,
            summary=f"{p.code} · {p.name}",
        )
        self.session.commit()
        return p

    def update_project(self, principal: Principal, project_id: uuid.UUID, data: ProjectUpdate) -> OperationalProject:
        ensure_permission(principal, Perm.FINANCE_PROJECTS_MANAGE)
        p = self.session.get(OperationalProject, project_id)
        if p is None:
            raise NotFound("Project not found.")
        fields = data.model_fields_set
        changes: dict[str, object] = {}
        for name in ("name", "description", "status", "start_date", "end_date"):
            if name in fields and getattr(data, name) is not None or (name == "description" and name in fields):
                new = getattr(data, name)
                if new != getattr(p, name):
                    changes[name] = [str(getattr(p, name)), str(new)]
                    setattr(p, name, new)
        if p.start_date and p.end_date and p.end_date < p.start_date:
            raise BusinessRuleViolation("End date must be on or after the start date.")
        if "manager_employee_id" in fields:
            p.manager_employee_id = self._active_employee(data.manager_employee_id) if data.manager_employee_id else None
        self.audit.record(
            "finance.project_updated",
            actor_user_id=principal.user_id,
            entity_type="operational_project",
            entity_id=p.id,
            summary=f"{p.code} · {p.name}",
            changes=changes or None,
        )
        self.session.commit()
        return p

    # --- budgets ------------------------------------------------------------------------------------
    def _budget_query(self) -> Select:
        s = _sums()
        return (
            select(Budget, s.c.adjustments, s.c.committed, s.c.actual)
            .join(BudgetCategory, Budget.category_id == BudgetCategory.id)
            .outerjoin(OperationalProject, Budget.project_id == OperationalProject.id)
            .outerjoin(Department, Department.id == func.coalesce(Budget.department_id, OperationalProject.department_id))
            .outerjoin(s, s.c.budget_id == Budget.id)
        )

    def list_budgets(
        self,
        principal: Principal,
        params: ListParams,
        *,
        fiscal_year: int | None,
        scope: str | None,
        department_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
        category_id: uuid.UUID | None,
        status: str | None,
    ) -> tuple[list[BudgetOut], int, int]:
        ensure_permission(principal, Perm.FINANCE_BUDGETS_READ)
        stmt = self._budget_query()
        if fiscal_year:
            stmt = stmt.where(Budget.fiscal_year == fiscal_year)
        if scope == "department":
            stmt = stmt.where(Budget.department_id.is_not(None))
        elif scope == "project":
            stmt = stmt.where(Budget.project_id.is_not(None))
        if department_id:
            stmt = stmt.where(Department.id == department_id)
        if project_id:
            stmt = stmt.where(Budget.project_id == project_id)
        if category_id:
            stmt = stmt.where(Budget.category_id == category_id)
        if status:
            stmt = stmt.where(Budget.status == status)
        if params.q:
            term = f"%{escape_like(params.q)}%"
            stmt = stmt.where(
                or_(
                    BudgetCategory.name.ilike(term, escape="\\"),
                    Department.name.ilike(term, escape="\\"),
                    OperationalProject.name.ilike(term, escape="\\"),
                    OperationalProject.code.ilike(term, escape="\\"),
                )
            )
        sort_map = {**BUDGET_SORT, "department": Department.name}
        stmt = apply_sort(stmt, params.sort, sort_map, "department")
        total = self.session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
        rows = self.session.execute(stmt.limit(params.page_size).offset((params.page - 1) * params.page_size)).unique().all()
        pages = max(1, -(-total // params.page_size))
        return [self._budget_out(b, adj, com, act) for b, adj, com, act in rows], total, pages

    def get_budget(self, principal: Principal, budget_id: uuid.UUID) -> BudgetDetail:
        ensure_permission(principal, Perm.FINANCE_BUDGETS_READ)
        row = self.session.execute(self._budget_query().where(Budget.id == budget_id)).unique().one_or_none()
        if row is None:
            raise NotFound("Budget not found.")
        ledger = self.session.scalars(
            select(BudgetLedgerEntry).where(BudgetLedgerEntry.budget_id == budget_id).order_by(BudgetLedgerEntry.created_at.desc())
        )
        base = self._budget_out(*row)
        return BudgetDetail(**base.model_dump(), ledger=[LedgerEntryOut.model_validate(e) for e in ledger])

    def create_budget(self, principal: Principal, data: BudgetCreate) -> Budget:
        ensure_permission(principal, Perm.FINANCE_BUDGETS_MANAGE)
        if self.session.get(BudgetCategory, data.category_id) is None:
            raise BusinessRuleViolation("Choose a budget category.", code="invalid_category")
        if data.department_id:
            self._active_department(data.department_id)
        if data.project_id and self.session.get(OperationalProject, data.project_id) is None:
            raise BusinessRuleViolation("Choose an operational project.", code="invalid_project")
        budget = Budget(
            fiscal_year=data.fiscal_year,
            category_id=data.category_id,
            department_id=data.department_id,
            project_id=data.project_id,
            allocated_amount=q2(data.allocated_amount),
            notes=data.notes,
        )
        self.session.add(budget)
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise Conflict("A budget for this scope, category and year already exists.", code="budget_exists") from exc
        self.audit.record(
            "finance.budget_created",
            actor_user_id=principal.user_id,
            entity_type="budget",
            entity_id=budget.id,
            summary=f"FY{budget.fiscal_year} allocation SAR {budget.allocated_amount}",
            changes={"allocated_amount": str(budget.allocated_amount)},
        )
        self.session.commit()
        return budget

    def update_budget(self, principal: Principal, budget_id: uuid.UUID, data: BudgetUpdate) -> Budget:
        ensure_permission(principal, Perm.FINANCE_BUDGETS_MANAGE)
        budget = self.lock_budget(budget_id)
        changes: dict[str, object] = {}
        if data.allocated_amount is not None and q2(data.allocated_amount) != budget.allocated_amount:
            pos = self.position(budget_id)
            new = q2(data.allocated_amount)
            if new + pos.adjustments < pos.used:
                raise BusinessRuleViolation(
                    f"The allocation can't be lower than what is already committed and spent (SAR {pos.used}).",
                    code="allocation_below_usage",
                    details={"fields": [{"field": "allocated_amount", "message": f"Must be at least SAR {pos.used - pos.adjustments}."}]},
                )
            changes["allocated_amount"] = [str(budget.allocated_amount), str(new)]
            budget.allocated_amount = new
        if data.status and data.status != budget.status:
            changes["status"] = [budget.status, data.status]
            budget.status = data.status
        if "notes" in data.model_fields_set:
            budget.notes = data.notes
        self.audit.record(
            "finance.budget_updated",
            actor_user_id=principal.user_id,
            entity_type="budget",
            entity_id=budget.id,
            changes=changes or None,
            summary=f"FY{budget.fiscal_year} budget updated",
        )
        self.session.commit()
        return budget

    def summary(self, principal: Principal, fiscal_year: int) -> BudgetSummary:
        ensure_permission(principal, Perm.FINANCE_BUDGETS_READ)
        rows = self.session.execute(self._budget_query().where(Budget.fiscal_year == fiscal_year, Budget.status == "active")).unique().all()
        outs = [self._budget_out(*r) for r in rows]
        allocated = q2(sum((b.position.allocated + b.position.adjustments for b in outs), ZERO))
        committed = q2(sum((b.position.committed for b in outs), ZERO))
        actual = q2(sum((b.position.actual for b in outs), ZERO))
        pos = BudgetPosition(allocated, ZERO, committed, actual)
        by_dept: dict[uuid.UUID, DepartmentSpend] = {}
        for b in outs:
            d = b.owner_department
            cur = by_dept.get(d.id) or DepartmentSpend(department=d, allocated=ZERO, committed=ZERO, available=ZERO)
            by_dept[d.id] = DepartmentSpend(
                department=d,
                allocated=q2(cur.allocated + b.position.allocated + b.position.adjustments),
                committed=q2(cur.committed + b.position.committed + b.position.actual),
                available=q2(cur.available + b.position.available),
            )
        return BudgetSummary(
            fiscal_year=fiscal_year,
            budget_count=len(outs),
            allocated=allocated,
            committed=committed,
            actual=actual,
            available=pos.available,
            utilisation_pct=pos.utilisation_pct,
            over_threshold_count=sum(1 for b in outs if b.position.utilisation_pct >= ALERT_THRESHOLD),
            by_department=sorted(by_dept.values(), key=lambda x: x.allocated, reverse=True),
        )

    # --- helpers --------------------------------------------------------------------------------------
    def _budget_out(self, b: Budget, adj, com, act) -> BudgetOut:
        pos = BudgetPosition(b.allocated_amount, Decimal(adj or 0), Decimal(com or 0), Decimal(act or 0))
        owner = b.department if b.department else b.project.department  # type: ignore[union-attr]
        return BudgetOut(
            id=b.id,
            fiscal_year=b.fiscal_year,
            status=b.status,
            scope="department" if b.department_id else "project",
            category=CategoryOut.model_validate(b.category),
            department=DepartmentRef.model_validate(b.department) if b.department else None,
            project=ProjectRef.model_validate(b.project) if b.project else None,
            owner_department=DepartmentRef.model_validate(owner),
            notes=b.notes,
            position=pos.out(),
        )

    def _project_totals(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[Decimal, Decimal, Decimal]]:
        if not ids:
            return {}
        rows = self.session.execute(self._budget_query().where(Budget.project_id.in_(ids), Budget.status == "active")).unique().all()
        out: dict[uuid.UUID, tuple[Decimal, Decimal, Decimal]] = {}
        for b, adj, com, act in rows:
            pos = BudgetPosition(b.allocated_amount, Decimal(adj or 0), Decimal(com or 0), Decimal(act or 0))
            a, c, v = out.get(b.project_id, (ZERO, ZERO, ZERO))
            out[b.project_id] = (q2(a + pos.capacity), q2(c + pos.used), q2(v + pos.available))
        return out

    def _project_out(self, p: OperationalProject, totals: tuple[Decimal, Decimal, Decimal] | None) -> ProjectOut:
        a, c, v = totals or (ZERO, ZERO, ZERO)
        return ProjectOut(
            id=p.id,
            code=p.code,
            name=p.name,
            description=p.description,
            status=p.status,
            start_date=p.start_date,
            end_date=p.end_date,
            department=DepartmentRef.model_validate(p.department),
            manager=EmployeeRef.model_validate(p.manager) if p.manager else None,
            allocated_total=a,
            committed_total=c,
            available_total=v,
        )

    def _active_department(self, department_id: uuid.UUID) -> Department:
        d = self.session.get(Department, department_id)
        if d is None or not d.is_active:
            raise BusinessRuleViolation("Choose an active department.", code="invalid_department")
        return d

    def _active_employee(self, employee_id: uuid.UUID) -> uuid.UUID:
        e = self.session.get(Employee, employee_id)
        if e is None or not e.is_active:
            raise BusinessRuleViolation("Choose an active employee.", code="invalid_employee")
        return e.id


__all__ = ["FinanceService", "BudgetPosition", "BudgetCheck", "paginate"]
