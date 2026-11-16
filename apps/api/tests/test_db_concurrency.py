"""Real concurrency: two approvers race on the same step through separate connections with committed data.

Exactly one decision may win, and the budget may receive exactly one commitment. Uses committed rows
(unlike the rest of the suite) and truncates every table afterwards.
"""

from __future__ import annotations

import threading
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from app.core.errors import AppError
from app.core.security import hash_password
from app.modules.approvals.models import ApprovalDecision, ApprovalRequest
from app.modules.approvals.service import ApprovalService
from app.modules.finance.models import Budget, BudgetCategory, BudgetLedgerEntry
from app.modules.hr.models import Department, Employee
from app.modules.identity.models import User
from app.modules.identity.service import build_principal
from app.modules.procurement.models import Supplier
from app.modules.procurement.schemas import ItemIn, QuotationIn, QuotationItemIn, RequestCreate
from app.modules.procurement.service import ProcurementService
from app.seed.__main__ import sync_permissions, sync_roles
from app.seed.reference import seed_reference

pytestmark = pytest.mark.db


@pytest.fixture
def committed(engine):
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    yield maker
    with engine.begin() as conn:
        tables = [
            r[0] for r in conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version'"))
        ]
        conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))


def _setup(maker) -> tuple[uuid.UUID, uuid.UUID, dict[str, uuid.UUID]]:
    with maker() as s:
        perms = sync_permissions(s)
        roles = sync_roles(s, perms)
        seed_reference(s)
        pw = hash_password("x" * 12)
        users = {
            k: User(email=f"{k}@race.demo", password_hash=pw, full_name=k.title(), roles=[roles[r]])
            for k, r in {
                "eng": "employee",
                "head": "department_manager",
                "buyer": "procurement_officer",
                "fin1": "finance_manager",
                "fin2": "finance_manager",
            }.items()
        }
        s.add_all(users.values())
        dept = Department(code="RACE", name="Race dept")
        s.add(dept)
        s.flush()
        head = Employee(employee_no="R-1", full_name="Head", job_title="Head", department_id=dept.id, user_id=users["head"].id)
        eng = Employee(employee_no="R-2", full_name="Eng", job_title="Eng", department_id=dept.id, user_id=users["eng"].id)
        s.add_all([head, eng])
        s.flush()
        dept.manager_employee_id = head.id
        cat = s.scalar(select(BudgetCategory).where(BudgetCategory.code == "EQUIP"))
        budget = Budget(fiscal_year=date.today().year, category_id=cat.id, department_id=dept.id, allocated_amount=Decimal("500000"))
        sup = Supplier(code="SUP-R1", name="Race supplier", category="Materials")
        s.add_all([budget, sup])
        s.commit()

        P = lambda k: build_principal(s.get(User, users[k].id))  # noqa: E731
        svc = ProcurementService(s)
        pr = svc.create_request(
            P("eng"),
            RequestCreate(
                title="Race test",
                justification="Concurrency test request.",
                department_id=dept.id,
                category_id=cat.id,
                items=[ItemIn(description="Pump", quantity=Decimal("1"), estimated_unit_price=Decimal("80000"))],
            ),
        )
        svc.submit(P("eng"), pr.id)
        detail = svc.detail(P("buyer"), pr.id)
        svc.add_quotation(
            P("buyer"),
            pr.id,
            QuotationIn(supplier_id=sup.id, items=[QuotationItemIn(request_item_id=detail.items[0].id, unit_price=Decimal("75000"))]),
        )
        svc.select_quotation(P("buyer"), pr.id, svc.detail(P("buyer"), pr.id).quotations[0].id)
        svc.send_for_approval(P("buyer"), pr.id)
        approval = ApprovalService(s).latest_for_entity("purchase_request", pr.id)
        ApprovalService(s).approve(P("head"), approval.id, None)  # department step; finance step is now open to fin1 and fin2
        return approval.id, budget.id, {k: u.id for k, u in users.items()}


def test_concurrent_final_approvals_commit_once(committed):
    approval_id, budget_id, users = _setup(committed)
    barrier = threading.Barrier(2)
    results: dict[str, str] = {}

    def decide(key: str) -> None:
        with committed() as s:
            principal = build_principal(s.get(User, users[key]))
            barrier.wait()
            try:
                ApprovalService(s).approve(principal, approval_id, f"approved by {key}")
                results[key] = "ok"
            except AppError as exc:
                results[key] = exc.code

    threads = [threading.Thread(target=decide, args=(k,)) for k in ("fin1", "fin2")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sorted(results.values()) == ["already_decided", "ok"], results
    with committed() as s:
        assert s.get(ApprovalRequest, approval_id).status == "approved"
        assert (
            len(s.scalars(select(ApprovalDecision).where(ApprovalDecision.request_id == approval_id)).all()) == 2
        )  # department + one finance
        entries = s.scalars(select(BudgetLedgerEntry).where(BudgetLedgerEntry.budget_id == budget_id)).all()
        assert [(e.entry_type, e.amount) for e in entries] == [("commitment", Decimal("75000.00"))]
