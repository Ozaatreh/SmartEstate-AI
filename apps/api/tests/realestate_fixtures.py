"""Shared Phase 5 fixtures: a small fictional inventory and logged-in sales actors."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.modules.realestate.models import ReBuilding, RePaymentPlan, ReProject, ReUnit
from tests.business_fixtures import Actor


@dataclass
class Inventory:
    project: ReProject
    buildings: dict[str, ReBuilding] = field(default_factory=dict)
    units: dict[str, ReUnit] = field(default_factory=dict)  # key "A-101"
    plans: list[RePaymentPlan] = field(default_factory=list)


@pytest.fixture
def inventory(db: Session) -> Inventory:
    project = ReProject(code="TST", name="Test Residences", city="Riyadh", status="launched", amenities=["Pool"], is_demo_data=True, is_published=True)
    db.add(project)
    db.flush()
    inv = Inventory(project=project)
    for code, floors in (("A", 5), ("B", 3)):
        inv.buildings[code] = ReBuilding(project_id=project.id, code=code, name=f"Tower {code}", floors=floors)
    db.add_all(inv.buildings.values())
    db.flush()
    spec = [  # building, number, type, bedrooms, floor, area, price
        ("A", "101", "apartment", 1, 1, "75.00", "650000.00"),
        ("A", "102", "apartment", 2, 1, "110.00", "900000.00"),
        ("A", "201", "apartment", 3, 2, "150.00", "1250000.00"),
        ("A", "501", "penthouse", 4, 5, "320.00", "3200000.00"),
        ("B", "101", "studio", 0, 1, "45.00", "420000.00"),
        ("B", "301", "duplex", 3, 3, "210.00", "1800000.00"),
    ]
    for b, num, typ, beds, floor, area, price in spec:
        u = ReUnit(
            project_id=project.id,
            building_id=inv.buildings[b].id,
            unit_number=num,
            unit_type=typ,
            bedrooms=beds,
            bathrooms=max(1, beds),
            floor=floor,
            area_sqm=Decimal(area),
            list_price=Decimal(price),
        )
        inv.units[f"{b}-{num}"] = u
    db.add_all(inv.units.values())
    inv.plans = [
        RePaymentPlan(
            project_id=project.id,
            name="10/90 over 36 months",
            down_payment_pct=Decimal("10"),
            installments=36,
            installment_frequency="monthly",
            handover_pct=Decimal("0"),
            marketing_status="cleared",
        ),
        RePaymentPlan(
            project_id=project.id,
            name="20/50/30",
            down_payment_pct=Decimal("20"),
            installments=8,
            installment_frequency="quarterly",
            handover_pct=Decimal("30"),
            marketing_status="cleared",
        ),
    ]
    db.add_all(inv.plans)
    db.commit()
    for u in inv.units.values():
        db.refresh(u)
    return inv


@pytest.fixture
def sales(app, make_user):
    """Logged-in actors: manager, two agents, a marketing manager and a plain employee."""
    users = {
        "manager": make_user("sales_manager", name="Sara Manager"),
        "agent1": make_user("sales_agent", name="Agent One"),
        "agent2": make_user("sales_agent", name="Agent Two"),
        "marketing": make_user("marketing_manager", name="Mona Marketing"),
        "employee": make_user("employee", name="Eve Employee"),
    }
    cache: dict[str, Actor] = {}

    def get(key: str) -> Actor:
        if key not in cache:
            cache[key] = Actor(app, users[key])
        return cache[key]

    get.users = users  # type: ignore[attr-defined]
    return get
