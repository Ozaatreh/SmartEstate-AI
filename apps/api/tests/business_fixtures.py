"""A small organisation for business-operation tests (built per test inside the rolled-back transaction)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.finance.models import Budget, BudgetCategory, OperationalProject
from app.modules.hr.models import Department, Employee
from app.modules.identity.models import User
from app.modules.procurement.models import Supplier
from app.seed.reference import seed_reference
from tests.conftest import CSRF, TEST_PASSWORD

YEAR = date.today().year


@dataclass
class Org:
    users: dict[str, User] = field(default_factory=dict)
    employees: dict[str, Employee] = field(default_factory=dict)
    depts: dict[str, Department] = field(default_factory=dict)
    cats: dict[str, BudgetCategory] = field(default_factory=dict)
    budgets: dict[str, Budget] = field(default_factory=dict)
    suppliers: list[Supplier] = field(default_factory=list)
    project: OperationalProject | None = None


@pytest.fixture
def org(db: Session, make_user, roles) -> Org:
    seed_reference(db)
    o = Org()
    spec = {  # key: (role, department, manager key)
        "ceo": ("executive", "EXEC", None),
        "cfo": ("finance_manager", "FIN", "ceo"),
        "head": ("department_manager", "CONST", "ceo"),
        "eng": ("employee", "CONST", "head"),
        "buyer": ("procurement_officer", "PROC", "ceo"),
        "hr": ("hr_manager", "HR", "ceo"),
        "outsider": ("employee", "HR", "hr"),
    }
    for code in ("EXEC", "FIN", "CONST", "PROC", "HR"):
        o.depts[code] = Department(code=code, name=f"{code} department")
    db.add_all(o.depts.values())
    db.flush()
    for i, (key, (role, dept, _)) in enumerate(spec.items(), start=1):
        o.users[key] = make_user(role, name=f"{key.capitalize()} Person")
        o.employees[key] = Employee(
            employee_no=f"T-{i:03d}",
            full_name=f"{key.capitalize()} Person",
            job_title=role.replace("_", " ").title(),
            department_id=o.depts[dept].id,
            user_id=o.users[key].id,
        )
    db.add_all(o.employees.values())
    db.flush()
    for key, (_, _, mgr) in spec.items():
        o.employees[key].manager_id = o.employees[mgr].id if mgr else None
    for code, key in (("EXEC", "ceo"), ("FIN", "cfo"), ("CONST", "head"), ("PROC", "buyer"), ("HR", "hr")):
        o.depts[code].manager_employee_id = o.employees[key].id
    db.flush()
    o.cats = {c.code: c for c in db.query(BudgetCategory)}
    o.project = OperationalProject(code="OP-T01", name="Test infrastructure", department_id=o.depts["CONST"].id, status="active")
    db.add(o.project)
    db.flush()
    o.budgets["equip"] = Budget(
        fiscal_year=YEAR, category_id=o.cats["EQUIP"].id, department_id=o.depts["CONST"].id, allocated_amount=Decimal("100000.00")
    )
    o.budgets["project"] = Budget(
        fiscal_year=YEAR, category_id=o.cats["CAPEX-CONSTR"].id, project_id=o.project.id, allocated_amount=Decimal("1000000.00")
    )
    db.add_all(o.budgets.values())
    o.suppliers = [Supplier(code=f"SUP-T{i}", name=f"Supplier {i}", category="Materials", rating=Decimal("4.0")) for i in range(1, 4)]
    db.add_all(o.suppliers)
    db.commit()
    return o


class Actor:
    """A logged-in TestClient for one org user (fresh client so cookies don't mix)."""

    def __init__(self, app, user: User):
        self.client = TestClient(app, base_url="http://127.0.0.1")
        r = self.client.post("/api/v1/auth/login", json={"email": user.email, "password": TEST_PASSWORD}, headers=CSRF)
        assert r.status_code == 200, r.text
        self.user = user

    def get(self, path, **kw):
        return self.client.get("/api/v1" + path, **kw)

    def post(self, path, json=None):
        return self.client.post("/api/v1" + path, json=json if json is not None else {}, headers=CSRF)

    def patch(self, path, json):
        return self.client.patch("/api/v1" + path, json=json, headers=CSRF)

    def put(self, path, json):
        return self.client.put("/api/v1" + path, json=json, headers=CSRF)

    def delete(self, path):
        return self.client.delete("/api/v1" + path, headers=CSRF)


@pytest.fixture
def as_(app, org):
    cache: dict[str, Actor] = {}

    def _get(key: str) -> Actor:
        if key not in cache:
            cache[key] = Actor(app, org.users[key])
        return cache[key]

    return _get


def request_body(
    org: Org, *, items=(("Item A", "10", "unit", "1000.00"),), project: bool = False, category: str = "EQUIP", dept: str = "CONST"
) -> dict:
    return {
        "title": "Test request",
        "justification": "Needed for testing the purchase flow.",
        "department_id": str(org.depts[dept].id),
        "category_id": str(org.cats[category].id),
        "project_id": str(org.project.id) if project else None,
        "fiscal_year": YEAR,
        "priority": "normal",
        "items": [{"description": d, "quantity": q, "unit": u, "estimated_unit_price": p} for d, q, u, p in items],
    }


def quotation_body(detail: dict, supplier: Supplier, prices: list[str], days: int = 7) -> dict:
    return {
        "supplier_id": str(supplier.id),
        "reference": f"Q-{supplier.code}",
        "delivery_days": days,
        "items": [{"request_item_id": i["id"], "unit_price": p} for i, p in zip(detail["items"], prices, strict=True)],
    }


def to_approval(
    as_,
    org,
    *,
    unit_price: str = "1000.00",
    qty: str = "10",
    project: bool = False,
    category: str = "EQUIP",
    requester: str = "eng",
    dept: str = "CONST",
) -> tuple[dict, str]:
    """Create → submit → quote → select → send. Returns (request detail, approval id)."""
    r = as_(requester).post(
        "/procurement/requests",
        request_body(org, items=(("Item A", qty, "unit", unit_price),), project=project, category=category, dept=dept),
    )
    assert r.status_code == 201, r.text
    pr = r.json()
    assert as_(requester).post(f"/procurement/requests/{pr['id']}/submit").status_code == 200
    d = as_("buyer").post(f"/procurement/requests/{pr['id']}/quotations", quotation_body(pr, org.suppliers[0], [unit_price])).json()
    q = d["quotations"][0]["id"]
    assert as_("buyer").post(f"/procurement/requests/{pr['id']}/quotations/{q}/select").status_code == 200
    r = as_("buyer").post(f"/procurement/requests/{pr['id']}/send-for-approval")
    assert r.status_code == 200, r.text
    detail = r.json()
    return detail, detail["approval"]["id"]
