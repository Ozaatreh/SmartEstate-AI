"""Phase 6A — AI gateway units: configuration, provider over the real SDK (mocked HTTP), error translation,
retries, structured output, usage extraction, secret redaction and the "only the gateway talks to Anthropic"
architecture guard. No network, no database."""

from __future__ import annotations

import ast
import json
import logging
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import BaseModel, SecretStr

from app.ai.config import CAPABILITIES, estimate_cost, resolve_ai_config
from app.ai.errors import AIError
from app.core.logging import redact
from tests.ai_fakes import FAKE_KEY, Script, connect_error, error, message, provider, timeout_error
from tests.test_unit_core import make_settings

APP = Path(__file__).resolve().parents[1] / "app"
FRONTENDS = [Path(__file__).resolve().parents[3] / "apps" / app / "src" for app in ("dashboard", "marketing")]


def enabled(**kw):
    return make_settings(ai_enabled="true", anthropic_api_key=SecretStr(FAKE_KEY), **kw)


def profile(capability="system_check", **env):
    return resolve_ai_config(enabled(), environ=env).profile(capability)


class Verdict(BaseModel):
    label: str
    confidence: float


# ============================================================================ configuration
def test_config_profiles_defaults_and_overrides():
    cfg = resolve_ai_config(enabled(), environ={"AI_MODEL_BI_AGENT": "claude-sonnet-5-5", "AI_EFFORT_LEAD_SUMMARY": "low"})
    assert cfg.enabled and set(cfg.profiles) == set(CAPABILITIES)
    assert cfg.profile("property_assistant").model == "claude-opus-5-5" and cfg.profile("property_assistant").effort == "medium"
    assert cfg.profile("bi_agent").model == "claude-sonnet-5-5" and cfg.profile("bi_agent").effort == "high"
    assert cfg.profile("lead_summary").effort == "low"
    assert (cfg.timeout_seconds, cfg.max_retries, cfg.max_output_tokens, cfg.daily_cost_cap_usd) == (60.0, 2, 16000, Decimal("10"))
    assert cfg.profile("system_check").server_fallback is True
    with pytest.raises(ValueError):
        cfg.profile("sql_runner")


@pytest.mark.parametrize(
    ("overrides", "env", "state", "fragment"),
    [
        ({"ai_enabled": "false"}, {}, "disabled", "AI_ENABLED=false"),
        ({"ai_enabled": "true"}, {}, "misconfigured", "ANTHROPIC_API_KEY is not set"),
        ({"ai_enabled": "maybe"}, {}, "misconfigured", "AI_ENABLED must be"),
        ({"ai_request_timeout_seconds": "0"}, {}, "misconfigured", "AI_REQUEST_TIMEOUT_SECONDS"),
        ({"ai_max_retries": "9"}, {}, "misconfigured", "AI_MAX_RETRIES"),
        ({"ai_max_retries": "1.5"}, {}, "misconfigured", "AI_MAX_RETRIES"),
        ({"ai_max_output_tokens": "lots"}, {}, "misconfigured", "AI_MAX_OUTPUT_TOKENS"),
        ({"ai_daily_cost_cap_usd": "-1"}, {}, "misconfigured", "AI_DAILY_COST_CAP_USD"),
        ({}, {"AI_EFFORT_SYSTEM_CHECK": "turbo"}, "misconfigured", "AI_EFFORT_SYSTEM_CHECK"),
        ({}, {"AI_MODEL_LEAD_SUMMARY": "gpt-4"}, "misconfigured", "AI_MODEL_LEAD_SUMMARY"),
    ],
)
def test_config_problems_disable_ai_without_raising(overrides, env, state, fragment):
    base = {"ai_enabled": "true", "anthropic_api_key": SecretStr(FAKE_KEY)}
    if overrides.get("ai_enabled") == "true" and "anthropic_api_key" not in overrides and fragment.startswith("ANTHROPIC"):
        base.pop("anthropic_api_key")
    cfg = resolve_ai_config(make_settings(**{**base, **overrides}), environ=env)
    assert cfg.state == state and fragment in cfg.reason
    assert FAKE_KEY not in cfg.reason


def test_cost_estimate_uses_served_model_prices():
    assert estimate_cost("claude-opus-5-5", 1_000_000, 100_000, 0, 0) == Decimal("6.000000")  # 4 + 2
    assert estimate_cost("claude-opus-5-5", 1200, 300, 100, 0) == Decimal("0.010820")
    assert estimate_cost("claude-unknown-9", 10, 10, 0, 0) is None


# ============================================================================ provider over the real SDK
def test_success_builds_the_documented_request_and_extracts_usage():
    script = Script(message("Fine.", usage={"input_tokens": 11, "output_tokens": 4, "cache_read_input_tokens": 5,
                                            "cache_creation_input_tokens": 2}))
    out = provider(script).create(profile(), system="Be brief.", messages=[{"role": "user", "content": "Ping"}], max_tokens=512)
    sent = script.requests[0]
    assert sent["model"] == "claude-opus-5-5" and sent["max_tokens"] == 512 and sent["system"] == "Be brief."
    assert sent["thinking"] == {"type": "adaptive"} and sent["output_config"] == {"effort": "low"}
    assert sent["fallbacks"] == "default"  # server-side refusal fallback on current models
    assert "tools" not in sent and "tool_choice" not in sent  # the model can never call back into the app
    assert (out.text, out.stop_reason, out.model) == ("Fine.", "end_turn", "claude-opus-5-5")
    assert (out.input_tokens, out.output_tokens, out.cache_read_tokens, out.cache_write_tokens) == (11, 4, 5, 2)
    assert out.provider_request_id == "req_ok_123"


def test_structured_output_is_schema_constrained_and_validated():
    script = Script(message(json.dumps({"label": "hot", "confidence": 0.9})))
    out = provider(script).create(profile(), system=None, messages=[{"role": "user", "content": "Classify"}], max_tokens=256,
                                  output_schema=Verdict)
    fmt = script.requests[0]["output_config"]["format"]
    assert fmt["type"] == "json_schema" and fmt["schema"]["additionalProperties"] is False
    assert isinstance(out.parsed, Verdict) and out.parsed.label == "hot"


@pytest.mark.parametrize("body", ["not json at all", json.dumps({"label": "hot"}), json.dumps({"label": 1, "confidence": "x"})])
def test_invalid_structured_output_is_rejected(body):
    with pytest.raises(AIError) as exc:
        provider(Script(message(body))).create(profile(), system=None, messages=[{"role": "user", "content": "x"}], max_tokens=64,
                                               output_schema=Verdict)
    assert exc.value.category == "invalid_response"


@pytest.mark.parametrize(
    ("step", "category", "attempts_with_2_retries"),
    [
        (error(401, "authentication_error"), "authentication", 1),  # never retried
        (error(403, "permission_error"), "permission", 1),
        (error(400, "invalid_request_error"), "bad_request", 1),
        (error(404, "not_found_error"), "model_not_found", 1),
        (error(429, "rate_limit_error", headers={"retry-after": "0"}), "rate_limited", 3),  # bounded retries
        (error(500), "provider_error", 3),
        (error(529, "overloaded_error"), "overloaded", 3),
        (timeout_error, "timeout", 3),
        (connect_error, "connection", 3),
    ],
)
def test_provider_errors_are_categorised_and_only_transient_ones_retried(step, category, attempts_with_2_retries, monkeypatch):
    monkeypatch.setattr("anthropic._base_client.BaseClient._calculate_retry_timeout", lambda *a, **k: 0, raising=False)
    script = Script(step)
    with pytest.raises(AIError) as exc:
        provider(script, retries=2).create(profile(), system=None, messages=[{"role": "user", "content": "x"}], max_tokens=64)
    assert exc.value.category == category
    assert script.calls == attempts_with_2_retries
    assert exc.value.status_code == 503 and FAKE_KEY not in str(exc.value) and "boom" not in str(exc.value)


def test_transient_failure_then_success_recovers_within_retry_budget(monkeypatch):
    monkeypatch.setattr("anthropic._base_client.BaseClient._calculate_retry_timeout", lambda *a, **k: 0, raising=False)
    script = Script(error(529, "overloaded_error"), message("Recovered."))
    out = provider(script, retries=2).create(profile(), system=None, messages=[{"role": "user", "content": "x"}], max_tokens=64)
    assert out.text == "Recovered." and script.calls == 2


@pytest.mark.parametrize(
    "response",
    [
        lambda r: __import__("httpx2").Response(200, content=b"<html>proxy error</html>"),
        lambda r: __import__("httpx2").Response(200, json={"unexpected": True}),
        lambda r: __import__("httpx2").Response(200, json={**message(), "content": None}),
    ],
)
def test_malformed_provider_responses_are_rejected(response):
    with pytest.raises(AIError) as exc:
        provider(Script(response)).create(profile(), system=None, messages=[{"role": "user", "content": "x"}], max_tokens=64)
    assert exc.value.category == "invalid_response"


def test_models_lookup_for_health_check():
    script = Script({"id": "claude-opus-5-5", "type": "model", "display_name": "Claude Opus 5.5", "created_at": "2026-01-01T00:00:00Z"})
    assert provider(script).retrieve_model("claude-opus-5-5") == "claude-opus-5-5"
    assert script.paths == ["/v1/models/claude-opus-5-5"]


def test_explicit_key_is_sent_and_ambient_credentials_ignored(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-ambient-should-not-be-used")
    seen = {}

    def capture(request):
        seen["key"] = request.headers.get("authorization", "").removeprefix("Bearer ")  # SDK 2.x sends the key as a bearer token
        return __import__("httpx2").Response(200, json=message())

    provider(Script(capture)).create(profile(), system=None, messages=[{"role": "user", "content": "x"}], max_tokens=64)
    assert seen["key"] == FAKE_KEY


# ============================================================================ secrets
def test_secrets_never_leak_through_errors_logs_or_config(caplog):
    leaky = error(401, "authentication_error", msg=f"invalid x-api-key {FAKE_KEY}")
    with pytest.raises(AIError) as exc:
        provider(Script(leaky)).create(profile(), system=None, messages=[{"role": "user", "content": "x"}], max_tokens=64)
    assert FAKE_KEY not in str(exc.value) and FAKE_KEY not in json.dumps(exc.value.details)
    assert exc.value.__cause__ is None and exc.value.__suppress_context__  # the SDK exception (with its body) is dropped
    with caplog.at_level(logging.INFO):
        logging.getLogger("t").info("key is %s", FAKE_KEY)
    assert "SECRET" not in str(redact(caplog.records[-1].getMessage())) and "REDACTED" in str(redact(f"x {FAKE_KEY}"))
    cfg = resolve_ai_config(enabled())
    assert FAKE_KEY not in repr(cfg)


# ============================================================================ architecture guard
def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0] if node.level == 0 else node.module)
    return names


def test_only_the_provider_imports_the_anthropic_sdk():
    offenders = [str(p.relative_to(APP)) for p in APP.rglob("*.py") if "anthropic" in _imports(p) and p != APP / "ai" / "provider.py"]
    assert offenders == []
    dynamic = [str(p.relative_to(APP)) for p in APP.rglob("*.py")
               if p != APP / "ai" / "provider.py" and ("import_module(\"anthropic" in p.read_text(encoding="utf-8")
                                                       or "__import__(\"anthropic" in p.read_text(encoding="utf-8"))]
    assert dynamic == []


def test_provider_has_no_database_or_business_access():
    full = {a for a in ast.walk(ast.parse((APP / "ai" / "provider.py").read_text(encoding="utf-8")))
            if isinstance(a, ast.ImportFrom) for a in [a]}
    modules = {n.module for n in full if n.module}
    assert not any(m.startswith(("sqlalchemy", "app.db", "app.modules")) for m in modules)


def test_model_ids_only_in_ai_config():
    offenders = [str(p.relative_to(APP)) for p in APP.rglob("*.py")
                 if p != APP / "ai" / "config.py" and any(m in p.read_text(encoding="utf-8")
                                                         for m in ("claude-opus", "claude-sonnet", "claude-haiku", "claude-fable", "claude-mythos"))]
    assert offenders == []


def test_frontend_never_talks_to_anthropic():
    assert all(src.is_dir() for src in FRONTENDS), "both frontends (dashboard, marketing) must exist"
    hits = [str(p) for src in FRONTENDS for p in src.rglob("*") if p.is_file() and p.suffix in (".ts", ".tsx", ".js")
            and any(s in p.read_text(encoding="utf-8") for s in ("api.anthropic.com", "@anthropic-ai", "x-api-key", "ANTHROPIC_API_KEY", "claude-"))]
    assert hits == []
