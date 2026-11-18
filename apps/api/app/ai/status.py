"""AI startup resilience.

Rule: **no AI setting can stop the application from starting.** AI configuration is evaluated once at startup
into an ``AIStatus`` (configuration only, no network call). A missing key, a malformed flag or a bad model ID
only disables the AI features (with a logged reason). Every other feature keeps working.

Whether the provider actually answers is a separate, runtime question answered by the gateway
(``AIGateway.availability``): a valid configuration starts as ``unverified``, never as ``operational``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from app.ai.config import EFFORT_LEVELS, FEATURES, MODEL_ID_PATTERN, resolve_ai_config  # noqa: F401  (re-exported)
from app.core.config import Settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AIStatus:
    state: Literal["enabled", "disabled", "misconfigured"]
    reason: str
    default_model: str | None = None
    problems: tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        return self.state == "enabled"


def resolve_ai_status(settings: Settings, environ: dict[str, str] | None = None) -> AIStatus:
    try:
        cfg = resolve_ai_config(settings, environ)
        return AIStatus(cfg.state, cfg.reason, cfg.default_model, cfg.problems)
    except Exception as exc:  # resilience: never propagate
        log.exception("AI configuration could not be evaluated")
        return AIStatus("misconfigured", f"AI configuration could not be evaluated ({type(exc).__name__}).")


def log_ai_status(status: AIStatus) -> None:
    level = logging.INFO if status.state != "misconfigured" else logging.WARNING
    log.log(level, "AI status: %s — %s", status.state, status.reason, extra={"ai_state": status.state})
