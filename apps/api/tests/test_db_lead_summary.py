"""Phase 6B — AI Lead Intelligence: access rules, data minimisation, structured advisory output, graceful failure.

The AI provider is the real Anthropic SDK over a scripted HTTP transport (tests/ai_fakes.py); no network calls."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.ai.gateway import AIGateway
from app.ai.models import AIUsage
from app.modules.audit.models import AuditLog
from app.modules.crm.models import Lead, LeadActivity
from tests.ai_fakes import FAKE_KEY, Script, error, factory, message
from tests.test_unit_core import make_settings

pytestmark = pytest.mark.db

NAME, PHONE, EMAIL = "Rana Fictional", "+966 50 111 2222", "rana.fictional@example.com"
SUMMARY = {
    "overview": "Qualified buyer looking for a 2-bedroom apartment in Test Residences within 3 months.",
    "buying_signals": ["Asked for a second viewing of A-102.", "Budget matches the unit's list price."],
    "concerns": ["Financing approval is not recorded."],
    "next_action": "Call Rana Fictional on +966 50 111 2222 to confirm financing.",
    "next_action_reason": "Financing is the main open question before negotiation.",
}


@pytest.fixture
def sessions(connection):
    return lambda: Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)


def install(app, sessions, script: Script, *, enabled: bool = True) -> Script:
    s = make_settings(ai_enabled="true" if enabled else "false", anthropic_api_key=SecretStr(FAKE_KEY))
    app.state.ai_gateway = AIGateway(s, session_factory=sessions, provider_factory=factory(script, retries=0), environ={})
    return script


def make_lead(sales, db, inventory, *, owner: str = "agent1") -> dict:
    unit = inventory.units["A-102"]
    r = sales("manager").post("/crm/leads", {
        "full_name": NAME, "phone": PHONE, "email": EMAIL, "source": "website", "interest": f"2BR, call me on {PHONE}",
        "budget_min": "850000", "budget_max": "950000", "bedrooms_wanted": 2, "timeline": "within_3_months",
        "interested_unit_id": str(unit.id), "notes": f"{NAME} prefers evening calls. Email {EMAIL}.",
    })
    assert r.status_code == 201, r.text
    lead = r.json()
    db.execute(update(Lead).where(Lead.id == lead["id"]).values(
        owner_user_id=sales.users[owner].id, next_follow_up_at=datetime.now(UTC) + timedelta(days=1)))
    db.commit()
    a = sales(owner)
    assert a.post(f"/crm/leads/{lead['id']}/activities", {"type": "viewing", "body": f"Viewed A-102 with {NAME}; wants a second visit."}).status_code == 201
    assert a.post(f"/crm/leads/{lead['id']}/activities", {"type": "call", "body": "Asked about payment plans. Reach him at 0501112222."}).status_code == 201
    return lead


def snapshot(db, lead_id) -> tuple:
    db.expire_all()
    lead = db.get(Lead, lead_id)
    activities = db.scalar(select(func.count()).select_from(LeadActivity).where(LeadActivity.lead_id == lead_id))
    return (lead.stage, lead.owner_user_id, lead.next_follow_up_at, lead.updated_at, lead.score, lead.notes, activities)


def test_owner_gets_structured_advisory_summary_with_minimal_context(app, db, sales, inventory, sessions):
    lead = make_lead(sales, db, inventory)
    script = install(app, sessions, Script(message(json.dumps(SUMMARY))))
    before = snapshot(db, lead["id"])
    r = sales("agent1").post(f"/crm/leads/{lead['id']}/ai-summary")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ai_generated"] is True and "advisory" in out["advisory_notice"].lower()
    assert out["lead_code"] == lead["code"] and out["interactions_considered"] >= 2
    assert out["buying_signals"] == SUMMARY["buying_signals"] and out["concerns"] == SUMMARY["concerns"]
    # Contact details the model produced are redacted from the output, too.
    assert NAME not in json.dumps(out) and PHONE not in json.dumps(out) and "[redacted]" in out["next_action"]

    # What the model received: the necessary context, never contact details or staff names.
    (sent,) = script.requests
    assert sent["model"] == "claude-opus-5-5" and "tools" not in sent
    prompt = json.dumps(sent)
    for secret in (NAME, "Rana", PHONE, EMAIL, "0501112222", "Agent One", "Sara Manager"):
        assert secret not in prompt, secret
    context = json.loads(sent["messages"][0]["content"].split("<lead_data>\n")[1].split("\n</lead_data>")[0])
    assert context["stage"] == "new" and context["preferences"]["budget_max_sar"] == "950000"
    assert context["preferences"]["timeline"] == "within_3_months" and context["unit_interest"]["code"] == "A-102"
    assert context["project_interest"]["code"] == "TST" and context["follow_up"]["next_follow_up_at"]
    assert [i["type"] for i in context["interactions"]][-2:] == ["viewing", "call"]
    assert "full_name" not in prompt and "\"phone\"" not in prompt and "\"email\"" not in prompt

    # Advisory only: nothing in the CRM changed; an audit entry (ids/codes only) and a usage row were written.
    assert snapshot(db, lead["id"]) == before
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "crm.lead_ai_summary_generated", AuditLog.entity_id == lead["id"]))
    assert audit is not None and NAME not in audit.summary
    usage = db.scalar(select(AIUsage).where(AIUsage.capability == "lead_summary"))
    assert usage.status == "succeeded" and usage.actor_user_id == sales.users["agent1"].id


def test_access_follows_lead_ownership_and_rbac(app, db, sales, inventory, sessions):
    lead = make_lead(sales, db, inventory, owner="agent1")
    script = install(app, sessions, Script(message(json.dumps(SUMMARY))))
    path = f"/crm/leads/{lead['id']}/ai-summary"
    assert sales("agent2").post(path).status_code == 404  # another agent's lead: invisible
    assert sales("employee").post(path).status_code == 404
    # The marketing manager can't see a lead they didn't register.
    assert sales("marketing").post(path).status_code == 404
    assert script.calls == 0  # access is decided before anything reaches the model
    assert "ai_summary" in sales("agent1").get(f"/crm/leads/{lead['id']}").json()["allowed_actions"]
    assert "ai_summary" in sales("manager").get(f"/crm/leads/{lead['id']}").json()["allowed_actions"]
    assert sales("agent1").post(path).status_code == 200
    assert sales("manager").post(path).status_code == 200  # managers summarise any lead
    assert script.calls == 2


def test_viewer_who_cannot_work_the_lead_is_refused(app, db, sales, sessions):
    r = sales("marketing").post("/crm/leads", {"full_name": NAME, "phone": PHONE, "source": "campaign"})
    lead = r.json()
    db.execute(update(Lead).where(Lead.id == lead["id"]).values(owner_user_id=sales.users["agent2"].id))
    db.commit()
    script = install(app, sessions, Script(message(json.dumps(SUMMARY))))
    detail = sales("marketing").get(f"/crm/leads/{lead['id']}").json()
    assert "ai_summary" not in detail["allowed_actions"]
    assert sales("marketing").post(f"/crm/leads/{lead['id']}/ai-summary").status_code == 403
    assert script.calls == 0


@pytest.mark.parametrize(
    ("step", "enabled", "code"),
    [
        (message(json.dumps(SUMMARY)), False, "ai_disabled"),
        (error(529, "overloaded_error"), True, "ai_unavailable"),
        ({**message("", stop="refusal"), "content": []}, True, "ai_refused"),  # a real refusal has no content
        (message("not json at all"), True, "ai_invalid_response"),
    ],
)
def test_ai_failures_degrade_gracefully_and_crm_keeps_working(app, db, sales, inventory, sessions, step, enabled, code):
    lead = make_lead(sales, db, inventory)
    install(app, sessions, Script(step), enabled=enabled)
    before = snapshot(db, lead["id"])
    a1 = sales("agent1")
    r = a1.post(f"/crm/leads/{lead['id']}/ai-summary")
    assert r.status_code == 503 and r.json()["error"]["code"] == code
    assert FAKE_KEY not in r.text and NAME not in r.text
    assert snapshot(db, lead["id"]) == before
    assert db.scalar(select(AuditLog).where(AuditLog.action == "crm.lead_ai_summary_generated")) is None
    # The rest of the CRM is unaffected.
    assert a1.get(f"/crm/leads/{lead['id']}").status_code == 200
    assert a1.post(f"/crm/leads/{lead['id']}/activities", {"type": "note", "body": "Still interested."}).status_code == 201
    assert a1.post(f"/crm/leads/{lead['id']}/stage", {"stage": "contacted"}).status_code == 200


def test_unknown_lead_is_not_found(app, sales, sessions):
    script = install(app, sessions, Script(message(json.dumps(SUMMARY))))
    assert sales("manager").post("/crm/leads/00000000-0000-0000-0000-000000000000/ai-summary").status_code == 404
    assert script.calls == 0
