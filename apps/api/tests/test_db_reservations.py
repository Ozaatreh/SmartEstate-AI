"""Phase 5C — reservations: create / cancel / convert / expire, atomic status changes, uniqueness, permissions,
no ledger postings for deposits, audit and events."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.automation.models import AutomationEvent
from app.modules.audit.models import AuditLog
from app.modules.crm.models import Lead, UnitReservation
from app.modules.crm.reservations import ReservationService
from app.modules.finance.models import BudgetLedgerEntry
from app.modules.notifications.models import Notification
from app.modules.realestate.models import ReUnit
from tests.test_db_crm import new_lead

pytestmark = pytest.mark.db


def reserve(actor, lead, unit, **kw):
    return actor.post("/crm/reservations", {"lead_id": lead["id"], "unit_id": str(unit.id), **kw})


def test_reserve_moves_unit_and_lead_atomically(sales, db, inventory):
    lead = new_lead(sales, db)
    unit = inventory.units["A-102"]
    before_ledger = db.scalar(select(func.count()).select_from(BudgetLedgerEntry))
    r = reserve(sales("agent1"), lead, unit, deposit_amount="25000.00", notes="Paid by transfer (fictional)")
    assert r.status_code == 201, r.text
    res = r.json()
    assert res["code"].startswith("RSV-") and res["status"] == "active" and res["unit_status"] == "reserved"
    hours = (datetime.fromisoformat(res["expires_at"]) - datetime.fromisoformat(res["reserved_at"])).total_seconds() / 3600
    assert hours == 72  # default duration
    assert res["deposit_amount"] == "25000.00" and res["allowed_actions"] == ["cancel", "convert"]
    d = sales("agent1").get(f"/crm/leads/{lead['id']}").json()
    assert d["stage"] == "negotiation" and d["interested_unit"]["code"] == "A-102" and d["project"]["code"] == "TST"
    assert d["reservations"][0]["code"] == res["code"]
    assert db.scalar(select(func.count()).select_from(BudgetLedgerEntry)) == before_ledger  # deposit is informational only
    body = [t["body"] for t in sales("agent1").get(f"/crm/leads/{lead['id']}/activities").json()]
    assert any("reserved A-102" in b and "informational" in b for b in body) and "Stage: new → negotiation — Reserved A-102" in body
    types = {e for (e,) in db.execute(select(AutomationEvent.event_type))}
    assert {"reservation.created", "unit.status_changed", "lead.stage_changed"} <= types
    assert db.scalar(select(AuditLog).where(AuditLog.action == "crm.reservation_created", AuditLog.entity_type == "unit_reservation"))
    assert db.scalar(select(AuditLog).where(AuditLog.action == "realestate.unit_status_changed"))


def test_custom_duration_and_later_stage_kept(sales, db, inventory):
    lead = new_lead(sales, db)
    sales("agent1").post(f"/crm/leads/{lead['id']}/stage", {"stage": "negotiation"})
    r = reserve(sales("agent1"), lead, inventory.units["B-101"], hours=24)
    res = r.json()
    assert (datetime.fromisoformat(res["expires_at"]) - datetime.fromisoformat(res["reserved_at"])) == timedelta(hours=24)
    stage_changes = [t for t in sales("agent1").get(f"/crm/leads/{lead['id']}/activities").json() if t["type"] == "stage_change"]
    assert len(stage_changes) == 1  # only the manual move; reserving didn't touch negotiation
    assert reserve(sales("agent1"), lead, inventory.units["A-101"], hours=0).status_code == 422
    assert reserve(sales("agent1"), lead, inventory.units["A-101"], deposit_amount="-1").status_code == 422


def test_double_reservation_refused_by_service_and_database(sales, db, inventory):
    l1, l2 = new_lead(sales, db), new_lead(sales, db, owner="agent2")
    unit = inventory.units["A-201"]
    assert reserve(sales("agent1"), l1, unit).status_code == 201
    r = reserve(sales("agent2"), l2, unit)
    assert r.status_code == 409 and r.json()["error"]["code"] == "unit_unavailable"
    # Database guard, bypassing the service: a second active row for the unit violates the partial unique index.
    first = db.scalar(select(UnitReservation).where(UnitReservation.unit_id == unit.id))
    now = datetime.now(UTC)
    db.add(
        UnitReservation(
            code="RSV-X", unit_id=unit.id, lead_id=first.lead_id, status="active", reserved_at=now, expires_at=now + timedelta(hours=1)
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_cancel_releases_unit_once(sales, db, inventory):
    lead = new_lead(sales, db)
    unit = inventory.units["A-101"]
    res = reserve(sales("agent1"), lead, unit).json()
    a1 = sales("agent1")
    assert a1.post(f"/crm/reservations/{res['id']}/cancel", {"reason": ""}).status_code == 422
    r = a1.post(f"/crm/reservations/{res['id']}/cancel", {"reason": "Buyer postponed"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled" and r.json()["unit_status"] == "available"
    assert r.json()["allowed_actions"] == [] and r.json()["cancel_reason"] == "Buyer postponed"
    again = a1.post(f"/crm/reservations/{res['id']}/cancel", {"reason": "again"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "reservation_not_active"
    assert a1.post(f"/crm/reservations/{res['id']}/convert").json()["error"]["code"] == "reservation_not_active"
    # The unit can be reserved again.
    assert reserve(a1, lead, unit).status_code == 201
    # All events share one created_at here (the test runs in a single transaction), so compare transitions, not order:
    # available → reserved twice and reserved → available once is exactly reserve, cancel, reserve.
    ev = sorted(
        (e.payload["from"], e.payload["to"])
        for e in db.scalars(select(AutomationEvent).where(AutomationEvent.event_type == "unit.status_changed"))
    )
    assert ev == [("available", "reserved"), ("available", "reserved"), ("reserved", "available")]


def test_convert_sells_unit_and_wins_lead(sales, db, inventory):
    lead = new_lead(sales, db)
    unit = inventory.units["B-301"]
    res = reserve(sales("agent1"), lead, unit).json()
    # A lead with an active reservation can't be marked won by hand.
    r = sales("agent1").post(f"/crm/leads/{lead['id']}/stage", {"stage": "won", "reason": "Signed"})
    assert r.json()["error"]["code"] == "active_reservation"
    r = sales("agent1").post(f"/crm/reservations/{res['id']}/convert")
    assert r.status_code == 200 and r.json()["status"] == "converted" and r.json()["unit_status"] == "sold"
    d = sales("agent1").get(f"/crm/leads/{lead['id']}").json()
    assert d["stage"] == "won" and d["close_reason"] == f"Bought B-301 ({res['code']})" and d["allowed_stages"] == []
    assert "reserve" not in d["allowed_actions"]
    # Sold units can't be reserved or reopened by hand.
    other = new_lead(sales, db)
    assert reserve(sales("agent1"), other, unit).json()["error"]["code"] == "unit_unavailable"
    assert (
        sales("manager").patch(f"/realestate/units/{unit.id}", {"status": "available"}).json()["error"]["code"] == "invalid_status_change"
    )


def test_closed_lead_and_project_mismatch(sales, db, inventory):
    lead = new_lead(sales, db)
    sales("agent1").post(f"/crm/leads/{lead['id']}/stage", {"stage": "lost", "reason": "Not interested"})
    assert reserve(sales("agent1"), lead, inventory.units["A-101"]).json()["error"]["code"] == "lead_closed"
    other = sales("manager").post("/realestate/projects", {"code": "OTH", "name": "Other", "city": "Jeddah"}).json()
    lead2 = new_lead(sales, db, project_id=other["id"])
    assert reserve(sales("agent1"), lead2, inventory.units["A-101"]).json()["error"]["code"] == "unit_project_mismatch"
    inventory.units["A-501"].status = "blocked"
    db.commit()
    lead3 = new_lead(sales, db)
    assert reserve(sales("agent1"), lead3, inventory.units["A-501"]).json()["error"]["code"] == "unit_unavailable"


def test_reservation_permissions_and_scope(sales, db, inventory):
    own, other = new_lead(sales, db, owner="agent1"), new_lead(sales, db, owner="agent2")
    a1, a2, m = sales("agent1"), sales("agent2"), sales("manager")
    # Agents reserve only for their own leads; others don't even see the lead.
    assert reserve(a1, other, inventory.units["A-101"]).status_code == 404
    for who in ("marketing", "employee"):
        assert reserve(sales(who), own, inventory.units["A-101"]).status_code == 403
    mine = reserve(a1, own, inventory.units["A-101"]).json()
    theirs = reserve(m, other, inventory.units["A-102"]).json()  # managers reserve for any lead
    assert {r["code"] for r in a1.get("/crm/reservations").json()["items"]} == {mine["code"]}
    assert a1.get("/crm/reservations", params={"scope": "all"}).status_code == 403
    assert m.get("/crm/reservations", params={"scope": "all"}).json()["total"] == 2
    assert a1.get(f"/crm/reservations/{theirs['id']}").status_code == 404
    assert a1.post(f"/crm/reservations/{theirs['id']}/cancel", {"reason": "not mine"}).status_code == 404
    assert a2.get(f"/crm/reservations/{theirs['id']}").json()["allowed_actions"] == ["cancel", "convert"]
    assert m.post(f"/crm/reservations/{mine['id']}/cancel", {"reason": "Manager override"}).status_code == 200
    assert sales("employee").get("/crm/reservations").status_code == 403


def test_unit_reservation_info_hides_lead_from_outsiders(sales, db, inventory):
    lead = new_lead(sales, db)
    unit = inventory.units["A-102"]
    reserve(sales("agent1"), lead, unit)
    info = sales("employee").get(f"/crm/units/{unit.id}/reservation").json()
    assert (
        info["code"].startswith("RSV-") and info["lead"] is None and info["reservation_id"] is None and info["reserved_by"] == "Agent One"
    )
    assert sales("agent1").get(f"/crm/units/{unit.id}/reservation").json()["lead"]["code"] == lead["code"]
    assert sales("employee").get(f"/crm/units/{inventory.units['A-101'].id}/reservation").json() is None


def test_expiry_releases_only_overdue_active_reservations(sales, db, inventory):
    l1, l2, l3 = new_lead(sales, db), new_lead(sales, db), new_lead(sales, db)
    a1 = sales("agent1")
    due = reserve(a1, l1, inventory.units["A-101"]).json()
    fresh = reserve(a1, l2, inventory.units["A-102"]).json()
    sold = reserve(a1, l3, inventory.units["A-201"]).json()
    a1.post(f"/crm/reservations/{sold['id']}/convert")
    past = datetime.now(UTC) - timedelta(minutes=5)
    db.execute(
        update(UnitReservation)
        .where(UnitReservation.id.in_([due["id"], sold["id"]]))
        .values(reserved_at=past - timedelta(hours=72), expires_at=past)
    )
    db.commit()
    svc = ReservationService(db)
    done = svc.expire_due()
    db.commit()
    assert [d["code"] for d in done] == [due["code"]]
    db.expire_all()
    assert db.get(UnitReservation, due["id"]).status == "expired" and db.get(ReUnit, inventory.units["A-101"].id).status == "available"
    assert db.get(UnitReservation, fresh["id"]).status == "active"
    assert db.get(UnitReservation, sold["id"]).status == "converted" and db.get(ReUnit, inventory.units["A-201"].id).status == "sold"
    assert svc.expire_due() == []  # idempotent
    n = db.scalar(
        select(Notification).where(Notification.type == "crm.reservation_expired", Notification.user_id == sales.users["agent1"].id)
    )
    assert n is not None and "A-101" in n.body
    assert db.get(Lead, l1["id"]).stage == "negotiation"  # expiry releases the unit; the lead stays in the pipeline
    assert db.scalar(select(AuditLog).where(AuditLog.action == "crm.reservation_expired"))


def test_database_rejects_inconsistent_reservation_rows(db, inventory, sales):
    lead = new_lead(sales, db)
    now = datetime.now(UTC)
    bad = [
        dict(expires_at=now - timedelta(hours=1)),  # expires before start
        dict(status="cancelled"),  # cancelled without reason / timestamp
        dict(deposit_amount=Decimal("-1")),
    ]
    for i, kw in enumerate(bad):
        row = dict(
            code=f"RSV-BAD{i}",
            unit_id=inventory.units["B-101"].id,
            lead_id=lead["id"],
            reserved_at=now,
            expires_at=now + timedelta(hours=1),
        )
        row.update(kw)
        db.add(UnitReservation(**row))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
