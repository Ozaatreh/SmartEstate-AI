"""AI startup resilience.

Rule: **no AI setting can stop the application from starting.** AI configuration is evaluated
here, once at startup, into an ``AIStatus``. A missing key, a malformed flag or a bad model ID
only disables the AI features (with a logged reason). Every other feature keeps working.

Phase 1 validates configuration only. The AI gateway (Phase 6) adds the live check of each
configured model through the Models API, and it degrades to ``misconfigured`` the same way.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Literal

from dotenv import dotenv_values

from app.core.config import REPO_ROOT, Settings

log = logging.getLogger(__name__)

MODEL_ID_PATTERN = re.compile(r"^claude-[a-z0-9][a-z0-9.\-]{1,62}$")
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
# AI agents (features) that may override the default model / effort via env.
FEATURES = ("bi_agent", "property_assistant", "marketing_studio", "lead_summary", "daily_digest")
TRUE, FALSE = {"1", "true", "yes", "on"}, {"0", "false", "no", "off", ""}


@dataclass(frozen=True)
class AIStatus:
    state: Literal["enabled", "disabled", "misconfigured"]
    reason: str
    default_model: str | None = None
    problems: tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        return self.state == "enabled"


def _parse_bool(raw: str) -> bool | None:
    value = (raw or "").strip().lower()
    return True if value in TRUE else False if value in FALSE else None


def resolve_ai_status(settings: Settings, environ: dict[str, str] | None = None) -> AIStatus:
    try:
        if environ is None:  # per-agent overrides may live in .env or the process environment
            file_values = {k: v or "" for k, v in dotenv_values(REPO_ROOT / ".env").items()}
            environ = {**file_values, **os.environ}
        env = {k.upper(): v for k, v in environ.items()}
        enabled = _parse_bool(settings.ai_enabled)
        model = (settings.ai_default_model or "").strip()

        if enabled is None:
            return AIStatus("misconfigured", f"AI_ENABLED must be true or false (got {settings.ai_enabled!r}).")
        if not enabled:
            return AIStatus("disabled", "AI features are turned off (AI_ENABLED=false).", model or None)

        problems: list[str] = []
        key = settings.anthropic_api_key.get_secret_value().strip() if settings.anthropic_api_key else ""
        if not key:
            problems.append("ANTHROPIC_API_KEY is not set.")
        if not model:
            problems.append("AI_DEFAULT_MODEL is not set.")
        elif not MODEL_ID_PATTERN.match(model):
            problems.append(f"AI_DEFAULT_MODEL {model!r} is not a valid Claude model ID.")
        for feature in FEATURES:
            override = env.get(f"AI_MODEL_{feature.upper()}", "").strip()
            if override and not MODEL_ID_PATTERN.match(override):
                problems.append(f"AI_MODEL_{feature.upper()} {override!r} is not a valid Claude model ID.")
            effort = env.get(f"AI_EFFORT_{feature.upper()}", "").strip().lower()
            if effort and effort not in EFFORT_LEVELS:
                problems.append(f"AI_EFFORT_{feature.upper()} must be one of {', '.join(EFFORT_LEVELS)}.")

        if problems:
            return AIStatus("misconfigured", "AI features are disabled: " + " ".join(problems), model or None, tuple(problems))
        return AIStatus("enabled", "AI configuration is valid.", model)
    except Exception as exc:  # resilience: never propagate
        log.exception("AI configuration could not be evaluated")
        return AIStatus("misconfigured", f"AI configuration could not be evaluated ({type(exc).__name__}).")


def log_ai_status(status: AIStatus) -> None:
    level = logging.INFO if status.state != "misconfigured" else logging.WARNING
    log.log(level, "AI status: %s — %s", status.state, status.reason, extra={"ai_state": status.state})
