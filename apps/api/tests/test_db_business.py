"""Phase 2 integration tests on PostgreSQL: HR, finance, procurement, approvals and the full PR lifecycle."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.modules.approvals.models import ApprovalDecision
from app.modules.audit.models import AuditLog
from app.modules.finance.models import BudgetLedgerEntry
from app.modules.finance.service import FinanceService
from app.modules.notifications.models import Notification
from tests.business_fixtures import YEAR, quotation_body, request_body, to_approval

pytestmark = pytest.mark.db


# ===================================================================================== HR
def test_directory_requires_permission_and_supports_search(as_, org, make_user, app):
    from tests.business_fixtures import Actor

    r = as_("eng").get("/hr/employees", params={"q": "Head"})
    assert r.status_code == 200 and [e["full_name"] for e in r.json()["items"]] == ["Head Person"]
    nobody = Actor(app, make_user(None))  # user without any role
    assert nobody.get("/hr/employees").status_code == 403


def test_employee_profile_shows_reporting_line_and_reports(as_, org):
    eng = as_("eng").get(f"/hr/employees/{org.employees['eng'].id}").json()
    assert [m["full_name"] for m in eng["reporting_line"]] == ["Head Person", "Ceo Person"]
    head = as_("eng").get(f"/hr/employees/{org.employees['head'].id}").json()
    assert [r["full_name"] for r in head["direct_reports"]] == ["Eng Person"]
    assert head["manages_departments"][0]["code"] == "CONST"


def test_hr_writes_need_hr_permission(as_, org):
    body = {
        "full_name": "New Hire",
        "job_title": "Site Engineer",
        "department_id": str(org.depts["CONST"].id),
        "manager_id": str(org.employees["head"].id),
        "email": "new.hire@smartestate.demo",
    }
    assert as_("eng").post("/hr/employees", body).status_code == 403
    r = as_("hr").post("/hr/employees", body)
    assert r.status_code == 201 and r.json()["employee_no"].startswith("EMP-") and r.json()["manager"]["full_name"] == "Head Person"
    assert as_("hr").post("/hr/employees", body).json()["error"]["code"] == "employee_email_exists"


def test_reporting_cycles_are_rejected(as_, org):
    r = as_("hr").patch(f"/hr/employees/{org.employees['head'].id}", {"manager_id": str(org.employees["eng"].id)})
    assert r.status_code == 422 and r.json()["error"]["code"] == "reporting_cycle"
    r = as_("hr").patch(f"/hr/employees/{org.employees['eng'].id}", {"manager_id": str(org.employees["eng"].id)})
    assert r.status_code == 422


def test_departments_list_headcount_and_manager(as_, org):
    depts = {d["code"]: d for d in as_("eng").get("/hr/departments").json()}
    assert depts["CONST"]["headcount"] == 2 and depts["CONST"]["manager"]["full_name"] == "Head Person"
    assert as_("eng").post("/hr/departments", {"code": "IT", "name": "IT"}).status_code == 403
    assert as_("hr").post("/hr/departments", {"code": "it", "name": "Information Technology"}).json()["code"] == "IT"


# ===================================================================================== finance
def test_budget_position_and_idempotent_commitment(db, org):
    fin = FinanceService(db)
    budget = org.budgets["equip"]
    kw = dict(
        budget_id=budget.id,
        amount=Decimal("12345.67"),
        source_type="test",
        source_id=budget.id,
        source_code="T",
        actor_user_id=None,
        description="test",
    )
    e1 = fin.commit(**kw)
    e2 = fin.commit(**kw)  # retried posting → same entry, no second financial effect
    assert e1.id == e2.id
    assert db.scalar(select(text("count(*)")).select_from(BudgetLedgerEntry)) == 1
    pos = fin.position(budget.id)
    assert (pos.allocated, pos.committed, pos.available) == (Decimal("100000.00"), Decimal("12345.67"), Decimal("87654.33"))
    assert pos.utilisation_pct == Decimal("12.3")
    fin.release(**{**kw, "amount": Decimal("345.67")})
    assert fin.position(budget.id).available == Decimal("88000.00")


def test_ledger_is_append_only(db, org):
    FinanceService(db).commit(
        budget_id=org.budgets["equip"].id,
        amount=Decimal("10"),
        source_type="t",
        source_id=org.budgets["equip"].id,
        source_code="T",
        actor_user_id=None,
        description="x",
    )
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("UPDATE budget_ledger_entries SET amount = 1"))
    db.rollback()


def test_budget_api_rbac_duplicates_and_allocation_floor(as_, org, db):
    body = {
        "fiscal_year": YEAR,
        "category_id": str(org.cats["EQUIP"].id),
        "department_id": str(org.depts["CONST"].id),
        "allocated_amount": "5000.00",
    }
    assert as_("eng").get("/finance/budgets").status_code == 403
    assert as_("head").post("/finance/budgets", body).status_code == 403  # read-only role
    assert as_("cfo").post("/finance/budgets", body).json()["error"]["code"] == "budget_exists"
    both = {**body, "project_id": str(org.project.id)}
    assert as_("cfo").post("/finance/budgets", both).status_code == 422
    FinanceService(db).commit(
        budget_id=org.budgets["equip"].id,
        amount=Decimal("60000"),
        source_type="t",
        source_id=org.budgets["equip"].id,
        source_code="T",
        actor_user_id=None,
        description="x",
    )
    db.commit()
    r = as_("cfo").patch(f"/finance/budgets/{org.budgets['equip'].id}", {"allocated_amount": "50000.00"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "allocation_below_usage"
    r = as_("cfo").patch(f"/finance/budgets/{org.budgets['equip'].id}", {"allocated_amount": "150000.00"})
    assert r.status_code == 200 and r.json()["position"]["available"] == "90000.00"


def test_budget_summary_totals(as_, org):
    s = as_("cfo").get("/finance/budgets/summary", params={"fiscal_year": YEAR}).json()
    assert s["budget_count"] == 2 and s["allocated"] == "1100000.00" and s["available"] == "1100000.00"


# ===================================================================================== procurement
def test_request_validation_and_exact_totals(as_, org):
    bad = request_body(org, items=())
    assert as_("eng").post("/procurement/requests", bad).status_code == 422
    r = as_("eng").post(
        "/procurement/requests", request_body(org, items=(("Cable", "3.333", "m", "0.15"), ("Pipe", "2", "unit", "1999.99")))
    )
    d = r.json()
    assert r.status_code == 201 and d["status"] == "draft" and d["code"].startswith("PR-")
    assert [i["line_total"] for i in d["items"]] == ["0.50", "3999.98"] and d["estimated_total"] == "4000.48"
    assert as_("outsider").get(f"/procurement/requests/{d['id']}").status_code == 404  # not visible to unrelated staff


def test_submit_requires_an_existing_budget(as_, org):
    pr = as_("eng").post("/procurement/requests", request_body(org, category="IT")).json()
    r = as_("eng").post(f"/procurement/requests/{pr['id']}/submit")
    assert r.status_code == 422 and r.json()["error"]["code"] == "budget_not_found"


def test_only_procurement_manages_quotations(as_, org):
    pr = as_("eng").post("/procurement/requests", request_body(org)).json()
    as_("eng").post(f"/procurement/requests/{pr['id']}/submit")
    r = as_("eng").post(f"/procurement/requests/{pr['id']}/quotations", quotation_body(pr, org.suppliers[0], ["900.00"]))
    assert r.status_code == 403
    r = as_("buyer").post(f"/procurement/requests/{pr['id']}/quotations", {**quotation_body(pr, org.suppliers[0], ["900.00"]), "items": []})
    assert r.status_code == 422


def test_quotation_comparison_and_selection(as_, org):
    pr = (
        as_("eng")
        .post("/procurement/requests", request_body(org, items=(("Item A", "2", "unit", "100.00"), ("Item B", "1", "unit", "50.00"))))
        .json()
    )
    as_("eng").post(f"/procurement/requests/{pr['id']}/submit")
    as_("buyer").post(f"/procurement/requests/{pr['id']}/quotations", quotation_body(pr, org.suppliers[0], ["90.00", "60.00"], days=10))
    d = (
        as_("buyer")
        .post(f"/procurement/requests/{pr['id']}/quotations", quotation_body(pr, org.suppliers[1], ["95.00", "40.00"], days=3))
        .json()
    )
    dup = as_("buyer").post(f"/procurement/requests/{pr['id']}/quotations", quotation_body(pr, org.suppliers[1], ["1.00", "1.00"]))
    assert dup.status_code == 409
    totals = {q["supplier"]["name"]: q["total_amount"] for q in d["quotations"]}
    assert totals == {"Supplier 1": "240.00", "Supplier 2": "230.00"}
    cmp = d["comparison"]
    lowest = next(q for q in d["quotations"] if q["is_lowest"])
    assert cmp["lowest_quotation_id"] == lowest["id"] == cmp["fastest_quotation_id"] and cmp["savings_vs_estimate"] == "20.00"
    assert [c["is_lowest"] for c in cmp["rows"][0]["cells"]] == [True, False]
    assert "send_for_approval" not in d["allowed_actions"]
    d = as_("buyer").post(f"/procurement/requests/{pr['id']}/quotations/{lowest['id']}/select").json()
    assert d["selected_quotation_id"] == lowest["id"] and d["approved_total"] == "230.00" and "send_for_approval" in d["allowed_actions"]
    other = next(q for q in d["quotations"] if q["id"] != lowest["id"])["id"]
    d = as_("buyer").post(f"/procurement/requests/{pr['id']}/quotations/{other}/select").json()
    assert [q["status"] for q in d["quotations"]].count("selected") == 1


# ===================================================================================== approvals
@pytest.mark.parametrize(
    ("unit_price", "levels"),
    [
        ("4000.00", ["department"]),  # 40,000 ≤ 50,000
        ("5000.00", ["department"]),  # exactly 50,000 stays in the first band
        ("6000.00", ["department", "finance"]),  # 60,000
        ("9999.00", ["department", "finance"]),  # 99,990 (over the 100k budget? no)
    ],
)
def test_approval_thresholds(as_, org, unit_price, levels):
    detail, _ = to_approval(as_, org, unit_price=unit_price)
    assert [s["level"] for s in detail["approval"]["steps"]] == levels


def test_executive_threshold_on_project_budget(as_, org):
    detail, _ = to_approval(as_, org, unit_price="30000.00", project=True, category="CAPEX-CONSTR")  # 300,000
    assert [s["level"] for s in detail["approval"]["steps"]] == ["department", "finance", "executive"]
    assert detail["budget_impact"]["scope_label"].startswith("OP-T01")


def test_over_budget_escalates_to_finance_and_executive(as_, org):
    detail, _ = to_approval(as_, org, unit_price="12000.00")  # 120,000 > 100,000 budget
    assert detail["over_budget"] is True and detail["budget_impact"]["over_budget"] is True
    assert [s["level"] for s in detail["approval"]["steps"]] == ["department", "finance", "executive"]


def test_requester_cannot_approve_and_escalation_when_requester_is_manager(as_, org):
    detail, approval = to_approval(as_, org, requester="head")
    step = detail["approval"]["steps"][0]
    assert step["assignee"]["full_name"] == "Ceo Person" and "Requester manages the department" in step["escalation_reason"]
    r = as_("head").post(f"/approvals/{approval}/approve", {})
    assert r.status_code == 404 or r.json()["error"]["code"] == "not_eligible_approver"
    assert as_("ceo").post(f"/approvals/{approval}/approve", {"comment": "ok"}).status_code == 200


def test_department_without_manager_goes_to_pool(as_, org, db):
    org.depts["CONST"].manager_employee_id = None
    db.commit()
    detail, approval = to_approval(as_, org)
    step = detail["approval"]["steps"][0]
    assert step["assignee"] is None and step["pool_label"] == "Department approvers"
    assert as_("head").post(f"/approvals/{approval}/approve", {}).status_code in (403, 404)


def test_one_person_decides_at_most_one_step(as_, org, db):
    from app.modules.identity.models import Role

    # The department head also holds finance approval rights.
    org.users["head"].roles.append(db.scalar(select(Role).where(Role.code == "finance_manager")))
    db.commit()
    _, approval = to_approval(as_, org, unit_price="6000.00")
    assert as_("head").post(f"/approvals/{approval}/approve", {}).status_code == 200
    r = as_("head").post(f"/approvals/{approval}/approve", {})
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_eligible_approver"
    assert as_("cfo").post(f"/approvals/{approval}/approve", {}).status_code == 200


def test_decisions_cannot_be_duplicated(as_, org, db):
    _, approval = to_approval(as_, org)
    assert as_("head").post(f"/approvals/{approval}/approve", {}).status_code == 200
    r = as_("head").post(f"/approvals/{approval}/approve", {})
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_decided"
    decision = db.scalar(select(ApprovalDecision))
    db.add(ApprovalDecision(step_id=decision.step_id, request_id=decision.request_id, decided_by=org.users["cfo"].id, decision="approved"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_reject_requires_comment_and_commits_nothing(as_, org, db):
    detail, approval = to_approval(as_, org)
    assert as_("head").post(f"/approvals/{approval}/reject", {"comment": ""}).status_code == 422
    r = as_("head").post(f"/approvals/{approval}/reject", {"comment": "Use existing stock first."})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    pr = as_("eng").get(f"/procurement/requests/{detail['id']}").json()
    assert pr["status"] == "rejected" and pr["approval"]["steps"][0]["decision"]["comment"] == "Use existing stock first."
    assert db.scalar(select(text("count(*)")).select_from(BudgetLedgerEntry)) == 0


def test_inbox_counts_and_visibility(as_, org):
    _, approval = to_approval(as_, org, unit_price="6000.00")
    assert as_("head").get("/approvals/pending-count").json() == {"pending": 1}
    assert as_("cfo").get("/approvals/pending-count").json() == {"pending": 0}  # finance step not active yet
    assert as_("eng").get("/approvals", params={"box": "pending"}).json()["total"] == 0
    assert as_("eng").get("/approvals", params={"box": "mine"}).json()["total"] == 1
    assert as_("eng").get("/approvals", params={"box": "all"}).status_code == 403
    as_("head").post(f"/approvals/{approval}/approve", {})
    assert as_("cfo").get("/approvals/pending-count").json() == {"pending": 1}
    assert as_("outsider").get(f"/approvals/{approval}").status_code == 404


# ===================================================================================== end-to-end lifecycle
def test_purchase_request_lifecycle_end_to_end(as_, org, db):
    eng, buyer, head, cfo = as_("eng"), as_("buyer"), as_("head"), as_("cfo")

    # 1–2. Employee creates a request; the system validates it.
    pr = eng.post(
        "/procurement/requests",
        request_body(org, items=(("Formwork panels", "50", "unit", "1200.00"), ("Ties and clamps", "10", "box", "350.50"))),
    ).json()
    assert pr["status"] == "draft" and pr["estimated_total"] == "63505.00" and pr["allowed_actions"] == ["edit", "submit", "cancel"]

    # 3. Budget check at submission.
    pr = eng.post(f"/procurement/requests/{pr['id']}/submit").json()
    assert pr["status"] == "sourcing" and pr["budget_impact"]["found"] and pr["budget_impact"]["available_after"] == "36495.00"
    assert pr["budget_impact"]["approval_levels"] == ["Department manager", "Finance"]
    assert eng.post(f"/procurement/requests/{pr['id']}/submit").status_code == 409

    # 4. Procurement manages quotations.
    buyer.post(f"/procurement/requests/{pr['id']}/quotations", quotation_body(pr, org.suppliers[0], ["1150.00", "300.00"]))
    pr = buyer.post(f"/procurement/requests/{pr['id']}/quotations", quotation_body(pr, org.suppliers[1], ["1180.00", "340.00"])).json()
    best = pr["comparison"]["lowest_quotation_id"]
    pr = buyer.post(f"/procurement/requests/{pr['id']}/quotations/{best}/select").json()
    assert pr["approved_total"] == "60500.00"

    # 5. Authorised approvers receive it.
    pr = buyer.post(f"/procurement/requests/{pr['id']}/send-for-approval").json()
    approval = pr["approval"]["id"]
    assert pr["status"] == "pending_approval" and [s["status"] for s in pr["approval"]["steps"]] == ["pending", "waiting"]
    assert db.scalar(select(Notification).where(Notification.user_id == org.users["head"].id, Notification.type == "approval.requested"))
    assert buyer.post(f"/procurement/requests/{pr['id']}/quotations/{best}/select").status_code == 409  # locked after sending

    # 6. Managers approve (department, then finance).
    assert head.post(f"/approvals/{approval}/approve", {"comment": "Needed for the podium pour."}).status_code == 200
    assert cfo.get("/approvals", params={"box": "pending"}).json()["items"][0]["entity_code"] == pr["code"]
    final = cfo.post(f"/approvals/{approval}/approve", {}).json()
    assert final["status"] == "approved" and final["allowed_actions"] == []

    # 8. Request status and financial records are consistent.
    pr = eng.get(f"/procurement/requests/{pr['id']}").json()
    assert pr["status"] == "approved" and pr["budget_impact"]["committed_by_this_request"]
    ledger = db.scalars(
        select(BudgetLedgerEntry).where(BudgetLedgerEntry.source_id == pr["id"]) if False else select(BudgetLedgerEntry)
    ).all()
    assert [(e.entry_type, e.amount, e.source_code) for e in ledger] == [("commitment", Decimal("60500.00"), pr["code"])]
    budget = cfo.get(f"/finance/budgets/{org.budgets['equip'].id}").json()
    assert budget["position"]["committed"] == "60500.00" and budget["position"]["available"] == "39500.00"
    assert head.post(f"/approvals/{approval}/approve", {}).status_code == 409  # no second commitment possible

    # 7. Every action is in the audit trail, in order.
    actions = [a["action"] for a in reversed(eng.get(f"/procurement/requests/{pr['id']}/activity").json())]
    assert actions == [
        "purchase_request.created",
        "purchase_request.submitted",
        "purchase_request.quotation_added",
        "purchase_request.quotation_added",
        "purchase_request.quotation_selected",
        "approval.requested",
        "purchase_request.sent_for_approval",
        "approval.step_approved",
        "approval.step_approved",
        "approval.completed",
        "purchase_request.approved",
    ]
    assert db.scalar(select(AuditLog).where(AuditLog.action == "purchase_request.approved")).changes["committed"] == "60500.00"
    notes = {n.type for n in db.scalars(select(Notification).where(Notification.user_id == org.users["eng"].id))}
    assert {"approval.progress", "approval.approved"} <= notes


def test_cancel_rules(as_, org):
    pr = as_("eng").post("/procurement/requests", request_body(org)).json()
    assert as_("eng").post(f"/procurement/requests/{pr['id']}/cancel", {"reason": "no"}).status_code == 422  # reason too short
    assert as_("eng").post(f"/procurement/requests/{pr['id']}/cancel", {"reason": "Not needed anymore"}).json()["status"] == "cancelled"
    detail, _ = to_approval(as_, org)
    assert as_("eng").post(f"/procurement/requests/{detail['id']}/cancel", {"reason": "Changed my mind"}).status_code == 409
