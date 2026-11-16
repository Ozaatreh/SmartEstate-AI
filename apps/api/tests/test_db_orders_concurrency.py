"""Real concurrency for purchase orders (committed data, separate connections; tables truncated afterwards).

- Two officers create an order for the same approved request at once → exactly one order.
- Two officers cancel the same order with "release budget" at once → exactly one release entry.
"""

from __future__ import annotations

import threading
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errors import AppError
from app.modules.approvals.models import ApprovalRequest
from app.modules.approvals.service import ApprovalService
from app.modules.finance.models import BudgetLedgerEntry
from app.modules.identity.models import User
from app.modules.identity.service import build_principal
from app.modules.procurement.models import PurchaseOrder
from app.modules.procurement.orders import OrderService
from app.modules.procurement.schemas import OrderCancelIn, OrderCreateIn
from tests.test_db_concurrency import _setup, committed  # noqa: F401  (fixture re-export)

pytestmark = pytest.mark.db


def _approved(maker) -> tuple[uuid.UUID, uuid.UUID, dict[str, uuid.UUID]]:
    approval_id, budget_id, users = _setup(maker)
    with maker() as s:
        ApprovalService(s).approve(build_principal(s.get(User, users["fin1"])), approval_id, "final")
        request_id = s.get(ApprovalRequest, approval_id).entity_id
    with maker() as s:  # a second procurement officer
        buyer = s.get(User, users["buyer"])
        twin = User(email="buyer2@race.demo", password_hash=buyer.password_hash, full_name="Buyer Two", roles=list(buyer.roles))
        s.add(twin)
        s.commit()
        users["buyer2"] = twin.id
    return request_id, budget_id, users


def _race(maker, users, fn) -> list[str]:
    barrier = threading.Barrier(2)
    results: list[str] = []

    def run(key: str) -> None:
        with maker() as s:
            principal = build_principal(s.get(User, users[key]))
            barrier.wait()
            try:
                fn(OrderService(s), principal)
                results.append("ok")
            except AppError as exc:
                results.append(exc.code)

    threads = [threading.Thread(target=run, args=(k,)) for k in ("buyer", "buyer2")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return sorted(results)


def test_concurrent_order_creation_yields_one_order(committed):  # noqa: F811
    request_id, _, users = _approved(committed)
    results = _race(committed, users, lambda svc, p: svc.create(p, request_id, OrderCreateIn()))
    assert results == ["active_order_exists", "ok"], results
    with committed() as s:
        assert len(s.scalars(select(PurchaseOrder).where(PurchaseOrder.request_id == request_id)).all()) == 1


def test_concurrent_cancel_with_release_releases_once(committed):  # noqa: F811
    request_id, budget_id, users = _approved(committed)
    with committed() as s:
        order = OrderService(s).create(build_principal(s.get(User, users["buyer"])), request_id, OrderCreateIn())
        order_id = order.id
    results = _race(
        committed, users, lambda svc, p: svc.cancel(p, order_id, OrderCancelIn(reason="Supplier withdrew", release_budget=True))
    )
    assert results == ["already_cancelled", "ok"], results
    with committed() as s:
        entries = s.scalars(
            select(BudgetLedgerEntry).where(BudgetLedgerEntry.budget_id == budget_id).order_by(BudgetLedgerEntry.created_at)
        )
        assert [(e.entry_type, e.amount) for e in entries] == [("commitment", Decimal("75000.00")), ("release", Decimal("-75000.00"))]
