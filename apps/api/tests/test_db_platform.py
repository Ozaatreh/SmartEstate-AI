"""Integration tests: auth, permissions, audit, notifications, health (PostgreSQL test DB)."""

from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.modules.audit.models import AuditLog
from app.modules.notifications.models import Notification
from app.modules.notifications.service import NotificationService
from tests.conftest import CSRF, login

pytestmark = pytest.mark.db


# --- authentication ---------------------------------------------------------------------------
def test_login_sets_httponly_cookie_and_me_works(client, make_user):
    user = make_user("executive", name="Faisal Test")
    r = login(client, user)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == user.email and body["initials"] == "FT"
    assert "audit.logs.read" in body["permissions"]
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/api" in cookie
    assert "token" not in body and "password_hash" not in body
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["id"] == str(user.id)


def test_wrong_password_and_unknown_email_get_same_error(client, make_user):
    user = make_user()
    a = login(client, user, "wrong-password")
    b = client.post("/api/v1/auth/login", json={"email": "nobody@smartestate.demo", "password": "x"}, headers=CSRF)
    assert a.status_code == b.status_code == 401
    assert a.json()["error"]["code"] == b.json()["error"]["code"] == "invalid_credentials"
    assert a.json()["error"]["message"] == b.json()["error"]["message"]


def test_account_locks_after_repeated_failures(client, make_user, settings):
    user = make_user()
    for _ in range(settings.login_max_failures):
        assert login(client, user, "nope").status_code == 401
    r = login(client, user)  # correct password, but locked
    assert r.status_code == 429 and r.json()["error"]["code"] == "account_locked"


def test_inactive_user_cannot_sign_in(client, make_user):
    user = make_user(active=False)
    assert login(client, user).json()["error"]["code"] == "invalid_credentials"


def test_requests_without_session_are_401(client):
    for path in ("/api/v1/auth/me", "/api/v1/notifications", "/api/v1/audit-logs"):
        r = client.get(path)
        assert r.status_code == 401 and r.json()["error"]["code"] == "not_authenticated"


def test_logout_revokes_existing_tokens(client, make_user, settings):
    user = make_user()
    login(client, user)
    old_cookie = client.cookies.get(settings.cookie_name)
    assert client.post("/api/v1/auth/logout", headers=CSRF).status_code == 204
    client.cookies.set(settings.cookie_name, old_cookie, path="/api")
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "session_expired"


def test_deactivated_user_session_stops_working(client, make_user, db):
    user = make_user()
    login(client, user)
    user.is_active = False
    db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_mutations_require_csrf_header(client, make_user):
    user = make_user()
    r = client.post("/api/v1/auth/login", json={"email": user.email, "password": "x"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_header_missing"


def test_validation_error_shape(client):
    r = client.post("/api/v1/auth/login", json={"email": "not-an-email", "password": "", "extra": 1}, headers=CSRF)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_failed" and err["request_id"]
    fields = {f["field"] for f in err["details"]["fields"]}
    assert {"email", "password", "extra"} <= fields


def test_request_id_header_echoed(client):
    r = client.get("/api/v1/health", headers={"X-Request-ID": "demo-request-0001"})
    assert r.headers["x-request-id"] == "demo-request-0001"


# --- audit ---------------------------------------------------------------------------------------
def test_login_events_are_audited(client, make_user, db):
    user = make_user()
    login(client, user, "bad")
    login(client, user)
    actions = list(db.scalars(select(AuditLog.action).where(AuditLog.actor_user_id == user.id).order_by(AuditLog.seq)))
    assert actions == ["auth.login_failed", "auth.login_succeeded"]


def test_audit_list_requires_permission(client, make_user):
    login(client, make_user("employee"))
    r = client.get("/api/v1/audit-logs")
    assert r.status_code == 403 and r.json()["error"]["details"]["required_permission"] == "audit.logs.read"


def test_audit_list_search_filter_sort_paginate(client, make_user):
    admin = make_user("super_admin", name="Audit Admin")
    for _ in range(3):
        login(client, make_user("employee"), "bad")
    login(client, admin)
    r = client.get("/api/v1/audit-logs", params={"action": "auth.login_failed", "page_size": 2, "sort": "-created_at"})
    assert r.status_code == 200
    page = r.json()
    assert page["total"] == 3 and len(page["items"]) == 2 and page["pages"] == 2
    assert all(i["action"] == "auth.login_failed" for i in page["items"])
    found = client.get("/api/v1/audit-logs", params={"q": "Audit Admin"}).json()
    assert found["total"] >= 1 and found["items"][0]["actor"]["full_name"] == "Audit Admin"
    bad = client.get("/api/v1/audit-logs", params={"sort": "ip_address"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_sort"


def test_audit_log_is_append_only(db, make_user):
    make_user()
    db.add(AuditLog(action="test.event", actor_user_id=None))
    db.commit()
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("UPDATE audit_logs SET action = 'tampered'"))
        db.flush()
    db.rollback()


# --- notifications --------------------------------------------------------------------------------
def test_notifications_are_private_and_deduplicated(client, make_user, db):
    me, other = make_user(), make_user()
    svc = NotificationService(db)
    svc.notify(me.id, type="t", title="Mine", dedupe_key="k1")
    svc.notify(me.id, type="t", title="Mine again", dedupe_key="k1")  # deduplicated
    svc.notify(me.id, type="t", title="Second")
    svc.notify(other.id, type="t", title="Theirs")
    db.commit()
    login(client, me)
    page = client.get("/api/v1/notifications").json()
    assert {n["title"] for n in page["items"]} == {"Mine", "Second"}
    assert client.get("/api/v1/notifications/unread-count").json() == {"unread": 2}

    theirs = db.scalar(select(Notification).where(Notification.user_id == other.id))
    assert client.post(f"/api/v1/notifications/{theirs.id}/read", headers=CSRF).status_code == 404

    first = page["items"][0]["id"]
    assert client.post(f"/api/v1/notifications/{first}/read", headers=CSRF).json()["read_at"]
    assert client.get("/api/v1/notifications", params={"unread_only": True}).json()["total"] == 1
    assert client.post("/api/v1/notifications/read-all", headers=CSRF).json() == {"marked": 1}
    assert client.get("/api/v1/notifications/unread-count").json() == {"unread": 0}


# --- health ---------------------------------------------------------------------------------------
def test_health_reports_database_and_ai(client):
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok" and body["database"] == "ok"
    assert body["ai"]["state"] in {"enabled", "disabled", "misconfigured"}


# --- seed -----------------------------------------------------------------------------------------
def test_seed_sync_is_idempotent(db, roles):
    from app.seed.__main__ import sync_permissions, sync_roles

    perms = sync_permissions(db)
    again = sync_roles(db, perms)
    assert set(again) == set(roles)
    assert "audit.logs.read" in {p.code for p in again["executive"].permissions}
