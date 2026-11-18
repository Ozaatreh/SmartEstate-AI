"""AI configuration — the single place for model selection, limits and prices.

- Model IDs come from the environment (``AI_DEFAULT_MODEL``, ``AI_MODEL_<CAPABILITY>``). The literals in this file
  are the price table and capability sets keyed by model ID; a test fails if a model ID appears anywhere else in
  ``app/``.
- Everything here is evaluated leniently: an invalid value disables AI with a reason, it never stops the app
  (see ``app/ai/status.py``).
- Resolution order per capability: ``AI_MODEL_<CAPABILITY>`` → ``AI_DEFAULT_MODEL``; effort:
  ``AI_EFFORT_<CAPABILITY>`` → the capability default below.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Literal

from dotenv import dotenv_values

from app.core.config import REPO_ROOT, Settings

log = logging.getLogger(__name__)
PROVIDER = "anthropic"
MODEL_ID_PATTERN = re.compile(r"^claude-[a-z0-9][a-z0-9.\-]{1,62}$")
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
Effort = Literal["low", "medium", "high", "xhigh", "max"]

# Capabilities = the named AI features that may call the gateway. Each gets its own model/effort profile.
# Phase 6A registers them; the features themselves arrive in Phase 6B+. ``system_check`` is the gateway's own
# smoke test / health capability.
DEFAULT_EFFORT: dict[str, Effort] = {
    "bi_agent": "high",
    "property_assistant": "medium",
    "marketing_studio": "high",
    "lead_summary": "medium",
    "daily_digest": "medium",
    "system_check": "low",
}
CAPABILITIES = tuple(DEFAULT_EFFORT)
# Capabilities that also need their own feature flag (AI_<CAPABILITY>_ENABLED=true), off by default.
FEATURE_FLAGGED = frozenset({"marketing_studio"})
FEATURES = CAPABILITIES[:-1]  # the business features (kept for app.ai.status compatibility)

# USD per million tokens: input, output, cache read, cache write (5-minute TTL = 1.25 × input).
# Source: Anthropic pricing as of 2026-11 (estimates for the cost cap; the invoice is authoritative).
PRICING_USD_PER_MTOK: dict[str, tuple[Decimal, Decimal, Decimal, Decimal]] = {
    "claude-opus-5-5": (Decimal("4"), Decimal("20"), Decimal("0.20"), Decimal("5")),
    "claude-opus-5": (Decimal("5"), Decimal("25"), Decimal("0.50"), Decimal("6.25")),
    "claude-sonnet-5-5": (Decimal("2"), Decimal("10"), Decimal("0.10"), Decimal("2.50")),
    "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50"), Decimal("0.01"), Decimal("0.125")),
    "claude-fable-5-2": (Decimal("8"), Decimal("40"), Decimal("0.20"), Decimal("10")),
}
# Models that accept the server-side refusal fallback (``fallbacks: "default"`` with the beta header).
SERVER_FALLBACK_MODELS = frozenset({"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-2", "claude-fable-5-1"})
SERVER_FALLBACK_BETA = "server-side-fallback-2026-07-01"

TRUE, FALSE = {"1", "true", "yes", "on"}, {"0", "false", "no", "off", ""}


@dataclass(frozen=True)
class ModelProfile:
    capability: str
    model: str
    effort: Effort
    max_tokens: int

    @property
    def server_fallback(self) -> bool:
        return self.model in SERVER_FALLBACK_MODELS


@dataclass(frozen=True)
class AIConfig:
    state: Literal["enabled", "disabled", "misconfigured"]
    reason: str
    default_model: str | None = None
    problems: tuple[str, ...] = ()
    profiles: dict[str, ModelProfile] = field(default_factory=dict)
    timeout_seconds: float = 60.0
    max_retries: int = 2
    max_output_tokens: int = 16000
    daily_cost_cap_usd: Decimal = Decimal("10")
    # Capabilities switched off by their own feature flag while AI as a whole stays on.
    disabled_capabilities: frozenset[str] = frozenset()

    @property
    def enabled(self) -> bool:
        return self.state == "enabled"

    def capability_enabled(self, capability: str) -> bool:
        return self.enabled and capability not in self.disabled_capabilities

    def profile(self, capability: str) -> ModelProfile:
        if capability not in CAPABILITIES:
            raise ValueError(f"Unknown AI capability {capability!r}")
        return self.profiles[capability]

    @property
    def models(self) -> list[str]:
        return sorted({p.model for p in self.profiles.values()})


def estimate_cost(model: str, input_tokens: int, output_tokens: int, cache_read: int, cache_write: int) -> Decimal | None:
    prices = PRICING_USD_PER_MTOK.get(model)
    if prices is None:
        return None
    pin, pout, pread, pwrite = prices
    total = Decimal(input_tokens) * pin + Decimal(output_tokens) * pout + Decimal(cache_read) * pread + Decimal(cache_write) * pwrite
    return (total / Decimal(1_000_000)).quantize(Decimal("0.000001"))


def _parse_bool(raw: str) -> bool | None:
    value = (raw or "").strip().lower()
    return True if value in TRUE else False if value in FALSE else None


def _environ() -> dict[str, str]:
    file_values = {k: v or "" for k, v in dotenv_values(REPO_ROOT / ".env").items()}
    return {k.upper(): v for k, v in {**file_values, **os.environ}.items()}


def _number(raw: str, name: str, lo: float, hi: float, problems: list[str], *, integer: bool = False) -> float:
    try:
        value = Decimal((raw or "").strip())
        if integer and value != value.to_integral_value():
            raise InvalidOperation
        if not (Decimal(str(lo)) <= value <= Decimal(str(hi))):
            raise InvalidOperation
        return float(value)
    except (InvalidOperation, ValueError):
        problems.append(f"{name} must be a number between {lo:g} and {hi:g}.")
        return lo


def resolve_ai_config(settings: Settings, environ: dict[str, str] | None = None) -> AIConfig:
    """Never raises; any problem becomes ``misconfigured`` with a reason that never contains the key."""
    env = {k.upper(): v for k, v in (environ if environ is not None else _environ()).items()}
    enabled = _parse_bool(settings.ai_enabled)
    model = (settings.ai_default_model or "").strip()
    if enabled is None:
        return AIConfig("misconfigured", f"AI_ENABLED must be true or false (got {settings.ai_enabled!r}).")
    if not enabled:
        return AIConfig("disabled", "AI features are turned off (AI_ENABLED=false).", model or None)

    problems: list[str] = []
    key = settings.anthropic_api_key.get_secret_value().strip() if settings.anthropic_api_key else ""
    if not key:
        problems.append("ANTHROPIC_API_KEY is not set.")
    if not model:
        problems.append("AI_DEFAULT_MODEL is not set.")
    elif not MODEL_ID_PATTERN.match(model):
        problems.append(f"AI_DEFAULT_MODEL {model!r} is not a valid Claude model ID.")
    timeout = _number(settings.ai_request_timeout_seconds, "AI_REQUEST_TIMEOUT_SECONDS", 5, 600, problems)
    retries = int(_number(settings.ai_max_retries, "AI_MAX_RETRIES", 0, 5, problems, integer=True))
    max_tokens = int(_number(settings.ai_max_output_tokens, "AI_MAX_OUTPUT_TOKENS", 256, 64000, problems, integer=True))
    cap = Decimal(str(_number(settings.ai_daily_cost_cap_usd, "AI_DAILY_COST_CAP_USD", 0, 100000, problems)))

    profiles: dict[str, ModelProfile] = {}
    for capability, default_effort in DEFAULT_EFFORT.items():
        override = env.get(f"AI_MODEL_{capability.upper()}", "").strip()
        if override and not MODEL_ID_PATTERN.match(override):
            problems.append(f"AI_MODEL_{capability.upper()} {override!r} is not a valid Claude model ID.")
        effort = env.get(f"AI_EFFORT_{capability.upper()}", "").strip().lower() or default_effort
        if effort not in EFFORT_LEVELS:
            problems.append(f"AI_EFFORT_{capability.upper()} must be one of {', '.join(EFFORT_LEVELS)}.")
            effort = default_effort
        profiles[capability] = ModelProfile(capability, override or model, effort, max_tokens)  # type: ignore[arg-type]

    if problems:
        return AIConfig("misconfigured", "AI features are disabled: " + " ".join(problems), model or None, tuple(problems))
    marketing = _parse_bool(getattr(settings, "ai_marketing_studio_enabled", "false"))
    if marketing is None:
        log.warning("AI_MARKETING_STUDIO_ENABLED must be true or false; marketing generation stays off.")
    disabled = frozenset() if marketing else FEATURE_FLAGGED  # anything but an explicit true keeps it off
    return AIConfig("enabled", "AI configuration is valid.", model, (), profiles, timeout, retries, max_tokens, cap, disabled)
