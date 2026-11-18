"""Phase 7A — public API boundary, public field allowlists, website inquiries → CRM leads, marketing AI flag.

The boundary tests call FastAPI directly without a session cookie: they don't depend on what any frontend sends."""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.automation.models import AutomationEvent
from app.modules.crm.models import Lead, LeadActivity
from app.modules.notifications.models import Notification
from app.modules.realestate.models import ReBuilding, ReProject, ReUnit
from app.public import catalog
from app.public import router as public_router
from app.public.inquiries import InquiryIn, InquiryService, issue_token
from tests.conftest import CSRF

pytestmark = pytest.mark.db

# Anonymous access is allowed only here. Everything else must answer 401 without a session.
PUBLIC_PREFIX = "/api/v1/public/"
ANONYMOUS_ALLOWED = {
    ("get", "/api/v1/health"),
    ("post", "/api/v1/auth/login"),
    ("post", "/api/v1/auth/logout"),  # clears the cookie; harmless without one
    ("get", "/api/v1/auth/me"),  # reports "not signed in"
}


def anonymous(app) -> TestClient:
    c = TestClient(app, base_url="http://127.0.0.1")
    c.headers.update(CSRF)
    return c


def fill(path: str) -> str:
    return re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)


# ================================================================== boundary
def test_every_non_public_route_requires_authentication(app):
    paths = app.openapi()["paths"]
    c = anonymous(app)
    checked, failures = 0, []
    for path, methods in paths.items():
        for method in methods:
            if path.startswith(PUBLIC_PREFIX) or (method, path) in ANONYMOUS_ALLOWED:
                continue
            r = c.request(method.upper(), fill(path), json={})
            checked += 1
            if r.status_code != 401:
                failures.append(f"{method.upper()} {path} → {r.status_code}")
    assert failures == [] and checked > 60


def test_anonymous_allowlist_exposes_nothing_private(app):
    c = anonymous(app)
    assert c.get("/api/v1/health").status_code == 200
    me = c.get("/api/v1/auth/me")
    assert me.status_code in (200, 401) and "email" not in me.text
    public = {p for p in app.openapi()["paths"] if p.startswith(PUBLIC_PREFIX)}
    assert public == {
        "/api/v1/public/assistant/status", "/api/v1/public/assistant/messages",
        "/api/v1/public/projects", "/api/v1/public/projects/{code}", "/api/v1/public/projects/{code}/units",
        "/api/v1/public/projects/{code}/units/{unit_code}", "/api/v1/public/models/{model_id}/file",
        "/api/v1/public/projects/{code}/images/{image_id}",  # approved uploaded images of published projects only
        "/api/v1/public/inquiries/form-token", "/api/v1/public/inquiries",
    }, "a new public endpoint needs a deliberate review and an update here"


def test_staff_cookie_does_not_widen_public_responses(app, inventory, make_user):
    from tests.business_fixtures import Actor

    admin = Actor(app, make_user("super_admin"))
    staff = admin.client.get("/api/v1/public/projects/TST").json()
    anon = anonymous(app).get("/api/v1/public/projects/TST").json()
    assert staff == anon


# ================================================================== field allowlists
@pytest.fixture
def catalogue(db, inventory):
    """TST is published; HID is not. A-101 is not a public unit; A-102 carries an internal note."""
    inventory.units["A-101"].is_public = False
    inventory.units["A-102"].notes = "INTERNAL: owner discount floor 820k"
    hidden = ReProject(code="HID", name="Hidden Towers", city="Jeddah", status="launched", is_published=False)
    db.add(hidden)
    db.flush()
    b = ReBuilding(project_id=hidden.id, code="H", name="Tower H", floors=3)
    db.add(b)
    db.flush()
    db.add(ReUnit(project_id=hidden.id, building_id=b.id, unit_number="101", unit_type="apartment", bedrooms=2, bathrooms=2,
                  floor=1, area_sqm=100, list_price=700000))
    db.commit()
    return inventory


def keys(model) -> set[str]:
    return set(model.model_fields)


def test_public_project_and_unit_responses_are_allowlisted(app, catalogue):
    c = anonymous(app)
    projects = c.get("/api/v1/public/projects").json()
    assert [p["code"] for p in projects] == ["TST"]  # unpublished HID is invisible
    assert set(projects[0]) == keys(catalog.PublicProject)
    detail = c.get("/api/v1/public/projects/TST").json()
    assert set(detail) == keys(catalog.PublicProjectDetail) and detail["is_demo_data"] is True
    assert {set(p) == keys(catalog.PublicPlan) for p in detail["payment_plans"]} == {True}
    units = c.get("/api/v1/public/projects/TST/units", params={"max_price": 1000000}).json()
    assert {u["code"] for u in units} == {"A-102", "B-101"}  # A-101 is not public
    assert all(set(u) == keys(catalog.PublicUnit) for u in units)
    unit = c.get("/api/v1/public/projects/TST/units/A-102").json()
    assert set(unit) == keys(catalog.PublicUnitDetail)
    assert all(set(p) == keys(catalog.PublicPlanBreakdown) for p in unit["payment_plans"]) and len(unit["payment_plans"]) == 2
    everything = json.dumps([projects, detail, units, unit])
    for secret in ("INTERNAL", "820k", "notes", "is_public", '"id"', "Hidden Towers"):
        assert secret not in everything, secret
    assert c.get("/api/v1/public/projects/HID").status_code == 404
    assert c.get("/api/v1/public/projects/HID/units").status_code == 404
    assert c.get("/api/v1/public/projects/TST/units/A-101").status_code == 404


def test_assistant_tools_see_only_published_projects(db, catalogue):
    units = catalog.search_units(db, max_price=None)
    assert {u.project_code for u in units} == {"TST"}
    assert "A-101" not in {u.code for u in units}


# ================================================================== inquiries
def token(settings, age: float = 10) -> str:
    return issue_token(settings, now=time.time() - age).token


def inquiry(settings, **kw) -> dict:
    return {"kind": "contact", "full_name": "Rana Fictional", "email": "rana.fictional@example.com", "phone": "+966 50 123 4567",
            "message": "Interested in a 2-bedroom.", "consent": True, "website": "", "form_token": token(settings), **kw}


@pytest.fixture(autouse=True)
def fresh_limiters(app):
    for attr in ("inquiry_ip_limiter", "inquiry_contact_limiter"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)


@pytest.mark.parametrize(("change", "field"), [
    ({"consent": False}, "consent"),
    ({"email": None, "phone": None}, "contact"),
    ({"phone": "call me maybe"}, "phone"),
    ({"message": ""}, "message"),
    ({"kind": "viewing", "project_code": "TST"}, "date"),
    ({"kind": "viewing", "project_code": "TST", "preferred_date": "2020-01-01"}, "past date"),
    ({"kind": "viewing", "project_code": "HID", "preferred_date": None}, "unpublished project"),
    ({"is_admin": True}, "unknown field"),
])
def test_inquiry_validation(app, db, catalogue, settings, change, field):
    body = inquiry(settings, **change)
    if field == "unpublished project":
        body["preferred_date"] = (date.today() + timedelta(days=3)).isoformat()
    r = anonymous(app).post("/api/v1/public/inquiries", json=body)
    assert r.status_code == 422, (field, r.text)
    assert db.scalar(select(func.count()).select_from(Lead)) == 0


def test_inquiry_creates_a_website_lead_through_the_lead_workflow(app, db, catalogue, settings):
    c = anonymous(app)
    when = (date.today() + timedelta(days=5)).isoformat()
    r = c.post("/api/v1/public/inquiries", json=inquiry(settings, kind="viewing", project_code="tst", unit_code="a-102",
                                                         preferred_date=when, message=None))
    assert r.status_code == 202 and r.json() == {"status": "received", "message": "Thank you — our sales team will contact you shortly."}
    lead = db.scalar(select(Lead))
    assert (lead.source, lead.full_name, lead.created_by) == ("website", "Rana Fictional", None)
    assert lead.consent_given_at is not None and lead.project_id == catalogue.project.id
    assert lead.interested_unit_id == catalogue.units["A-102"].id and lead.bedrooms_wanted == 2
    note = db.scalar(select(LeadActivity).where(LeadActivity.lead_id == lead.id))
    assert "Website viewing request" in note.body and when in note.body and "A-102" in note.body
    event = db.scalar(select(AutomationEvent).where(AutomationEvent.event_type == "lead.created", AutomationEvent.entity_id == str(lead.id)))
    assert event is not None and "rana" not in json.dumps(event.payload).lower()  # scoring/assignment run from this event


def test_repeat_inquiry_updates_the_existing_lead_with_an_identical_response(app, db, catalogue, settings, make_user):
    c = anonymous(app)
    first = c.post("/api/v1/public/inquiries", json=inquiry(settings))
    lead = db.scalar(select(Lead))
    owner = make_user("sales_agent")
    lead.owner_user_id = owner.id
    db.commit()
    again = c.post("/api/v1/public/inquiries", json=inquiry(settings, email="RANA.Fictional@Example.com", phone=None,
                                                             message="Can someone call me today?"))
    assert first.status_code == again.status_code == 202 and first.json() == again.json()
    assert db.scalar(select(func.count()).select_from(Lead)) == 1
    bodies = list(db.scalars(select(LeadActivity.body).where(LeadActivity.lead_id == lead.id)))
    assert len(bodies) == 2 and any("call me today" in b for b in bodies)
    assert db.scalar(select(Notification).where(Notification.user_id == owner.id, Notification.type == "crm.inquiry")) is not None
    # Same phone written differently also matches.
    c.post("/api/v1/public/inquiries", json=inquiry(settings, email=None, phone="050-123-4567"))
    assert db.scalar(select(func.count()).select_from(Lead)) == 1


@pytest.mark.parametrize("spam", [{"website": "https://spam.example"}, {"form_token": "x" * 12}, {"fresh": True}])
def test_spam_gets_the_same_answer_and_creates_nothing(app, db, catalogue, settings, spam):
    body = inquiry(settings)
    if spam.pop("fresh", False):
        body["form_token"] = token(settings, age=0)  # submitted instantly after the form loaded
    body.update(spam)
    r = anonymous(app).post("/api/v1/public/inquiries", json=body)
    assert r.status_code == 202 and r.json()["status"] == "received"
    assert db.scalar(select(func.count()).select_from(Lead)) == 0


def test_expired_form_is_rejected_visibly(app, db, catalogue, settings):
    r = anonymous(app).post("/api/v1/public/inquiries", json=inquiry(settings, form_token=token(settings, age=3 * 3600)))
    assert r.status_code == 422 and "expired" in r.json()["error"]["message"]


def test_inquiries_are_rate_limited_per_ip_and_per_contact(app, db, catalogue, settings, monkeypatch):
    monkeypatch.setattr(public_router, "MAX_INQUIRIES_PER_CONTACT", 2)
    c = anonymous(app)
    for _ in range(2):
        assert c.post("/api/v1/public/inquiries", json=inquiry(settings)).status_code == 202
    r = c.post("/api/v1/public/inquiries", json=inquiry(settings))
    assert r.status_code == 429 and r.json()["error"]["code"] == "inquiry_rate_limited"
    # A different contact still gets through until the per-IP limit (5 per window) is reached.
    statuses = [c.post("/api/v1/public/inquiries", json=inquiry(settings, email=f"p{i}@example.com", phone=None)).status_code for i in range(3)]
    assert statuses == [202, 202, 429]


def test_form_token_endpoint(app, settings):
    t = anonymous(app).get("/api/v1/public/inquiries/form-token").json()
    assert t["min_fill_seconds"] == 3 and re.fullmatch(r"\d+\.[0-9a-f]{32}", t["token"])


# ================================================================== concurrency (real commits, separate connections)
@pytest.fixture
def committed(engine, inventory_committed):
    """Rows committed for real; removed afterwards (append-only triggers bypassed only for this cleanup)."""
    marker = f"race-{uuid.uuid4().hex[:8]}@example.com"
    yield marker
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        ids = [r[0] for r in conn.execute(text("SELECT id FROM leads WHERE lower(email) = :e"), {"e": marker})]
        for lead_id in ids:
            conn.execute(text("DELETE FROM lead_activities WHERE lead_id = :i"), {"i": lead_id})
            conn.execute(text("DELETE FROM automation_events WHERE entity_id = :i"), {"i": str(lead_id)})
            conn.execute(text("DELETE FROM audit_logs WHERE entity_id = :i"), {"i": str(lead_id)})
            conn.execute(text("DELETE FROM leads WHERE id = :i"), {"i": lead_id})


@pytest.fixture
def inventory_committed(engine):
    """No committed inventory is needed for contact inquiries; kept explicit so the test owns all its rows."""
    return None


def test_concurrent_duplicate_inquiries_create_one_lead(engine, settings, committed):
    data = InquiryIn.model_validate({"kind": "contact", "full_name": "Race Visitor", "email": committed, "phone": None,
                                     "message": "Hello", "consent": True, "form_token": token(settings)})
    barrier, errors = threading.Barrier(4), []

    def submit():
        try:
            with Session(bind=engine) as s:
                barrier.wait(timeout=10)
                InquiryService(s).submit(data)
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(repr(exc))

    threads = [threading.Thread(target=submit) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert errors == []
    with Session(bind=engine) as s:
        leads = list(s.scalars(select(Lead).where(func.lower(Lead.email) == committed)))
        assert len(leads) == 1
        assert s.scalar(select(func.count()).select_from(LeadActivity).where(LeadActivity.lead_id == leads[0].id)) == 4
        assert leads[0].created_at > datetime.now(UTC) - timedelta(minutes=5)
