"""Phase 5A — real estate inventory: CRUD, filters, availability grid, unit status rules, RBAC, audit, constraints."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.automation.models import AutomationEvent
from app.modules.audit.models import AuditLog
from app.modules.realestate.models import RePaymentPlan, ReUnit
from app.modules.realestate.service import RealEstateService

pytestmark = pytest.mark.db


def test_project_building_unit_crud_and_audit(sales, db):
    m = sales("manager")
    r = m.post(
        "/realestate/projects",
        {
            "code": "nova-x",
            "name": "Nova X (fictional)",
            "city": "Riyadh",
            "amenities": ["Pool", " Gym ", "Pool"],
            "media": [{"url": "https://example.com/a.jpg", "caption": "Illustrative render"}],
        },
    )
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["code"] == "NOVA-X" and p["amenities"] == ["Pool", "Gym"] and p["media"][0]["url"] == "https://example.com/a.jpg"
    assert p["units"]["total"] == 0 and p["can_manage"] is True
    assert m.post("/realestate/projects", {"code": "NOVA-X", "name": "Dup", "city": "Riyadh"}).json()["error"]["code"] == "duplicate_code"

    b = m.post(f"/realestate/projects/{p['id']}/buildings", {"code": "t1", "name": "Tower 1", "floors": 4})
    assert b.status_code == 201 and b.json()["code"] == "T1"
    assert m.post(f"/realestate/projects/{p['id']}/buildings", {"code": "T1", "name": "Again", "floors": 2}).status_code == 409
    bid = b.json()["id"]
    unit = {
        "building_id": bid,
        "unit_number": "101",
        "unit_type": "apartment",
        "bedrooms": 2,
        "bathrooms": 2,
        "floor": 1,
        "area_sqm": "120.50",
        "list_price": "950000.00",
        "view": "Park",
    }
    u = m.post("/realestate/units", unit)
    assert u.status_code == 201, u.text
    assert u.json()["price_per_sqm"] == "7883.82" and u.json()["status"] == "available"
    assert m.post("/realestate/units", unit).json()["error"]["code"] == "duplicate_unit"
    assert m.post("/realestate/units", {**unit, "unit_number": "901", "floor": 9}).json()["error"]["code"] == "floor_out_of_range"
    assert m.post("/realestate/units", {**unit, "unit_number": "102", "area_sqm": "0"}).status_code == 422
    assert m.post("/realestate/units", {**unit, "unit_number": "103", "list_price": "-5"}).status_code == 422
    # Lowering floors below existing units is refused.
    assert m.patch(f"/realestate/buildings/{bid}", {"floors": 0}).status_code == 422
    r = m.patch(f"/realestate/units/{u.json()['id']}", {"list_price": "975000.00"})
    assert r.status_code == 200 and r.json()["list_price"] == "975000.00"
    assert m.delete(f"/realestate/buildings/{bid}").json()["error"]["code"] == "building_in_use"
    assert m.delete(f"/realestate/units/{u.json()['id']}").status_code == 204
    assert m.delete(f"/realestate/buildings/{bid}").status_code == 204

    actions = {a for (a,) in db.execute(select(AuditLog.action).where(AuditLog.action.like("realestate.%")))}
    assert {
        "realestate.project_created",
        "realestate.building_created",
        "realestate.unit_created",
        "realestate.unit_updated",
        "realestate.unit_deleted",
        "realestate.building_deleted",
    } <= actions


def test_payment_plan_validation_and_breakdown(sales, inventory):
    m = sales("manager")
    pid = inventory.project.id
    assert (
        m.post(f"/realestate/projects/{pid}/payment-plans", {"name": "Bad", "down_payment_pct": "101", "installments": 1}).status_code
        == 422
    )
    r = m.post(
        f"/realestate/projects/{pid}/payment-plans", {"name": "Over", "down_payment_pct": "60", "handover_pct": "50", "installments": 4}
    )
    assert r.status_code == 422
    r = m.post(f"/realestate/projects/{pid}/payment-plans", {"name": "Cash", "down_payment_pct": "100", "installments": 0})
    assert r.status_code == 201
    assert (
        m.post(f"/realestate/projects/{pid}/payment-plans", {"name": "cash", "down_payment_pct": "100", "installments": 0}).status_code
        == 409
    )
    assert m.patch(f"/realestate/payment-plans/{r.json()['id']}", {"down_payment_pct": "50"}).json()["error"]["code"] == "invalid_shares"

    unit = inventory.units["A-102"]  # SAR 900,000
    d = m.get(f"/realestate/units/{unit.id}").json()
    plans = {p["name"]: p for p in d["payment_plans"]}
    p1 = plans["10/90 over 36 months"]
    assert (p1["down_payment"], p1["installment_amount"], p1["last_installment_amount"], p1["handover_payment"]) == (
        "90000.00",
        "22500.00",
        "22500.00",
        "0.00",
    )
    p2 = plans["20/50/30"]
    assert (p2["down_payment"], p2["installment_amount"], p2["handover_payment"], p2["total"]) == (
        "180000.00",
        "56250.00",
        "270000.00",
        "900000.00",
    )
    assert plans["Cash"]["down_payment"] == "900000.00" and plans["Cash"]["installments"] == 0


def test_unit_filters_search_and_sort(sales, inventory):
    e = sales("employee")  # every internal user can browse inventory
    q = lambda **p: e.get("/realestate/units", params={"project_id": str(inventory.project.id), **p}).json()  # noqa: E731
    assert q()["total"] == 6
    assert [u["unit_number"] for u in q(bedrooms=3, sort="list_price")["items"]] == ["201", "301"]
    assert q(min_bedrooms=3)["total"] == 3
    assert q(price_max="1000000")["total"] == 3 and q(price_min="1000000", price_max="2000000")["total"] == 2
    assert q(unit_type="studio")["items"][0]["building"]["code"] == "B"
    assert q(building_id=str(inventory.buildings["B"].id))["total"] == 2
    assert q(sort="-list_price")["items"][0]["unit_type"] == "penthouse"
    assert q(q="501")["total"] == 1


def test_availability_grid_and_project_stats(sales, inventory, db):
    inventory.units["A-501"].status = "blocked"
    db.commit()
    e = sales("employee")
    grid = e.get(f"/realestate/projects/{inventory.project.id}/availability").json()
    assert grid["totals"] == {"available": 5, "reserved": 0, "sold": 0, "blocked": 1, "total": 6}
    a = next(b for b in grid["buildings"] if b["code"] == "A")
    assert [row["floor"] for row in a["rows"]] == [5, 2, 1] and [u["unit_number"] for u in a["rows"][-1]["units"]] == ["101", "102"]
    projects = e.get("/realestate/projects").json()["items"]
    tst = next(p for p in projects if p["code"] == "TST")
    assert tst["building_count"] == 2 and tst["price_from"] == "420000.00" and tst["price_to"] == "3200000.00" and tst["is_demo_data"]
    detail = e.get(f"/realestate/projects/{inventory.project.id}").json()
    assert detail["can_manage"] is False and len(detail["payment_plans"]) == 2
    assert {b["code"]: b["units"]["total"] for b in detail["buildings"]} == {"A": 4, "B": 2}


def test_manual_status_rules(sales, inventory, db):
    m = sales("manager")
    unit = inventory.units["A-101"]
    r = m.patch(f"/realestate/units/{unit.id}", {"status": "blocked"})
    assert r.status_code == 200 and r.json()["status"] == "blocked" and r.json()["allowed_status_changes"] == ["available"]
    for bad in ("reserved", "sold"):
        r = m.patch(f"/realestate/units/{unit.id}", {"status": bad})
        assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_status_change"
    assert m.patch(f"/realestate/units/{unit.id}", {"status": "available"}).status_code == 200
    # A reserved unit can't be edited commercially, unblocked or deleted by hand.
    unit.status = "reserved"
    db.commit()
    assert m.patch(f"/realestate/units/{unit.id}", {"list_price": "1.00"}).json()["error"]["code"] == "unit_locked"
    assert m.patch(f"/realestate/units/{unit.id}", {"status": "available"}).json()["error"]["code"] == "invalid_status_change"
    assert m.delete(f"/realestate/units/{unit.id}").json()["error"]["code"] == "unit_locked"
    assert m.patch(f"/realestate/units/{unit.id}", {"notes": "VIP viewing"}).status_code == 200  # notes stay editable
    ev = db.scalars(select(AutomationEvent).where(AutomationEvent.event_type == "unit.status_changed")).all()
    assert [(e.payload["from"], e.payload["to"]) for e in ev] == [("available", "blocked"), ("blocked", "available")]


def test_reservation_transitions_service_rules(db, inventory):
    svc = RealEstateService(db)
    unit = svc.lock_unit(inventory.units["B-101"].id)
    svc.transition_unit(unit, "reserved", actor_user_id=None, reason="test")
    from app.core.errors import Conflict

    with pytest.raises(Conflict):
        svc.transition_unit(unit, "reserved", actor_user_id=None, reason="double")
    svc.transition_unit(unit, "sold", actor_user_id=None, reason="sale")
    with pytest.raises(Conflict):
        svc.transition_unit(unit, "available", actor_user_id=None, reason="sold is terminal")


def test_inventory_permissions(sales, inventory):
    for who in ("employee", "agent1", "marketing"):
        a = sales(who)
        assert a.get("/realestate/projects").status_code == 200
        assert a.post("/realestate/projects", {"code": "X1", "name": "Nope", "city": "Riyadh"}).status_code == 403
        assert a.patch(f"/realestate/units/{inventory.units['A-101'].id}", {"status": "blocked"}).status_code == 403
        assert (
            a.post(
                f"/realestate/projects/{inventory.project.id}/payment-plans", {"name": "No", "down_payment_pct": "100", "installments": 0}
            ).status_code
            == 403
        )
    d = sales("agent1").get(f"/realestate/units/{inventory.units['A-101'].id}").json()
    assert d["can_manage"] is False and d["allowed_status_changes"] == []


def test_inventory_requires_read_permission(app, make_user, roles, db, inventory):
    from app.modules.identity.models import Role
    from tests.business_fixtures import Actor

    bare = Role(code="no_access", name="No access", description="nothing")
    db.add(bare)
    db.commit()
    user = make_user("employee")
    user.roles = [bare]
    db.commit()
    assert Actor(app, user).get("/realestate/units").status_code == 403


def test_database_constraints(db, inventory):
    b = inventory.buildings["A"]
    db.add(
        ReUnit(
            project_id=b.project_id,
            building_id=b.id,
            unit_number="101",
            unit_type="apartment",
            bedrooms=1,
            bathrooms=1,
            floor=1,
            area_sqm=Decimal("50"),
            list_price=Decimal("1"),
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
    db.add(
        RePaymentPlan(project_id=b.project_id, name="Broken", down_payment_pct=Decimal("70"), installments=2, handover_pct=Decimal("40"))
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_demo_seed_is_additive_and_idempotent(db):
    from sqlalchemy import func

    from app.modules.realestate.models import ReBuilding, ReProject
    from app.seed.demo_realestate import seed_demo_realestate

    first = seed_demo_realestate(db)
    db.commit()
    assert first == {"projects": 1, "buildings": 2, "units": 20, "payment_plans": 2}
    project = db.scalar(select(ReProject).where(ReProject.code == "NOVA"))
    assert project.is_demo_data and "fictional" in project.description.lower()
    # A user edits a seeded unit and reserves another; re-running changes nothing and duplicates nothing.
    unit = db.scalar(select(ReUnit).where(ReUnit.project_id == project.id, ReUnit.unit_number == "101").limit(1))
    unit.list_price = Decimal("1.00")
    unit.status = "reserved"
    db.commit()
    assert seed_demo_realestate(db) == {"projects": 0, "buildings": 0, "units": 0, "payment_plans": 0}
    db.commit()
    db.refresh(unit)
    assert unit.list_price == Decimal("1.00") and unit.status == "reserved"
    assert db.scalar(select(func.count()).select_from(ReUnit).where(ReUnit.project_id == project.id)) == 20
    assert db.scalar(select(func.count()).select_from(ReBuilding).where(ReBuilding.project_id == project.id)) == 2
    assert all(u.is_demo_data for u in db.scalars(select(ReUnit).where(ReUnit.project_id == project.id)))
