"""Phase 6A — AI gateway on PostgreSQL: usage tracking (metadata only), cost cap, availability states,
graceful degradation, endpoints, permissions and the append-only usage history."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
from pydantic import BaseModel, SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.ai.errors import AIError
from app.ai.gateway import AIGateway
from app.ai.models import AIUsage
from app.modules.audit.models import AuditLog
from tests.ai_fakes import FAKE_KEY, Script, error, factory, message
from tests.business_fixtures import Actor
from tests.test_unit_core import make_settings

pytestmark = pytest.mark.db
PROMPT = "Summarise the confidential note about buyer Rana Al-Fictional, phone +966 50 000 1234."


class Verdict(BaseModel):
    label: str
    confidence: float


@pytest.fixture
def sessions(connection):
    return lambda: Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)


def gateway(sessions, script: Script | None = None, *, enabled: bool = True, key: bool = True, **settings) -> AIGateway:
    s = make_settings(ai_enabled="true" if enabled else "false", anthropic_api_key=SecretStr(FAKE_KEY) if key else None, **settings)
    return AIGateway(s, session_factory=sessions, provider_factory=factory(script or Script(message()), retries=0), environ={})


def rows(db) -> list[AIUsage]:
    db.expire_all()
    return list(db.scalars(select(AIUsage).order_by(AIUsage.created_at)))


def ask(gw: AIGateway, actor=None):
    return gw.generate_text("system_check", messages=[{"role": "user", "content": PROMPT}], system="Be brief.", actor_user_id=actor)


def test_success_records_metadata_only(db, sessions, make_user):
    user = make_user("employee")
    gw = gateway(sessions)
    assert gw.availability().state == "unverified"  # valid config + key is NOT reported as operational
    result = ask(gw, user.id)
    assert result.text == "Hello from the fake model." and not result.truncated
    assert result.usage.input_tokens == 1200 and result.usage.estimated_cost_usd == Decimal("0.010820")
    (row,) = rows(db)
    assert (row.status, row.capability, row.provider, row.model, row.served_model) == ("succeeded", "system_check", "anthropic",
                                                                                         "claude-opus-5-5", "claude-opus-5-5")
    assert (row.actor_type, row.actor_user_id, row.input_tokens, row.output_tokens, row.cache_read_tokens) == ("user", user.id, 1200, 300, 100)
    assert row.provider_request_id == "req_ok_123" and row.request_id == result.usage.request_id and row.duration_ms >= 0
    stored = json.dumps({c.name: str(getattr(row, c.name)) for c in AIUsage.__table__.columns})
    assert "Rana" not in stored and "+966" not in stored and "Be brief" not in stored and FAKE_KEY not in stored  # no prompts, no secrets
    assert gw.availability().state == "operational"


def test_structured_output_and_truncation(db, sessions):
    gw = gateway(sessions, Script(message(json.dumps({"label": "warm", "confidence": 0.6}))))
    out = gw.generate_structured("lead_summary", Verdict, messages=[{"role": "user", "content": "Classify"}])
    assert out.data == Verdict(label="warm", confidence=0.6)
    gw2 = gateway(sessions, Script(message('{"label": "wa', stop="max_tokens")))
    with pytest.raises(AIError) as exc:
        gw2.generate_structured("lead_summary", Verdict, messages=[{"role": "user", "content": "Classify"}])
    assert exc.value.category in ("truncated", "invalid_response")
    assert rows(db)[-1].status == "failed"


def test_refusal_is_a_failure_not_an_answer(db, sessions):
    gw = gateway(sessions, Script(message("", stop="refusal")))
    with pytest.raises(AIError) as exc:
        ask(gw)
    assert exc.value.category == "refusal" and exc.value.code == "ai_refused"
    row = rows(db)[-1]
    assert (row.status, row.error_category, row.stop_reason, row.actor_type) == ("failed", "refusal", "refusal", "system")


def test_provider_failures_are_tracked_and_degrade_availability(db, sessions):
    script = Script(error(429, "rate_limit_error", headers={"retry-after": "0"}), message())
    gw = gateway(sessions, script)
    with pytest.raises(AIError) as exc:
        ask(gw)
    assert exc.value.category == "rate_limited"
    row = rows(db)[-1]
    assert (row.status, row.error_category, row.provider_status) == ("failed", "rate_limited", 429)
    a = gw.availability()
    assert a.state == "degraded" and a.last_error_category == "rate_limited" and a.usable
    ask(gw)  # the next call succeeds → operational again
    assert gw.availability().state == "operational"


def test_authentication_failure_is_tracked_without_secrets(db, sessions):
    gw = gateway(sessions, Script(error(401, "authentication_error", msg=f"bad key {FAKE_KEY}")))
    with pytest.raises(AIError) as exc:
        ask(gw)
    assert exc.value.category == "authentication"
    stored = json.dumps({c.name: str(getattr(rows(db)[-1], c.name)) for c in AIUsage.__table__.columns})
    assert FAKE_KEY not in stored and "bad key" not in stored


@pytest.mark.parametrize(("enabled", "key", "category"), [(False, True, "disabled"), (True, False, "misconfigured")])
def test_disabled_or_unconfigured_ai_rejects_without_calling_the_provider(db, sessions, enabled, key, category):
    script = Script(message())
    gw = gateway(sessions, script, enabled=enabled, key=key)
    with pytest.raises(AIError) as exc:
        ask(gw)
    assert exc.value.category == category and script.calls == 0
    assert (rows(db)[-1].status, rows(db)[-1].error_category) == ("rejected", category)
    assert gw.availability().state == category and not gw.availability().usable


def test_daily_cost_cap_blocks_before_spending(db, sessions):
    db.add(AIUsage(request_id=uuid.uuid4(), actor_type="system", capability="system_check", provider="anthropic", model="x",
                   status="succeeded", estimated_cost_usd=Decimal("1.000000"), duration_ms=1))
    db.commit()
    script = Script(message())
    gw = gateway(sessions, script, ai_daily_cost_cap_usd="1")
    with pytest.raises(AIError) as exc:
        ask(gw)
    assert exc.value.category == "budget_exceeded" and script.calls == 0
    assert rows(db)[-1].error_category == "budget_exceeded"
    assert gateway(sessions, Script(message()), ai_daily_cost_cap_usd="5").generate_text(
        "system_check", messages=[{"role": "user", "content": "ok"}]).text


def test_usage_write_failure_never_breaks_the_call(sessions):
    def broken():
        raise RuntimeError("database down")

    s = make_settings(ai_enabled="true", anthropic_api_key=SecretStr(FAKE_KEY), ai_daily_cost_cap_usd="5")
    gw = AIGateway(s, session_factory=broken, provider_factory=factory(Script(message())), environ={})
    with pytest.raises(AIError) as exc:  # the cost cap can't be verified → fail closed, no spend
        ask(gw)
    assert exc.value.category == "budget_exceeded"
    assert gw.availability().state == "unverified"  # availability never raises


def test_invalid_inputs_are_programming_errors(sessions):
    gw = gateway(sessions)
    for bad in ([], [{"role": "assistant", "content": "hi"}], [{"role": "user", "content": " "}],
                [{"role": "user", "content": "x", "tools": []}], [{"role": "system", "content": "x"}]):
        with pytest.raises(ValueError):
            gw.generate_text("system_check", messages=bad)
    with pytest.raises(ValueError):
        gw.generate_text("run_sql", messages=[{"role": "user", "content": "x"}])


def test_health_check_verifies_models_without_tokens(db, sessions, make_user):
    model = {"id": "claude-opus-5-5", "type": "model", "display_name": "Claude Opus 5.5", "created_at": "2026-01-01T00:00:00Z"}
    script = Script(model)
    gw = gateway(sessions, script)
    checks = gw.check_health(actor_user_id=make_user("super_admin").id)
    assert [(c.model, c.ok) for c in checks] == [("claude-opus-5-5", True)] and script.paths == ["/v1/models/claude-opus-5-5"]
    assert gw.availability().state == "operational"
    bad = gateway(sessions, Script(error(404, "not_found_error")))
    assert bad.check_health()[0].error_category == "model_not_found" and bad.availability().state == "degraded"


def test_startup_makes_no_provider_call_and_core_api_works(app, client, make_user):
    calls = []
    s = make_settings(ai_enabled="true", anthropic_api_key=SecretStr(FAKE_KEY))
    gw = AIGateway(s, provider_factory=lambda cfg, key: calls.append(1), environ={})  # type: ignore[arg-type,return-value]
    assert calls == [] and gw.config.enabled
    r = client.get("/api/v1/health")
    assert r.status_code == 200 and r.json()["ai"]["state"] == "disabled" and FAKE_KEY not in r.text


def test_endpoints_and_permissions(app, db, sessions, make_user):
    app.state.ai_gateway = gateway(sessions, Script({"id": "claude-opus-5-5", "type": "model", "display_name": "x",
                                                    "created_at": "2026-01-01T00:00:00Z"}))
    employee, admin = Actor(app, make_user("employee")), Actor(app, make_user("super_admin"))
    status = employee.get("/ai/status").json()
    assert status == {"state": "unverified", "reason": status["reason"], "usable": True}
    for path in ("/ai/gateway", "/ai/usage"):
        assert employee.get(path).status_code == 403
    assert employee.post("/ai/health-check").status_code == 403
    r = admin.post("/ai/health-check")
    assert r.status_code == 200 and r.json()["checks"][0]["ok"] and r.json()["status"]["state"] == "operational"
    assert db.scalar(select(AuditLog).where(AuditLog.action == "ai.health_checked")) is not None
    overview = admin.get("/ai/gateway").json()
    assert overview["state"] == "operational" and overview["today"]["succeeded"] == 1
    assert {p["capability"] for p in overview["profiles"]} >= {"system_check", "lead_summary"}
    usage = admin.get("/ai/usage", params={"status": "succeeded"}).json()
    assert usage["total"] == 1 and usage["items"][0]["capability"] == "system_check"
    for body in (overview, usage, status):
        assert FAKE_KEY not in json.dumps(body) and "api_key" not in json.dumps(body).lower()
    assert Actor(app, make_user("employee")).client.get("/api/v1/ai/status").status_code == 200
    from fastapi.testclient import TestClient

    assert TestClient(app, base_url="http://127.0.0.1").get("/api/v1/ai/status").status_code == 401


def test_usage_history_is_append_only(db, sessions):
    ask(gateway(sessions))
    row = rows(db)[-1]
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE ai_usage SET status = 'failed', error_category = 'x' WHERE id = :i"), {"i": row.id})
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM ai_usage WHERE id = :i"), {"i": row.id})
    db.rollback()
    assert db.scalar(select(func.count()).select_from(AIUsage)) >= 1


def test_marketing_studio_flag_blocks_only_marketing_generation(db, sessions):
    script = Script(message(), message())
    gw = gateway(sessions, script)  # AI_ENABLED=true, AI_MARKETING_STUDIO_ENABLED unset → off
    assert gw.config.enabled and not gw.config.capability_enabled("marketing_studio")
    with pytest.raises(AIError) as exc:
        gw.generate_text("marketing_studio", messages=[{"role": "user", "content": "Write a post"}])
    assert exc.value.category == "feature_disabled" and exc.value.code == "ai_feature_disabled" and script.calls == 0
    assert (rows(db)[-1].status, rows(db)[-1].error_category) == ("rejected", "feature_disabled")
    assert gw.generate_text("lead_summary", messages=[{"role": "user", "content": "Summarise"}]).text  # other AI still works
    assert gw.availability().state == "operational"
    on = gateway(sessions, Script(message()), ai_marketing_studio_enabled="true")
    assert on.generate_text("marketing_studio", messages=[{"role": "user", "content": "Write a post"}]).text
    for bad in ("maybe", ""):
        assert not gateway(sessions, ai_marketing_studio_enabled=bad).config.capability_enabled("marketing_studio")
