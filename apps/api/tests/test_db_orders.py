"""Purchase orders (Phase 4): population, lifecycle, single commitment / single release, RBAC, audit, events."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.automation.models import AutomationEvent
from app.modules.audit.models import AuditLog
from app.modules.finance.models import BudgetLedgerEntry
from app.modules.procurement.models import PurchaseOrder
from tests.business_fixtures import quotation_body, request_body

pytestmark = pytest.mark.db


def approved_request(as_, org, *, prices=("1000.00", "250.50"), qtys=("10", "4")) -> dict:
    """Two-line request quoted by two suppliers; the cheaper (supplier 2) is selected and approved by the department."""
    items = tuple((f"Item {i}", q, "unit", "1200.00") for i, q in enumerate(qtys, start=1))
    pr = as_("eng").post("/procurement/requests", request_body(org, items=items)).json()
    assert as_("eng").post(f"/procurement/requests/{pr['id']}/submit").status_code == 200
    buyer = as_("buyer")
    buyer.post(f"/procurement/requests/{pr['id']}/quotations", quotation_body(pr, org.suppliers[0], ["1100.00", "300.00"]))
    d = buyer.post(f"/procurement/requests/{pr['id']}/quotations", quotation_body(pr, org.suppliers[1], list(prices))).json()
    q = next(x for x in d["quotations"] if x["supplier"]["id"] == str(org.suppliers[1].id))
    assert buyer.post(f"/procurement/requests/{pr['id']}/quotations/{q['id']}/select").status_code == 200
    d = buyer.post(f"/procurement/requests/{pr['id']}/send-for-approval").json()
    assert as_("head").post(f"/approvals/{d['approval']['id']}/approve", {}).status_code == 200
    d = as_("buyer").get(f"/procurement/requests/{pr['id']}").json()
    assert d["status"] == "approved"
    return d


def ledger(db, org) -> list[tuple[str, Decimal]]:
    rows = db.scalars(
        select(BudgetLedgerEntry).where(BudgetLedgerEntry.budget_id == org.budgets["equip"].id).order_by(BudgetLedgerEntry.created_at)
    )
    return [(e.entry_type, e.amount) for e in rows]


def create(as_, pr, **body):
    return as_("buyer").post(f"/procurement/requests/{pr['id']}/purchase-orders", body)


def test_order_copies_selected_quotation_and_writes_no_ledger_entry(as_, org, db):
    pr = approved_request(as_, org)
    assert "create_purchase_order" in pr["allowed_actions"]
    assert ledger(db, org) == [("commitment", Decimal("11002.00"))]  # 10×1000 + 4×250.50

    r = create(as_, pr, expected_delivery_date="2026-12-20", delivery_address="NOVA site gate 2")
    assert r.status_code == 201, r.text
    po = r.json()
    assert po["code"].startswith("PO-") and po["status"] == "draft"
    assert po["supplier"]["id"] == str(org.suppliers[1].id) and po["request_code"] == pr["code"]
    assert po["total_amount"] == "11002.00" == pr["approved_total"] == po["committed_amount"]
    assert [(ln["description"], ln["quantity"], ln["unit_price"], ln["line_total"]) for ln in po["lines"]] == [
        ("Item 1", "10.000", "1000.00", "10000.00"),
        ("Item 2", "4.000", "250.50", "1002.00"),
    ]
    assert po["allowed_actions"] == ["edit", "issue", "cancel"] and po["released_amount"] is None

    r = as_("buyer").post(f"/procurement/purchase-orders/{po['id']}/issue")
    assert r.status_code == 200 and r.json()["status"] == "issued" and r.json()["issued_by"] == "Buyer Person"
    assert r.json()["allowed_actions"] == ["cancel"]
    assert ledger(db, org) == [("commitment", Decimal("11002.00"))]  # neither create nor issue touch the ledger

    detail = as_("eng").get(f"/procurement/requests/{pr['id']}").json()
    assert [o["code"] for o in detail["purchase_orders"]] == [po["code"]] and detail["status"] == "approved"
    assert "create_purchase_order" not in as_("buyer").get(f"/procurement/requests/{pr['id']}").json()["allowed_actions"]


def test_order_requires_fully_approved_request(as_, org):
    pr = as_("eng").post("/procurement/requests", request_body(org)).json()
    r = create(as_, pr)
    assert r.status_code == 409 and r.json()["error"]["code"] == "request_not_approved"


def test_only_one_active_order_per_request(as_, org, db):
    pr = approved_request(as_, org)
    assert create(as_, pr).status_code == 201
    r = create(as_, pr)
    assert r.status_code == 409 and r.json()["error"]["code"] == "active_order_exists"
    # The database enforces it too (partial unique index on active orders).
    first = db.scalar(select(PurchaseOrder).where(PurchaseOrder.request_id == pr["id"]))
    from sqlalchemy.exc import IntegrityError

    clone = PurchaseOrder(
        code="PO-X",
        request_id=first.request_id,
        quotation_id=first.quotation_id,
        supplier_id=first.supplier_id,
        budget_id=first.budget_id,
        total_amount=first.total_amount,
        created_by=first.created_by,
    )
    db.add(clone)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_edit_and_issue_only_from_draft(as_, org):
    pr = approved_request(as_, org)
    po = create(as_, pr).json()
    r = as_("buyer").patch(f"/procurement/purchase-orders/{po['id']}", {"delivery_address": "Gate 3", "payment_terms": "Net 45"})
    assert r.status_code == 200 and r.json()["delivery_address"] == "Gate 3" and r.json()["payment_terms"] == "Net 45"
    r = as_("buyer").patch(f"/procurement/purchase-orders/{po['id']}", {"total_amount": "1.00"})
    assert r.status_code == 422  # prices and lines are frozen copies of the approved quotation
    assert as_("buyer").post(f"/procurement/purchase-orders/{po['id']}/issue").status_code == 200
    r = as_("buyer").post(f"/procurement/purchase-orders/{po['id']}/issue")
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_state"
    assert as_("buyer").patch(f"/procurement/purchase-orders/{po['id']}", {"notes": "late"}).status_code == 409


def test_cancel_with_release_releases_once_and_closes_request(as_, org, db):
    pr = approved_request(as_, org)
    po = create(as_, pr).json()
    as_("buyer").post(f"/procurement/purchase-orders/{po['id']}/issue")
    before = as_("cfo").get(f"/finance/budgets/{org.budgets['equip'].id}").json()

    r = as_("buyer").post(f"/procurement/purchase-orders/{po['id']}/cancel", {"reason": "Supplier withdrew", "release_budget": True})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "cancelled" and out["budget_released"] and out["released_amount"] == "11002.00"
    assert out["request_status"] == "closed" and out["allowed_actions"] == []
    assert ledger(db, org) == [("commitment", Decimal("11002.00")), ("release", Decimal("-11002.00"))]
    after = as_("cfo").get(f"/finance/budgets/{org.budgets['equip'].id}").json()
    assert Decimal(after["position"]["available"]) == Decimal(before["position"]["available"]) + Decimal("11002.00")

    r = as_("buyer").post(f"/procurement/purchase-orders/{po['id']}/cancel", {"reason": "again", "release_budget": True})
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_cancelled"
    r = create(as_, pr)  # a closed request takes no further orders
    assert r.status_code == 409 and r.json()["error"]["code"] == "request_not_approved"
    assert len(ledger(db, org)) == 2


def test_cancel_keeping_budget_allows_linked_replacement(as_, org, db):
    pr = approved_request(as_, org)
    first = create(as_, pr).json()
    r = as_("buyer").post(f"/procurement/purchase-orders/{first['id']}/cancel", {"reason": "Wrong delivery site", "release_budget": False})
    assert r.status_code == 200 and not r.json()["budget_released"] and r.json()["request_status"] == "approved"
    assert ledger(db, org) == [("commitment", Decimal("11002.00"))]

    r = create(as_, pr, delivery_address="Correct site")
    assert r.status_code == 201
    second = r.json()
    assert second["replaces"] == {"id": first["id"], "code": first["code"]} and second["total_amount"] == "11002.00"
    assert as_("buyer").get(f"/procurement/purchase-orders/{first['id']}").json()["replaced_by"]["id"] == second["id"]

    r = as_("buyer").post(f"/procurement/purchase-orders/{second['id']}/cancel", {"reason": "Project paused", "release_budget": True})
    assert r.status_code == 200 and r.json()["request_status"] == "closed"
    assert ledger(db, org) == [("commitment", Decimal("11002.00")), ("release", Decimal("-11002.00"))]


def test_release_refused_while_another_active_order_needs_commitment(as_, org, db):
    """Guard for the (index-prevented) case of two active orders: release must not strand a live order."""
    from app.modules.identity.models import User
    from app.modules.identity.service import build_principal
    from app.modules.procurement.models import PurchaseRequest
    from app.modules.procurement.orders import OrderService

    pr = approved_request(as_, org)
    first = create(as_, pr).json()
    as_("buyer").post(f"/procurement/purchase-orders/{first['id']}/cancel", {"reason": "Replace it", "release_budget": False})
    second = create(as_, pr).json()
    svc = OrderService(db)
    request = db.get(PurchaseRequest, pr["id"])
    from app.core.errors import BusinessRuleViolation

    with pytest.raises(BusinessRuleViolation) as exc:  # releasing "for" the cancelled first order while the second is active
        svc._release_commitment(
            request, excluding_order=first["id"], actor=build_principal(db.get(User, org.users["buyer"].id)), reason="x"
        )
    assert exc.value.code == "commitment_in_use"
    assert ledger(db, org) == [("commitment", Decimal("11002.00"))]
    assert as_("buyer").get(f"/procurement/purchase-orders/{second['id']}").json()["status"] == "draft"


def test_order_permissions(as_, org):
    pr = approved_request(as_, org)
    assert "create_purchase_order" not in as_("cfo").get(f"/procurement/requests/{pr['id']}").json()["allowed_actions"]
    for who in ("eng", "cfo", "ceo", "head"):
        r = as_(who).post(f"/procurement/requests/{pr['id']}/purchase-orders", {})
        assert r.status_code in (403, 404), (who, r.status_code)
    po = create(as_, pr).json()
    for who in ("eng", "cfo", "ceo"):
        assert as_(who).post(f"/procurement/purchase-orders/{po['id']}/issue").status_code == 403
        r = as_(who).post(f"/procurement/purchase-orders/{po['id']}/cancel", {"reason": "nope", "release_budget": True})
        assert r.status_code == 403
    # Read access: finance/executive see everything (read-only); the requester sees their own; others see nothing.
    for who in ("cfo", "ceo", "eng"):
        r = as_(who).get(f"/procurement/purchase-orders/{po['id']}")
        assert r.status_code == 200 and r.json()["allowed_actions"] == [], who
    assert as_("outsider").get(f"/procurement/purchase-orders/{po['id']}").status_code == 404
    assert as_("outsider").get("/procurement/purchase-orders").json()["total"] == 0
    assert as_("eng").get("/procurement/purchase-orders").json()["total"] == 1
    assert as_("hr").get("/procurement/purchase-orders").json()["total"] == 0
    assert as_("head").get("/procurement/purchase-orders").json()["total"] == 1  # department manager of the request


def test_list_filters_and_search(as_, org):
    pr = approved_request(as_, org)
    po = create(as_, pr).json()
    buyer = as_("buyer")
    assert buyer.get("/procurement/purchase-orders", params={"status": "draft"}).json()["total"] == 1
    assert buyer.get("/procurement/purchase-orders", params={"status": "issued"}).json()["total"] == 0
    assert buyer.get("/procurement/purchase-orders", params={"q": po["code"]}).json()["items"][0]["id"] == po["id"]
    assert buyer.get("/procurement/purchase-orders", params={"q": pr["code"]}).json()["total"] == 1
    assert buyer.get("/procurement/purchase-orders", params={"request_id": pr["id"]}).json()["total"] == 1


def test_audit_and_events(as_, org, db):
    pr = approved_request(as_, org)
    po = create(as_, pr).json()
    as_("buyer").post(f"/procurement/purchase-orders/{po['id']}/issue")
    as_("buyer").post(f"/procurement/purchase-orders/{po['id']}/cancel", {"reason": "Supplier withdrew", "release_budget": True})
    po_actions = [a for (a,) in db.execute(select(AuditLog.action).where(AuditLog.entity_id == po["id"]).order_by(AuditLog.created_at))]
    assert po_actions == ["purchase_order.created", "purchase_order.issued", "purchase_order.cancelled"]
    pr_actions = {a for (a,) in db.execute(select(AuditLog.action).where(AuditLog.entity_id == pr["id"]))}
    assert {
        "purchase_request.order_created",
        "purchase_request.order_issued",
        "purchase_request.order_cancelled",
        "purchase_request.closed",
    } <= pr_actions
    types = [t for (t,) in db.execute(select(AutomationEvent.event_type).order_by(AutomationEvent.created_at))]
    assert {"purchase_order.created", "purchase_order.issued", "purchase_order.cancelled", "purchase_request.closed"} <= set(types)
    assert types.count("budget.ledger_changed") == 2  # commitment + release only
    activity = as_("eng").get(f"/procurement/requests/{pr['id']}/activity").json()
    assert any(i["action"] == "purchase_request.closed" for i in activity)


def test_cancel_validates_reason(as_, org):
    pr = approved_request(as_, org)
    po = create(as_, pr).json()
    r = as_("buyer").post(f"/procurement/purchase-orders/{po['id']}/cancel", {"reason": "", "release_budget": True})
    assert r.status_code == 422
    r = as_("buyer").post(f"/procurement/purchase-orders/{po['id']}/cancel", {"reason": "ok reason"})
    assert r.status_code == 422  # the budget decision is explicit, never defaulted


def test_requests_without_orders_keep_commitment(as_, org, db):
    """Existing approved requests: the commitment stays untouched until an order is cancelled with release."""
    approved_request(as_, org)
    assert db.scalar(select(func.count()).select_from(PurchaseOrder)) == 0
    assert ledger(db, org) == [("commitment", Decimal("11002.00"))]
    stats = as_("buyer").get("/procurement/requests/stats", params={"scope": "all"}).json()
    assert stats["approved"] == 1 and stats["closed"] == 0
