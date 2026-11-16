"""Phase 5D — CRM workflows on the automation engine: crm.follow_up_sla and crm.reservation_expiry (schedule single-fire,
escalation dedupe per lead per day, retries without duplicates, audit) and the preserved crm.lead_registration key."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.automation.engine import Engine
from app.automation.errors import TransientError
from app.automation.manager import sync_definitions
from app.automation.models import WorkflowDefinition, WorkflowExecution
from app.modules.audit.models import AuditLog
from app.modules.crm.models import Lead, LeadActivity, UnitReservation
from app.modules.notifications.models import Notification
from app.modules.realestate.models import ReUnit
from tests.test_db_crm import new_lead
from tests.test_db_reservations import reserve

pytestmark = pytest.mark.db


@pytest.fixture
def wf(db, connection, roles):
    sync_definitions(db)
    db.commit()
    return Engine(lambda: Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False), "worker-5d")


def fire(engine: Engine, db: Session, key: str) -> list[WorkflowExecution]:
    """Fires only ``key``'s schedule slot and drains the queue."""
    db.execute(update(WorkflowDefinition).where(WorkflowDefinition.key != key).values(next_run_at=func.now() + text("interval '1 hour'")))
    db.execute(update(WorkflowDefinition).where(WorkflowDefinition.key == key).values(next_run_at=None))
    db.commit()
    engine.fire_schedules()
    engine.run_until_idle()
    db.expire_all()
    return list(db.scalars(select(WorkflowExecution).where(WorkflowExecution.workflow_key == key).order_by(WorkflowExecution.created_at)))


def make_due(db: Session) -> None:
    db.execute(
        update(WorkflowExecution)
        .where(WorkflowExecution.status == "pending")
        .values(available_at=func.clock_timestamp() - text("interval '1 second'"))
    )
    db.commit()


def overdue(db, lead_id, hours=3):
    db.execute(update(Lead).where(Lead.id == lead_id).values(next_follow_up_at=datetime.now(UTC) - timedelta(hours=hours)))
    db.commit()


def test_definitions_registered_with_schedules(db, wf):
    defs = {d.key: d for d in db.scalars(select(WorkflowDefinition))}
    assert defs["crm.follow_up_sla"].schedule_minutes == 15 and defs["crm.reservation_expiry"].schedule_minutes == 15
    assert defs["crm.lead_registration"].event_types == ["lead.created"] and defs["crm.lead_registration"].version == 1
    assert "crm.new_lead" in defs["crm.lead_registration"].description


def test_follow_up_sla_escalates_once_per_lead_per_day(sales, db, wf):
    late = new_lead(sales, db, owner="agent1")
    on_time = new_lead(sales, db, owner="agent1")
    closed = new_lead(sales, db, owner="agent2")
    overdue(db, late["id"])
    sales("agent2").post(f"/crm/leads/{closed['id']}/stage", {"stage": "lost", "reason": "No budget"})
    db.execute(update(Lead).where(Lead.id == closed["id"]).values(next_follow_up_at=datetime.now(UTC) - timedelta(hours=5)))
    db.commit()

    (ex,) = fire(wf, db, "crm.follow_up_sla")
    assert ex.status == "succeeded" and ex.result["escalate"]["leads"] == [late["code"]]
    manager_note = db.scalar(
        select(Notification).where(Notification.user_id == sales.users["manager"].id, Notification.type == "crm.follow_up_overdue")
    )
    assert manager_note is not None and late["code"] in manager_note.title and "Fictional Buyer" not in manager_note.body
    assert db.scalar(
        select(Notification).where(Notification.user_id == sales.users["agent1"].id, Notification.type == "crm.follow_up_overdue")
    )
    assert db.scalar(select(AuditLog).where(AuditLog.action == "crm.lead_escalated", AuditLog.entity_id == late["id"]))

    # Replaying the same slot is single-fire (no second execution); a later slot the same day escalates nothing new.
    assert len(fire(wf, db, "crm.follow_up_sla")) == 1
    from app.modules.crm.service import CRMService

    assert CRMService(db).escalate_overdue(now=datetime.now(UTC) + timedelta(minutes=15)) == []
    db.commit()
    count = db.scalar(select(func.count()).select_from(Notification).where(Notification.type == "crm.follow_up_overdue"))
    assert count == 2  # one manager + the owner
    assert (
        db.scalar(
            select(func.count())
            .select_from(LeadActivity)
            .where(LeadActivity.lead_id == late["id"], LeadActivity.dedupe_key.like("%:sla:%"))
        )
        == 1
    )
    assert not db.scalar(select(LeadActivity).where(LeadActivity.lead_id == on_time["id"], LeadActivity.dedupe_key.like("%:sla:%")))


def test_follow_up_sla_dedupe_is_per_day(sales, db):
    from app.modules.crm.service import CRMService

    lead = new_lead(sales, db, owner="agent1")
    overdue(db, lead["id"], hours=30)
    svc = CRMService(db)
    today = datetime.now(UTC)
    assert len(svc.escalate_overdue(now=today)) == 1
    assert svc.escalate_overdue(now=today + timedelta(minutes=15)) == []
    assert len(svc.escalate_overdue(now=today + timedelta(days=1))) == 1  # escalates again the next day
    db.commit()


def test_follow_up_sla_retries_without_duplicates(sales, db, wf, monkeypatch):
    from app.modules.crm import service as crm_service

    lead = new_lead(sales, db, owner="agent1")
    overdue(db, lead["id"])
    real = crm_service.CRMService.escalate_overdue
    calls = {"n": 0}

    def flaky(self, **kw):
        calls["n"] += 1
        result = real(self, **kw)
        if calls["n"] == 1:
            raise TransientError("database briefly unavailable")  # after doing the work → rolled back with the step
        return result

    monkeypatch.setattr(crm_service.CRMService, "escalate_overdue", flaky)
    (ex,) = fire(wf, db, "crm.follow_up_sla")
    assert ex.status == "pending" and ex.attempt == 1  # retry scheduled with backoff
    make_due(db)
    wf.run_until_idle()
    db.expire_all()
    ex = db.get(WorkflowExecution, ex.id)
    assert ex.status == "succeeded" and ex.attempt == 2 and ex.result["escalate"]["escalated"] == 1
    assert (
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.type == "crm.follow_up_overdue", Notification.user_id == sales.users["manager"].id)
        )
        == 1
    )


def test_reservation_expiry_workflow_releases_units(sales, db, wf, inventory):
    l1, l2 = new_lead(sales, db), new_lead(sales, db)
    due = reserve(sales("agent1"), l1, inventory.units["A-101"]).json()
    keep = reserve(sales("agent1"), l2, inventory.units["A-102"]).json()
    past = datetime.now(UTC) - timedelta(minutes=1)
    db.execute(
        update(UnitReservation).where(UnitReservation.id == due["id"]).values(reserved_at=past - timedelta(hours=72), expires_at=past)
    )
    db.commit()
    (ex,) = fire(wf, db, "crm.reservation_expiry")
    assert ex.status == "succeeded" and ex.result["expire"]["reservations"] == [due["code"]]
    assert db.get(UnitReservation, due["id"]).status == "expired" and db.get(ReUnit, inventory.units["A-101"].id).status == "available"
    assert db.get(UnitReservation, keep["id"]).status == "active" and db.get(ReUnit, inventory.units["A-102"].id).status == "reserved"
    # Schedule single-fire: replaying the same slot creates no duplicate execution.
    db.execute(update(WorkflowDefinition).where(WorkflowDefinition.key == "crm.reservation_expiry").values(next_run_at=None))
    db.commit()
    assert wf.fire_schedules() == 0


def test_reservation_expiry_retry_is_idempotent(sales, db, wf, inventory, monkeypatch):
    from app.modules.crm import reservations as res_mod

    lead = new_lead(sales, db)
    due = reserve(sales("agent1"), lead, inventory.units["B-101"]).json()
    past = datetime.now(UTC) - timedelta(minutes=1)
    db.execute(
        update(UnitReservation).where(UnitReservation.id == due["id"]).values(reserved_at=past - timedelta(hours=72), expires_at=past)
    )
    db.commit()
    real = res_mod.ReservationService.expire_due
    calls = {"n": 0}

    def flaky(self, **kw):
        calls["n"] += 1
        out = real(self, **kw)
        if calls["n"] == 1:
            raise TransientError("lost connection")
        return out

    monkeypatch.setattr(res_mod.ReservationService, "expire_due", flaky)
    (ex,) = fire(wf, db, "crm.reservation_expiry")
    make_due(db)
    wf.run_until_idle()
    db.expire_all()
    ex = db.get(WorkflowExecution, ex.id)
    assert ex.status == "succeeded" and ex.result["expire"]["expired"] == 1
    assert db.scalar(select(func.count()).select_from(Notification).where(Notification.type == "crm.reservation_expired")) == 1
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "crm.reservation_expired", AuditLog.entity_type == "unit_reservation")
        )
        == 1
    )
