"""Fictional NOVA Residences inventory (Phase 5 demo data). Additive and idempotent.

    python -m app.seed.demo_realestate

- Inserts only what is missing, matched by natural keys (project code; building code; building + unit number;
  project + plan name). Existing rows — including anything a user created or edited — are never updated or deleted.
- Every row it creates carries ``is_demo_data = true``. NOVA Residences, its towers, units, prices and payment plans are
  fictional. It has no media links (brochures are generated in Marketing → Brochures & posters).
- Development / test only: refuses to run in staging or production.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.modules.realestate.models import ReBuilding, RePaymentPlan, ReProject, ReUnit
from app.modules.realestate.repository import RealEstateRepository

PROJECT = {
    "code": "NOVA",
    "name": "NOVA Residences",
    "city": "Riyadh",
    "district": "North Riyadh (fictional)",
    "description": "A fictional residential community of two towers with landscaped podium gardens, created only to demonstrate the "
    "SmartEstate AI prototype. No real project, developer or price is represented.",
    "status": "launched",
    "launch_date": date(2026, 9, 1),
    "handover_date": date(2028, 12, 31),
    "amenities": [
        "Swimming pool",
        "Fitness centre",
        "Children's play area",
        "Landscaped podium",
        "Covered parking",
        "24/7 security",
        "Residents' lounge",
    ],
    "media": [],  # no placeholder links: there is no real brochure or tour for a fictional project
}
BUILDINGS = (("A", "Tower A — Garden", 6), ("B", "Tower B — Park", 5))
# building, unit, type, bedrooms, bathrooms, floor, area m², view, list price (SAR, fictional)
UNITS = (
    ("A", "101", "apartment", 1, 1, 1, "78.00", "Garden", "690000.00"),
    ("A", "102", "apartment", 2, 2, 1, "112.00", "Garden", "925000.00"),
    ("A", "201", "apartment", 2, 2, 2, "115.00", "Garden", "955000.00"),
    ("A", "202", "apartment", 3, 3, 2, "148.00", "Pool", "1240000.00"),
    ("A", "301", "apartment", 2, 2, 3, "115.00", "Garden", "975000.00"),
    ("A", "302", "apartment", 3, 3, 3, "150.00", "Pool", "1275000.00"),
    ("A", "401", "apartment", 1, 1, 4, "80.00", "City", "725000.00"),
    ("A", "402", "apartment", 3, 3, 4, "152.00", "Pool", "1310000.00"),
    ("A", "501", "duplex", 4, 4, 5, "240.00", "City", "2150000.00"),
    ("A", "502", "apartment", 2, 2, 5, "118.00", "City", "1020000.00"),
    ("A", "601", "penthouse", 4, 5, 6, "320.00", "Skyline", "3350000.00"),
    ("B", "101", "studio", 0, 1, 1, "46.00", "Park", "435000.00"),
    ("B", "102", "studio", 0, 1, 1, "48.00", "Park", "449000.00"),
    ("B", "201", "apartment", 1, 1, 2, "76.00", "Park", "675000.00"),
    ("B", "202", "apartment", 2, 2, 2, "110.00", "Park", "910000.00"),
    ("B", "301", "apartment", 2, 2, 3, "112.00", "Park", "935000.00"),
    ("B", "302", "apartment", 3, 3, 3, "146.00", "Boulevard", "1215000.00"),
    ("B", "401", "apartment", 3, 3, 4, "149.00", "Boulevard", "1260000.00"),
    ("B", "402", "townhouse", 3, 4, 4, "205.00", "Park", "1790000.00"),
    ("B", "501", "penthouse", 4, 5, 5, "290.00", "Skyline", "2980000.00"),
)
PLANS = (
    {
        "name": "10 / 90 over 3 years",
        "down_payment_pct": Decimal("10"),
        "installments": 36,
        "installment_frequency": "monthly",
        "handover_pct": Decimal("0"),
        "description": "10% on signing, the rest in 36 equal monthly installments (fictional).",
    },
    {
        "name": "20 / 50 / 30 construction-linked",
        "down_payment_pct": Decimal("20"),
        "installments": 8,
        "installment_frequency": "quarterly",
        "handover_pct": Decimal("30"),
        "description": "20% on signing, 50% over 8 quarterly installments, 30% at handover (fictional).",
    },
)


def seed_demo_realestate(session: Session) -> dict[str, int]:
    """Returns how many rows of each kind were created (0s on a re-run)."""
    repo = RealEstateRepository(session)
    created = {"projects": 0, "buildings": 0, "units": 0, "payment_plans": 0}
    project = repo.project_by_code(PROJECT["code"])
    if project is None:
        project = ReProject(**PROJECT, is_demo_data=True)
        session.add(project)
        session.flush()
        created["projects"] += 1
    buildings: dict[str, ReBuilding] = {}
    for code, name, floors in BUILDINGS:
        b = repo.building_by_code(project.id, code)
        if b is None:
            b = ReBuilding(project_id=project.id, code=code, name=name, floors=floors, is_demo_data=True)
            session.add(b)
            session.flush()
            created["buildings"] += 1
        buildings[code] = b
    for b_code, number, typ, beds, baths, floor, area, view, price in UNITS:
        b = buildings[b_code]
        if floor > b.floors or repo.unit_by_number(b.id, number) is not None:
            continue  # never touch an existing unit (it may have been reserved, sold or edited)
        session.add(
            ReUnit(
                project_id=project.id,
                building_id=b.id,
                unit_number=number,
                unit_type=typ,
                bedrooms=beds,
                bathrooms=baths,
                floor=floor,
                area_sqm=Decimal(area),
                view=view,
                list_price=Decimal(price),
                is_demo_data=True,
            )
        )
        created["units"] += 1
    for plan in PLANS:
        if repo.plan_by_name(project.id, str(plan["name"])) is None:
            session.add(RePaymentPlan(project_id=project.id, is_demo_data=True, marketing_status="cleared", **plan))
            created["payment_plans"] += 1
    session.flush()
    return created


def main() -> None:
    settings = get_settings()
    if not settings.is_dev_like:
        raise SystemExit("The fictional demo inventory is only seeded in development or test.")
    with get_sessionmaker()() as session:
        created = seed_demo_realestate(session)
        session.commit()
    print("Fictional NOVA inventory: " + ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in created.items()) + " created.")


if __name__ == "__main__":
    main()
