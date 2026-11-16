"""Phase 5B — CRM pipeline on PostgreSQL: links, updates, follow-ups, stages, activities, reassignment, stats,
scoping, budget-fit scoring, project round-robin pools, audit/event hygiene (no personal data)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.automation.engine import Engine
from app.automation.manager import sync_definitions
from app.automation.models import AutomationEvent
from app.modules.audit.models import AuditLog
from app.modules.crm.models import Lead, LeadActivity, SalesAssignmentState
from app.modules.crm.service import CRMService

pytestmark = pytest.mark.db


def same_minute(a: str, b: str) -> bool:
    return abs((datetime.fromisoformat(a) - datetime.fromisoformat(b)).total_seconds()) < 60


def body(**kw) -> dict:
    return {"full_name": "Fictional Buyer", "phone": "+966 50 111 2222", "email": "buyer@example.com", "source": "website", **kw}


def new_lead(sales, db, *, owner: str | None = "agent1", creator: str = "manager", **kw) -> dict:
    r = sales(creator).post("/crm/leads", body(**kw))
    assert r.status_code == 201, r.text
    if owner:
        db.execute(
            update(Lead)
            .where(Lead.id == r.json()["id"])
            .values(owner_user_id=sales.users[owner].id, next_follow_up_at=datetime.now(UTC) + timedelta(hours=48))
        )
        db.commit()
    return r.json()


def test_create_links_project_and_unit(sales, db, inventory):
    unit = inventory.units["A-102"]
    r = sales("manager").post("/crm/leads", body(interested_unit_id=str(unit.id), timeline="within_3_months"))
    assert r.status_code == 201, r.text
    lead = r.json()
    assert lead["project"]["code"] == "TST" and lead["interested_unit"]["code"] == "A-102" and lead["timeline"] == "within_3_months"
    other = sales("manager").post("/realestate/projects", {"code": "OTH", "name": "Other", "city": "Jeddah"}).json()
    r = sales("manager").post("/crm/leads", body(project_id=other["id"], interested_unit_id=str(unit.id)))
    assert r.status_code == 422 and r.json()["error"]["code"] == "unit_project_mismatch"
    assert sales("manager").post("/crm/leads", body(timeline="someday")).status_code == 422
    # Personal data stays out of the outbox and the audit summary.
    ev = db.scalar(select(AutomationEvent).where(AutomationEvent.event_type == "lead.created", AutomationEvent.entity_id == lead["id"]))
    assert "buyer@example.com" not in str(ev.payload) and "Fictional Buyer" not in str(ev.payload)
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "crm.lead_created", AuditLog.entity_id == lead["id"]))
    assert "Fictional Buyer" not in audit.summary


def test_update_follow_up_and_privacy_of_changes(sales, db, inventory):
    lead = new_lead(sales, db)
    a1 = sales("agent1")
    future = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    r = a1.patch(
        f"/crm/leads/{lead['id']}",
        {"phone": "+966 55 999 0000", "budget_max": "950000", "next_follow_up_at": future, "project_id": str(inventory.project.id)},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["budget_max"] == "950000.00" and d["project"]["code"] == "TST" and same_minute(d["next_follow_up_at"], future)
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "crm.lead_updated", AuditLog.entity_id == lead["id"]))
    assert audit.changes["phone"] == "changed" and "+966 55 999 0000" not in str(audit.changes)
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    assert a1.patch(f"/crm/leads/{lead['id']}", {"next_follow_up_at": past}).json()["error"]["code"] == "follow_up_in_past"
    assert a1.patch(f"/crm/leads/{lead['id']}", {"phone": None, "email": None}).json()["error"]["code"] == "contact_required"
    assert a1.patch(f"/crm/leads/{lead['id']}", {"budget_min": "2000000"}).json()["error"]["code"] == "invalid_budget"
    timeline = a1.get(f"/crm/leads/{lead['id']}/activities").json()
    assert any("Follow-up scheduled" in t["body"] for t in timeline)


def test_stage_transitions_reasons_and_timeline(sales, db):
    lead = new_lead(sales, db)
    a1 = sales("agent1")
    stage = lambda s, reason=None: a1.post(f"/crm/leads/{lead['id']}/stage", {"stage": s, "reason": reason})  # noqa: E731
    r = stage("qualified")  # forward jumps are allowed
    assert r.status_code == 200 and r.json()["stage"] == "qualified" and "contacted" not in r.json()["allowed_stages"]
    assert stage("contacted").json()["error"]["code"] == "invalid_transition"  # no going back
    assert stage("qualified").json()["error"]["code"] == "same_stage"
    assert stage("lost").json()["error"]["code"] == "reason_required"
    r = stage("lost", "Chose another developer")
    assert r.json()["stage"] == "lost" and r.json()["close_reason"] == "Chose another developer" and r.json()["next_follow_up_at"] is None
    assert r.json()["follow_up_overdue"] is False
    r = stage("viewing")  # reopen from lost
    assert r.json()["stage"] == "viewing" and r.json()["close_reason"] is None and r.json()["next_follow_up_at"]
    assert stage("won").json()["error"]["code"] == "reason_required"
    r = stage("won", "Signed SPA")
    assert r.json()["allowed_stages"] == [] and stage("lost", "x" * 5).json()["error"]["code"] == "invalid_transition"
    changes = [t["body"] for t in a1.get(f"/crm/leads/{lead['id']}/activities").json() if t["type"] == "stage_change"]
    assert changes == [
        "Stage: viewing → won — Signed SPA",
        "Stage: lost → viewing",
        "Stage: qualified → lost — Chose another developer",
        "Stage: new → qualified",
    ]
    ev = [
        e.payload["to"]
        for e in db.scalars(
            select(AutomationEvent).where(AutomationEvent.event_type == "lead.stage_changed").order_by(AutomationEvent.created_at)
        )
    ]
    assert ev == ["qualified", "lost", "viewing", "won"]
    assert db.scalar(select(AuditLog).where(AuditLog.action == "crm.lead_stage_changed")) is not None


def test_activities_update_last_activity_and_follow_up(sales, db):
    lead = new_lead(sales, db)
    a1 = sales("agent1")
    earlier = (datetime.now(UTC) - timedelta(hours=3)).isoformat()
    follow = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    r = a1.post(
        f"/crm/leads/{lead['id']}/activities",
        {"type": "call", "body": "Discussed 2-bedroom options", "occurred_at": earlier, "next_follow_up_at": follow},
    )
    assert r.status_code == 201, r.text
    assert r.json()[0]["type"] == "call" and r.json()[0]["performed_by"]["full_name"] == "Agent One"
    d = a1.get(f"/crm/leads/{lead['id']}").json()
    assert same_minute(d["last_activity_at"], earlier) and same_minute(d["next_follow_up_at"], follow)
    a1.post(f"/crm/leads/{lead['id']}/activities", {"type": "whatsapp", "body": "Sent brochure"})
    assert datetime.fromisoformat(a1.get(f"/crm/leads/{lead['id']}").json()["last_activity_at"]) > datetime.fromisoformat(earlier)
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    assert a1.post(f"/crm/leads/{lead['id']}/activities", {"type": "note", "body": "x" * 5, "occurred_at": tomorrow}).status_code == 422
    assert a1.post(f"/crm/leads/{lead['id']}/activities", {"type": "system", "body": "spoof"}).status_code == 422
    assert {t["type"] for t in a1.get(f"/crm/leads/{lead['id']}/activities").json()} >= {"call", "whatsapp"}


def test_reassignment_is_manager_only(sales, db):
    lead = new_lead(sales, db)
    m, a1 = sales("manager"), sales("agent1")
    target = str(sales.users["agent2"].id)
    assert a1.post(f"/crm/leads/{lead['id']}/assign", {"owner_user_id": target}).status_code == 403
    r = m.post(f"/crm/leads/{lead['id']}/assign", {"owner_user_id": str(sales.users["marketing"].id)})
    assert r.json()["error"]["code"] == "invalid_owner"
    r = m.post(f"/crm/leads/{lead['id']}/assign", {"owner_user_id": target, "reason": "Agent One on leave"})
    assert r.status_code == 200 and r.json()["owner"]["full_name"] == "Agent Two"
    assert m.post(f"/crm/leads/{lead['id']}/assign", {"owner_user_id": target}).json()["error"]["code"] == "same_owner"
    # The previous owner loses access; the new owner gains it.
    assert a1.get(f"/crm/leads/{lead['id']}").status_code == 404
    assert "change_stage" in sales("agent2").get(f"/crm/leads/{lead['id']}").json()["allowed_actions"]
    names = [u["full_name"] for u in m.get("/crm/sales-users").json()]
    assert "Agent One" in names and "Agent Two" in names and "Mona Marketing" not in names
    assert a1.get("/crm/sales-users").status_code == 403
    assert db.scalar(select(AuditLog).where(AuditLog.action == "crm.lead_reassigned")).changes["owner_user_id"][1] == target


def test_scope_and_work_permissions(sales, db):
    own = new_lead(sales, db, owner="agent1")
    other = new_lead(sales, db, owner="agent2")
    marketing_lead = new_lead(sales, db, owner="agent2", creator="marketing")
    a1, mk, emp, m = sales("agent1"), sales("marketing"), sales("employee"), sales("manager")
    assert {x["id"] for x in a1.get("/crm/leads").json()["items"]} == {own["id"]}
    assert a1.get(f"/crm/leads/{other['id']}").status_code == 404
    assert a1.get("/crm/leads", params={"scope": "all"}).status_code == 403
    assert a1.post(f"/crm/leads/{other['id']}/stage", {"stage": "contacted"}).status_code == 404
    # The creator (marketing) can see their lead but not work it.
    d = mk.get(f"/crm/leads/{marketing_lead['id']}").json()
    assert d["allowed_actions"] == [] and d["allowed_stages"] == []
    assert mk.post(f"/crm/leads/{marketing_lead['id']}/stage", {"stage": "contacted"}).status_code == 403
    assert mk.post(f"/crm/leads/{marketing_lead['id']}/activities", {"type": "note", "body": "hello"}).status_code == 403
    assert emp.get("/crm/leads").status_code == 403
    # Managers see and work everything.
    assert m.get("/crm/leads", params={"scope": "all"}).json()["total"] == 3
    assert m.post(f"/crm/leads/{other['id']}/stage", {"stage": "contacted"}).status_code == 200
    assert set(m.get(f"/crm/leads/{own['id']}").json()["allowed_actions"]) >= {
        "edit",
        "change_stage",
        "add_activity",
        "reassign",
        "reserve",
    }


def test_stats_and_filters(sales, db, inventory):
    a = new_lead(sales, db, owner="agent1", project_id=str(inventory.project.id))
    new_lead(sales, db, owner="agent1")
    new_lead(sales, db, owner=None)
    db.execute(update(Lead).where(Lead.id == a["id"]).values(next_follow_up_at=datetime.now(UTC) - timedelta(hours=1)))
    db.commit()
    m, a1 = sales("manager"), sales("agent1")
    sales("agent1").post(f"/crm/leads/{a['id']}/stage", {"stage": "viewing"})
    s = m.get("/crm/leads/stats", params={"scope": "all"}).json()
    assert (s["new"], s["viewing"], s["open"], s["overdue"], s["unassigned"]) == (2, 1, 3, 1, 1)
    assert a1.get("/crm/leads/stats").json()["open"] == 2
    q = lambda **p: m.get("/crm/leads", params={"scope": "all", **p}).json()["total"]  # noqa: E731
    assert q(stage="viewing") == 1 and q(stage="open") == 3 and q(overdue=True) == 1
    assert q(project_id=str(inventory.project.id)) == 1 and q(owner_user_id=str(sales.users["agent1"].id)) == 2
    assert q(q=a["code"]) == 1
    assert m.get("/crm/leads", params={"scope": "all", "overdue": True}).json()["items"][0]["follow_up_overdue"] is True


@pytest.fixture
def wf(db, connection, roles):
    from sqlalchemy.orm import Session

    sync_definitions(db)
    db.commit()
    return Engine(lambda: Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False), "worker-crm")


def test_registration_scores_budget_fit_and_uses_project_pool(sales, db, inventory, wf):
    # sales fixture makes two agents; leads with a project use the project's pool, others "default".
    m = sales("manager")
    with_project = m.post(
        "/crm/leads", body(project_id=str(inventory.project.id), budget_max="1000000", bedrooms_wanted=2, timeline="immediate")
    ).json()
    without = m.post("/crm/leads", body(budget_max="100000")).json()
    wf.run_until_idle()
    db.expire_all()
    l1, l2 = db.get(Lead, with_project["id"]), db.get(Lead, without["id"])
    reasons1 = [r["reason"] for r in l1.score_reasons]
    assert "Budget fits 1 available unit" in reasons1 and "Timeline: ready to buy now" in reasons1  # A-102 (2 BR, 900k)
    assert "No available units within budget" in [r["reason"] for r in l2.score_reasons]
    pools = {s.pool for s in db.scalars(select(SalesAssignmentState))}
    assert {"TST", "default"} <= pools
    assert l1.owner_user_id and l2.owner_user_id
    assert db.scalar(select(AutomationEvent).where(AutomationEvent.event_type == "lead.assigned", AutomationEvent.entity_id == str(l1.id)))


def test_existing_lead_scores_are_not_recalculated(sales, db, inventory, wf):
    """Decision C2: leads registered before Phase 5 keep their score; nothing re-scores them."""
    lead = new_lead(sales, db, owner=None, budget_max="1000000")
    db.execute(
        update(Lead)
        .where(Lead.id == lead["id"])
        .values(score=42, grade="warm", score_reasons=[{"points": 42, "reason": "legacy"}], stage="contacted")
    )
    db.commit()
    wf.run_until_idle()  # the registration workflow skips non-new leads
    db.expire_all()
    assert db.get(Lead, lead["id"]).score == 42
    sales("manager").patch(f"/crm/leads/{lead['id']}", {"timeline": "immediate", "budget_max": "5000000"})
    db.expire_all()
    assert db.get(Lead, lead["id"]).score == 42  # updates don't re-score either


def test_activity_dedupe_and_last_activity_never_moves_backwards(db, sales):
    lead = new_lead(sales, db)
    svc = CRMService(db)
    now = datetime.now(UTC)
    assert svc._activity(lead["id"], "system", "once", dedupe="k1", occurred_at=now) is not None
    assert svc._activity(lead["id"], "system", "twice", dedupe="k1", occurred_at=now) is None
    svc._activity(lead["id"], "note", "old", dedupe=None, occurred_at=now - timedelta(days=5))
    db.commit()
    db.expire_all()
    assert db.get(Lead, lead["id"]).last_activity_at == now
    assert len(db.scalars(select(LeadActivity).where(LeadActivity.dedupe_key == "k1")).all()) == 1
