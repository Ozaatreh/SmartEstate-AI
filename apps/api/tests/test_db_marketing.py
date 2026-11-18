"""Phase 7B — Marketing Studio: campaigns, EN/AR content, versions, review through the shared approval engine
(no self-approval, human decisions only, no auto-publishing), channel rules, facts check, permissions, AI flag."""

from __future__ import annotations

import pytest
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.ai.gateway import AIGateway
from app.automation.engine import Engine
from app.automation.manager import sync_definitions
from app.automation.models import AutomationEvent, WorkflowExecution
from app.modules.approvals.models import ApprovalRequest
from app.modules.audit.models import AuditLog
from app.modules.identity.models import Permission
from app.modules.marketing.models import MarketingContent, MarketingContentVersion
from app.modules.notifications.models import Notification
from app.seed.reference import seed_reference
from tests.ai_fakes import FAKE_KEY, Script, factory, message
from tests.business_fixtures import Actor
from tests.test_unit_core import make_settings

pytestmark = pytest.mark.db


@pytest.fixture
def team(app, db, make_user):
    # Reference data (incl. the marketing approval policy) — other test modules may have truncated the test database.
    seed_reference(db)
    db.commit()
    users = {
        "lina": make_user("marketing_specialist", name="Lina Specialist"),
        "omar": make_user("marketing_specialist", name="Omar Specialist"),
        "huda": make_user("marketing_manager", name="Huda Manager"),
        "sami": make_user("marketing_manager", name="Sami Manager"),
        "ceo": make_user("executive", name="Faisal Exec"),
        "agent": make_user("sales_agent", name="Yousef Agent"),
    }
    cache: dict[str, Actor] = {}

    def get(key: str) -> Actor:
        if key not in cache:
            cache[key] = Actor(app, users[key])
        return cache[key]

    get.users = users  # type: ignore[attr-defined]
    return get


def campaign(team, inventory, **kw) -> dict:
    r = team("lina").post("/marketing/campaigns", {
        "name": "NOVA spring launch", "objective": "Book viewings for 2-bedroom units", "project_id": str(inventory.project.id),
        "channels": ["instagram", "x", "email"], "start_date": "2026-12-01", "end_date": "2027-01-31", **kw,
    })
    assert r.status_code == 201, r.text
    return r.json()


def content(team, camp: dict, who: str = "lina", **kw) -> dict:
    body = {"campaign_id": camp["id"], "channel": "instagram", "language": "en", "headline": "Life at Test Residences",
            "body": "Pool, garden views and 2-bedroom homes from SAR 650,000.", "call_to_action": "Book a viewing",
            "hashtags": ["Riyadh", "#NewHome"], **kw}
    r = team(who).post("/marketing/content", body)
    assert r.status_code == 201, r.text
    return r.json()


def pending_for(actor: Actor) -> list[dict]:
    return actor.get("/approvals", params={"box": "pending"}).json()["items"]


# ================================================================== full lifecycle
def test_specialist_writes_en_and_ar_content_and_manager_approves(app, db, team, inventory):
    camp = campaign(team, inventory)
    assert camp["code"].startswith("MC-") and camp["status"] == "draft" and set(camp["allowed_actions"]) >= {"edit", "archive", "add_content"}
    en = content(team, camp)
    assert en["hashtags"] == ["#Riyadh", "#NewHome"] and en["version"] == 1 and en["status"] == "draft"
    ar = content(team, camp, channel="x", language="ar", headline=None, body="شقق بغرفتي نوم في مشروع تست ريزيدنسز.", call_to_action="احجز زيارتك",
                 hashtags=["الرياض"])
    assert ar["language"] == "ar" and ar["hashtags"] == ["#الرياض"]

    # Edit the draft twice → versions 2 and 3, each kept.
    lina = team("lina")
    r = lina.patch(f"/marketing/content/{en['id']}", {"body": "Pool and garden views. 2-bedroom homes from SAR 650,000.", "note": "Tighter copy"})
    assert r.status_code == 200 and r.json()["version"] == 2
    r = lina.patch(f"/marketing/content/{en['id']}", {"call_to_action": "Request a viewing"})
    d = r.json()
    assert d["version"] == 3 and [v["version"] for v in d["versions"]] == [3, 2, 1] and d["versions"][1]["note"] == "Tighter copy"
    assert d["versions"][2]["body"].startswith("Pool, garden views")  # the original text is preserved
    assert lina.patch(f"/marketing/content/{en['id']}", {"call_to_action": "Request a viewing"}).json()["version"] == 3  # no-op save

    # Submit → pending, review opened in the same transaction, event for the workflow.
    d = lina.post(f"/marketing/content/{en['id']}/submit").json()
    assert d["status"] == "pending_approval" and d["approval_id"] and not d["can_decide"]
    assert d["decide_blocked_reason"] == "You can't approve a request you submitted."
    req = db.get(ApprovalRequest, d["approval_id"])
    assert (req.entity_type, req.status, req.amount, [s.level for s in req.steps]) == ("marketing_content", "pending", 0, ["marketing"])
    assert db.scalar(select(AutomationEvent).where(AutomationEvent.event_type == "marketing_content.submitted",
                                                   AutomationEvent.entity_id == en["id"]))
    assert lina.patch(f"/marketing/content/{en['id']}", {"body": "x"}).json()["error"]["code"] == "content_locked"

    # The manager sees it in the approval inbox and in the content view; the specialist can't decide it.
    huda = team("huda")
    assert [i["entity_code"] for i in pending_for(huda)] == [en["code"]]
    assert pending_for(lina) == []
    assert huda.get(f"/marketing/content/{en['id']}").json()["allowed_actions"] == ["approve", "reject"]
    r = lina.post(f"/approvals/{d['approval_id']}/approve", {"comment": "LGTM"})
    assert r.status_code in (403, 404)
    note = db.scalar(select(Notification).where(Notification.user_id == team.users["huda"].id, Notification.type == "approval.requested"))
    assert note is not None and "SAR" not in (note.body or "")  # no meaningless "SAR 0.00" for content

    # Approve → approved, and nothing is published or sent anywhere.
    events_before = set(db.scalars(select(AutomationEvent.id)))  # ids, not a count: created_at ties inside the test transaction
    r = huda.post(f"/approvals/{d['approval_id']}/approve", {"comment": "Good to go"})
    assert r.status_code == 200, r.text
    d = huda.get(f"/marketing/content/{en['id']}").json()
    assert d["status"] == "approved" and d["approvals"][0]["status"] == "approved" and d["approvals"][0]["version"] == 3
    assert d["approvals"][0]["steps"][0]["decided_by"]["full_name"] == "Huda Manager"
    new_events = [e.event_type for e in db.scalars(select(AutomationEvent)) if e.id not in events_before]
    assert new_events == ["approval.decided"]  # no publishing event of any kind
    assert lina.patch(f"/marketing/content/{en['id']}", {"body": "changed"}).json()["error"]["code"] == "content_locked"
    assert db.scalar(select(AuditLog).where(AuditLog.action == "marketing.content_approved", AuditLog.entity_id == en["id"]))
    # The Arabic draft is untouched and still a draft.
    assert lina.get(f"/marketing/content/{ar['id']}").json()["status"] == "draft"


def test_rejected_content_is_revised_and_resubmitted(db, team, inventory):
    camp = campaign(team, inventory)
    c = content(team, camp)
    lina, huda = team("lina"), team("huda")
    approval = lina.post(f"/marketing/content/{c['id']}/submit").json()["approval_id"]
    assert huda.post(f"/approvals/{approval}/reject", {"comment": ""}).status_code == 422  # a reason is required
    assert huda.post(f"/approvals/{approval}/reject", {"comment": "Add the handover date"}).status_code == 200
    d = lina.get(f"/marketing/content/{c['id']}").json()
    assert d["status"] == "rejected" and d["rejection_comment"] == "Add the handover date" and set(d["allowed_actions"]) >= {"edit", "submit"}
    d = lina.patch(f"/marketing/content/{c['id']}", {"body": "Pool and garden views; homes from SAR 650,000. Handover 2028."}).json()
    assert (d["status"], d["version"], d["versions"][0]["note"], d["rejection_comment"]) == ("draft", 2, "Revised after rejection", None)
    second = lina.post(f"/marketing/content/{c['id']}/submit").json()
    assert second["approval_id"] != approval and len(second["approvals"]) == 2
    assert huda.post(f"/approvals/{second['approval_id']}/approve", {}).status_code == 200
    d = lina.get(f"/marketing/content/{c['id']}").json()
    assert [a["status"] for a in d["approvals"]] == ["approved", "rejected"] and [a["version"] for a in d["approvals"]] == [2, 1]


def test_nobody_approves_content_they_wrote_or_edited(app, db, team, inventory, roles):
    # Give one manager the right to write content too: having edited it, she may no longer approve it.
    roles["marketing_manager"].permissions.append(db.scalar(select(Permission).where(Permission.code == "marketing.content.create")))
    db.commit()
    camp = campaign(team, inventory)
    c = content(team, camp)
    huda, sami = team("huda"), team("sami")
    assert huda.patch(f"/marketing/content/{c['id']}", {"call_to_action": "Visit us"}).status_code == 200
    approval = team("lina").post(f"/marketing/content/{c['id']}/submit").json()["approval_id"]
    d = huda.get(f"/marketing/content/{c['id']}").json()
    assert not d["can_decide"] and d["decide_blocked_reason"] == "You can't approve content you wrote or edited."
    assert pending_for(huda) == [] and huda.post(f"/approvals/{approval}/approve", {}).status_code in (403, 404)
    assert [i["entity_code"] for i in pending_for(sami)] == [c["code"]]
    assert not db.scalar(select(Notification).where(Notification.user_id == team.users["huda"].id, Notification.type == "approval.requested"))
    assert sami.post(f"/approvals/{approval}/approve", {}).status_code == 200
    # A super admin who submits their own content can't approve it either.
    admin = Actor(app, team.users["huda"])  # same person, fresh client
    assert admin.get("/approvals", params={"box": "pending"}).json()["items"] == []


def test_permissions_are_enforced_by_the_api(team, inventory):
    camp = campaign(team, inventory)
    c = content(team, camp)
    agent, ceo, huda = team("agent"), team("ceo"), team("huda")
    assert agent.get("/marketing/campaigns").status_code == 403
    assert agent.get(f"/marketing/content/{c['id']}").status_code == 403
    assert ceo.get("/marketing/campaigns").json()["total"] == 1  # executives can read
    valid = {"name": "Exec campaign", "objective": "Awareness", "project_id": camp["project"]["id"], "channels": ["x"]}
    assert ceo.post("/marketing/campaigns", valid).status_code == 403
    assert huda.post("/marketing/content", {"campaign_id": camp["id"], "channel": "x", "language": "en", "body": "Hi there"}).status_code == 403
    assert huda.patch(f"/marketing/content/{c['id']}", {"body": "x"}).status_code == 403
    assert ceo.get(f"/marketing/content/{c['id']}").json()["allowed_actions"] == []


# ================================================================== rules
def test_channel_and_campaign_rules(team, inventory):
    camp = campaign(team, inventory)
    lina = team("lina")
    base = {"campaign_id": camp["id"], "language": "en", "body": "Hello"}
    errors = {
        "not a campaign channel": {**base, "channel": "linkedin"},
        "too long for X": {**base, "channel": "x", "body": "a" * 281},
        "email needs a subject": {**base, "channel": "email"},
        "no hashtags in email": {**base, "channel": "email", "headline": "Subject", "hashtags": ["#a"]},
        "bad hashtag": {**base, "channel": "x", "hashtags": ["two words"]},
        "unknown field": {**base, "channel": "x", "published": True},
    }
    for label, body in errors.items():
        assert lina.post("/marketing/content", body).status_code == 422, label
    assert lina.post("/marketing/campaigns", {"name": "Bad dates", "objective": "Test", "project_id": camp["project"]["id"],
                                              "channels": ["x"], "start_date": "2027-02-01", "end_date": "2027-01-01"}).status_code == 422
    c = content(team, camp, channel="x", hashtags=[])
    r = lina.patch(f"/marketing/campaigns/{camp['id']}", {"channels": ["email"]})
    assert r.json()["error"]["code"] == "channel_in_use"
    lina.post(f"/marketing/content/{c['id']}/submit")
    assert lina.post(f"/marketing/campaigns/{camp['id']}/archive").json()["error"]["code"] == "content_pending"
    approval_id = lina.get(f"/marketing/content/{c['id']}").json()["approval_id"]
    assert team("huda").post(f"/approvals/{approval_id}/approve", {}).status_code == 200
    archived = lina.post(f"/marketing/campaigns/{camp['id']}/archive").json()
    assert archived["status"] == "archived" and archived["allowed_actions"] == []
    assert lina.post("/marketing/content", {**base, "channel": "x"}).json()["error"]["code"] == "campaign_archived"
    assert lina.patch(f"/marketing/campaigns/{camp['id']}", {"name": "Renamed"}).json()["error"]["code"] == "campaign_archived"


def test_facts_check_flags_invented_figures(team, inventory):
    camp = campaign(team, inventory)
    lina = team("lina")
    facts = lina.get(f"/marketing/projects/{camp['project']['id']}/facts").json()
    assert facts["price_from_sar"] == "420000.00" and "Pool" in facts["amenities"] and facts["payment_plans"]
    ok = lina.post("/marketing/facts-check", {"project_id": camp["project"]["id"],
                                              "body": "Studios from SAR 420,000, 2-bedroom homes at SAR 900,000, 10% down. Floor 5. Since 2026."}).json()
    assert ok == []
    bad = lina.post("/marketing/facts-check", {"project_id": camp["project"]["id"],
                                               "body": "Homes from SAR 600,000 or 1.5M, only 5% down, 5-bedroom villas. ٦٠٠٬٠٠٠ ريال"}).json()
    assert {w["kind"] for w in bad} == {"price", "percentage", "bedrooms"} and len([w for w in bad if w["kind"] == "price"]) == 3
    c = content(team, camp, body="Homes from SAR 600,000.")
    assert [w["kind"] for w in lina.get(f"/marketing/content/{c['id']}").json()["fact_warnings"]] == ["price"]


# ================================================================== AI stays off; history is append-only; workflow
def test_ai_generation_is_off_and_manual_flow_works(app, sessions_factory, team, inventory):
    script = Script(message())
    s = make_settings(ai_enabled="true", anthropic_api_key=SecretStr(FAKE_KEY), ai_marketing_studio_enabled="false")
    app.state.ai_gateway = AIGateway(s, session_factory=sessions_factory, provider_factory=factory(script, retries=0), environ={})
    lina = team("lina")
    assert lina.get("/marketing/ai-status").json() == {
        "enabled": False, "reason": "AI drafting is turned off (AI_MARKETING_STUDIO_ENABLED=false). Write and edit content manually."}
    r = lina.post("/marketing/content/generate", {})
    assert r.status_code == 503 and r.json()["error"]["code"] == "ai_feature_disabled" and script.calls == 0
    camp = campaign(team, inventory)
    c = content(team, camp)
    assert lina.post(f"/marketing/content/{c['id']}/submit").json()["status"] == "pending_approval"
    assert c["generated_by_ai"] is False


@pytest.fixture
def sessions_factory(connection):
    return lambda: Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)


def test_version_history_is_append_only(db, team, inventory):
    c = content(team, campaign(team, inventory))
    v = db.scalar(select(MarketingContentVersion).where(MarketingContentVersion.content_id == c["id"]))
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE marketing_content_versions SET body = 'x' WHERE id = :i"), {"i": v.id})
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM marketing_content_versions WHERE id = :i"), {"i": v.id})
    db.rollback()


def test_content_review_workflow_checks_the_route(db, connection, roles, team, inventory):
    sync_definitions(db)
    db.commit()
    engine = Engine(lambda: Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False), "worker-7b")
    c = content(team, campaign(team, inventory))
    team("lina").post(f"/marketing/content/{c['id']}/submit")
    engine.run_until_idle()
    db.expire_all()
    ex = db.scalar(select(WorkflowExecution).where(WorkflowExecution.workflow_key == "marketing.content_review",
                                                   WorkflowExecution.trigger_type == "event"))
    assert ex is not None and ex.status == "succeeded"
    assert ex.result["verify_route"]["status"] == "ok" and ex.result["verify_route"]["approvers"] == 2  # Huda and Sami
    assert db.get(MarketingContent, c["id"]).status == "pending_approval"  # the workflow never decides
