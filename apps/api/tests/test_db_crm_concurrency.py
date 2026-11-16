"""Real concurrency for Phase 5 (committed data, separate connections; tables truncated afterwards).

- N leads assigned round-robin concurrently → every lead gets exactly one owner, the pool cursor is consistent and the
  distribution is even (no duplicate or lost assignment).
- Two users reserve the same unit at once → exactly one active reservation; the unit is reserved once.
- Expiry racing a conversion → the converted reservation never expires.
"""

from __future__ import annotations

import threading
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from app.core.errors import AppError
from app.core.security import hash_password
from app.modules.crm.models import Lead, SalesAssignmentState, UnitReservation
from app.modules.crm.reservations import ReservationService
from app.modules.crm.schemas import ReservationIn
from app.modules.crm.service import CRMService
from app.modules.identity.models import User
from app.modules.identity.service import build_principal
from app.modules.realestate.models import ReBuilding, ReProject, ReUnit
from app.seed.__main__ import sync_permissions, sync_roles
from tests.test_db_concurrency import committed  # noqa: F401  (fixture re-export)

pytestmark = pytest.mark.db


def _setup(maker, *, agents: int = 3, leads: int = 0) -> dict:
    with maker() as s:
        roles = sync_roles(s, sync_permissions(s))
        pw = hash_password("x" * 12)
        users = {
            f"agent{i}": User(email=f"agent{i}@race.demo", password_hash=pw, full_name=f"Agent {i}", roles=[roles["sales_agent"]])
            for i in range(agents)
        }
        users["manager"] = User(email="manager@race.demo", password_hash=pw, full_name="Manager", roles=[roles["sales_manager"]])
        s.add_all(users.values())
        project = ReProject(code="RACE", name="Race Residences", city="Riyadh")
        s.add(project)
        s.flush()
        building = ReBuilding(project_id=project.id, code="A", name="Tower A", floors=3)
        s.add(building)
        s.flush()
        unit = ReUnit(
            project_id=project.id,
            building_id=building.id,
            unit_number="101",
            unit_type="apartment",
            bedrooms=2,
            bathrooms=2,
            floor=1,
            area_sqm=Decimal("100"),
            list_price=Decimal("900000"),
        )
        s.add(unit)
        rows = [
            Lead(code=f"LEAD-R{i:03d}", full_name="Race Lead", phone="+966500000000", source="website", project_id=project.id)
            for i in range(leads)
        ]
        s.add_all(rows)
        s.commit()
        return {"users": {k: u.id for k, u in users.items()}, "unit": unit.id, "project": project.id, "leads": [r.id for r in rows]}


def _run(fns) -> list[str]:
    barrier = threading.Barrier(len(fns))
    results: list[str] = []
    lock = threading.Lock()

    def wrap(fn):
        barrier.wait()
        try:
            out = fn()
        except AppError as exc:
            out = exc.code
        except Exception as exc:  # noqa: BLE001 - surfaced in the assertion message
            out = f"error:{type(exc).__name__}:{exc}"
        with lock:
            results.append(out)

    threads = [threading.Thread(target=wrap, args=(f,)) for f in fns]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return results


def test_concurrent_round_robin_assigns_each_lead_once_and_evenly(committed):  # noqa: F811
    ctx = _setup(committed, agents=3, leads=12)

    def assign(lead_id: uuid.UUID):
        def go():
            with committed() as s:
                CRMService(s).assign_round_robin(lead_id, follow_up_hours=48)
                s.commit()
            return "ok"

        return go

    results = _run([assign(lead) for lead in ctx["leads"]])
    assert results == ["ok"] * 12, results
    with committed() as s:
        owners = [s.get(Lead, lead).owner_user_id for lead in ctx["leads"]]
        assert all(owners)
        assert sorted(Counter(owners).values()) == [4, 4, 4]  # even distribution: nothing duplicated or lost
        state = s.get(SalesAssignmentState, "RACE")
        assert state is not None and state.last_assigned_user_id in owners
        # Re-running is idempotent: owned leads are left alone.
        for lead in ctx["leads"]:
            assert CRMService(s).assign_round_robin(lead, follow_up_hours=48)[1] is False


def test_concurrent_reservations_for_one_unit_succeed_once(committed):  # noqa: F811
    ctx = _setup(committed, agents=2, leads=2)
    with committed() as s:
        for lead, agent in zip(ctx["leads"], ("agent0", "agent1"), strict=True):
            s.execute(update(Lead).where(Lead.id == lead).values(owner_user_id=ctx["users"][agent]))
        s.commit()

    def reserve(lead_id: uuid.UUID, agent: str):
        def go():
            with committed() as s:
                principal = build_principal(s.get(User, ctx["users"][agent]))
                ReservationService(s).create(principal, ReservationIn(lead_id=lead_id, unit_id=ctx["unit"]))
            return "ok"

        return go

    results = _run([reserve(ctx["leads"][0], "agent0"), reserve(ctx["leads"][1], "agent1")])
    assert sorted(results) == ["ok", "unit_unavailable"], results
    with committed() as s:
        active = s.scalars(select(UnitReservation).where(UnitReservation.unit_id == ctx["unit"], UnitReservation.status == "active")).all()
        assert len(active) == 1 and s.get(ReUnit, ctx["unit"]).status == "reserved"


def test_expiry_racing_conversion_never_expires_a_sale(committed):  # noqa: F811
    ctx = _setup(committed, agents=1, leads=1)
    with committed() as s:
        s.execute(update(Lead).where(Lead.id == ctx["leads"][0]).values(owner_user_id=ctx["users"]["agent0"]))
        s.commit()
        principal = build_principal(s.get(User, ctx["users"]["agent0"]))
        r = ReservationService(s).create(principal, ReservationIn(lead_id=ctx["leads"][0], unit_id=ctx["unit"]))
        rid = r.id
        s.execute(
            update(UnitReservation)
            .where(UnitReservation.id == rid)
            .values(reserved_at=datetime.now(UTC) - timedelta(hours=80), expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        s.commit()

    def convert():
        with committed() as s:
            ReservationService(s).convert(build_principal(s.get(User, ctx["users"]["agent0"])), rid)
        return "converted"

    def expire():
        with committed() as s:
            done = ReservationService(s).expire_due()
            s.commit()
        return f"expired:{len(done)}"

    results = _run([convert, expire])
    with committed() as s:
        r = s.get(UnitReservation, rid)
        unit = s.get(ReUnit, ctx["unit"])
        # Either the conversion won (sold) or the expiry won first (then conversion is refused); never both.
        if r.status == "converted":
            assert unit.status == "sold" and "converted" in results
        else:
            assert r.status == "expired" and unit.status == "available" and "reservation_not_active" in results
