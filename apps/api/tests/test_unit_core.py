"""Unit tests that need no database."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from pydantic import SecretStr

from app.ai.status import resolve_ai_status
from app.common.listing import apply_sort, escape_like
from app.core.config import Settings
from app.core.errors import PermissionDenied, ValidationFailed
from app.core.logging import redact
from app.core.security import create_session_token, decode_session_token, hash_password, verify_password
from app.modules.identity.principal import Principal, ensure_permission
from app.modules.identity.service import initials


def make_settings(**overrides) -> Settings:
    base = {
        "database_url": "postgresql+psycopg://u:p@127.0.0.1:1/x_test",
        "secret_key": "s" * 48,
        "app_env": "test",
        "ai_enabled": "false",
        "ai_default_model": "claude-opus-5-5",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


# --- passwords & tokens -------------------------------------------------------------
def test_password_hash_roundtrip():
    h = hash_password("a-long-password-123")
    assert h.startswith("$argon2id$")
    assert verify_password("a-long-password-123", h)
    assert not verify_password("wrong", h)
    assert not verify_password("anything", None)
    assert not verify_password("anything", "not-a-hash")


def test_session_token_roundtrip_and_tampering():
    s = make_settings()
    uid = uuid.uuid4()
    token, claims = create_session_token(s, uid, 3)
    decoded = decode_session_token(s, token)
    assert decoded and decoded.user_id == uid and decoded.token_version == 3
    assert decode_session_token(s, token[:-2] + "xx") is None
    assert decode_session_token(make_settings(secret_key="t" * 48), token) is None


def test_expired_and_wrong_audience_tokens_rejected():
    s = make_settings()
    now = datetime.now(UTC)
    base = {"sub": str(uuid.uuid4()), "tv": 0, "sid": "x", "iat": now - timedelta(hours=2), "iss": s.jwt_issuer}
    expired = jwt.encode({**base, "exp": now - timedelta(minutes=1), "aud": s.jwt_audience}, "s" * 48, algorithm="HS256")
    wrong_aud = jwt.encode({**base, "exp": now + timedelta(hours=1), "aud": "other"}, "s" * 48, algorithm="HS256")
    assert decode_session_token(s, expired) is None
    assert decode_session_token(s, wrong_aud) is None


# --- settings guards ----------------------------------------------------------------
def test_production_rejects_placeholder_secret():
    with pytest.raises(ValueError):
        make_settings(app_env="production", secret_key="<generate>" + "x" * 40)


def test_secure_cookie_auto():
    assert make_settings(app_env="development").secure_cookies is False
    assert make_settings(app_env="staging", secret_key="k" * 48).secure_cookies is True


# --- AI startup resilience ---------------------------------------------------------------
@pytest.mark.parametrize(
    ("overrides", "env", "state", "fragment"),
    [
        ({}, {}, "disabled", "AI_ENABLED=false"),
        ({"ai_enabled": "maybe"}, {}, "misconfigured", "AI_ENABLED must be"),
        ({"ai_enabled": "true"}, {}, "misconfigured", "ANTHROPIC_API_KEY is not set"),
        ({"ai_enabled": "true", "anthropic_api_key": SecretStr("k"), "ai_default_model": ""}, {}, "misconfigured", "AI_DEFAULT_MODEL is not set"),
        ({"ai_enabled": "true", "anthropic_api_key": SecretStr("k"), "ai_default_model": "gpt-4"}, {}, "misconfigured", "not a valid Claude model ID"),
        ({"ai_enabled": "true", "anthropic_api_key": SecretStr("k")}, {"AI_EFFORT_BI_AGENT": "ultra"}, "misconfigured", "AI_EFFORT_BI_AGENT"),
        ({"ai_enabled": "true", "anthropic_api_key": SecretStr("k")}, {"AI_MODEL_PROPERTY_ASSISTANT": "bad model"}, "misconfigured", "AI_MODEL_PROPERTY_ASSISTANT"),
        ({"ai_enabled": "true", "anthropic_api_key": SecretStr("k")}, {"AI_MODEL_BI_AGENT": "claude-sonnet-5-5"}, "enabled", "valid"),
    ],
)
def test_ai_status_never_raises(overrides, env, state, fragment):
    status = resolve_ai_status(make_settings(**overrides), environ=env)
    assert status.state == state
    assert fragment in status.reason


def test_ai_status_never_leaks_key():
    status = resolve_ai_status(make_settings(ai_enabled="true", anthropic_api_key=SecretStr("sk-ant-secret"), ai_default_model="x"), environ={})
    assert "sk-ant-secret" not in status.reason


def test_app_starts_with_broken_ai_config():
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(make_settings(ai_enabled="yes-please", ai_default_model="???"))
    with TestClient(app) as c:  # lifespan runs; must not raise
        assert app.state.ai_status.state == "misconfigured"
        assert c.get("/api/v1/does-not-exist").status_code == 404


def test_no_hardcoded_model_ids_in_app_code():
    """Model IDs live only in configuration (.env / .env.example), never in application code."""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    offenders = [p for p in app_dir.rglob("*.py") if "claude-opus" in p.read_text(encoding="utf-8") or "claude-sonnet" in p.read_text(encoding="utf-8") or "claude-haiku" in p.read_text(encoding="utf-8")]
    assert offenders == []


# --- logging redaction -----------------------------------------------------------------
def test_redact_nested_sensitive_keys():
    data = {"email": "a@b.c", "password": "x", "nested": {"api_key": "y", "items": [{"token": "z", "ok": 1}]}}
    out = redact(data)
    assert out == {"email": "a@b.c", "password": "[REDACTED]", "nested": {"api_key": "[REDACTED]", "items": [{"token": "[REDACTED]", "ok": 1}]}}
    assert "REDACTED" in redact("key sk-ant-abcdef1234567890")


# --- permissions ------------------------------------------------------------------------
def test_principal_permissions():
    p = Principal(uuid.uuid4(), "a@b.c", "A", frozenset({"employee"}), frozenset({"audit.logs.read"}))
    ensure_permission(p, "audit.logs.read")
    with pytest.raises(PermissionDenied):
        ensure_permission(p, "identity.users.manage")
    admin = Principal(uuid.uuid4(), "a@b.c", "A", frozenset({"super_admin"}), frozenset())
    ensure_permission(admin, "anything.at.all")


# --- listing ------------------------------------------------------------------------------
def test_sort_whitelist():
    from sqlalchemy import column, select

    allowed = {"name": column("name")}
    assert "ORDER BY name DESC" in str(apply_sort(select(column("name")), "-name", allowed, "name"))
    with pytest.raises(ValidationFailed):
        apply_sort(select(column("name")), "password", allowed, "name")
    assert escape_like("50%_off\\") == "50\\%\\_off\\\\"


def test_initials():
    assert initials("Layla Haddad") == "LH"
    assert initials("  ") == "?"
