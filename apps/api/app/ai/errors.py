"""AI error categories. Messages are fixed, user-safe strings: provider error bodies, prompts and credentials are
never copied into them (the provider's raw message can echo request details)."""

from __future__ import annotations

from app.core.errors import ExternalServiceUnavailable

# category → (API error code, safe message, transient?)
CATEGORIES: dict[str, tuple[str, str, bool]] = {
    "disabled": ("ai_disabled", "AI features are turned off.", False),
    "feature_disabled": ("ai_feature_disabled", "This AI feature is turned off.", False),
    "misconfigured": ("ai_misconfigured", "AI features are not configured correctly.", False),
    "budget_exceeded": ("ai_budget_exceeded", "The daily AI budget has been reached. Try again tomorrow.", False),
    "authentication": ("ai_unavailable", "The AI provider rejected the configured credentials.", False),
    "permission": ("ai_unavailable", "The AI provider refused this request for the configured account.", False),
    "rate_limited": ("ai_rate_limited", "The AI provider is busy. Try again shortly.", True),
    "timeout": ("ai_timeout", "The AI provider did not answer in time.", True),
    "connection": ("ai_unavailable", "The AI provider could not be reached.", True),
    "overloaded": ("ai_unavailable", "The AI provider is overloaded. Try again shortly.", True),
    "provider_error": ("ai_unavailable", "The AI provider returned an error.", True),
    "bad_request": ("ai_bad_request", "The AI request was rejected as invalid.", False),
    "model_not_found": ("ai_misconfigured", "The configured AI model is not available.", False),
    "invalid_response": ("ai_invalid_response", "The AI provider returned an unexpected response.", False),
    "refusal": ("ai_refused", "The AI model declined this request.", False),
    "truncated": ("ai_truncated", "The AI response was cut off before it was complete.", False),
}


class AIError(ExternalServiceUnavailable):
    """Raised by the gateway. HTTP 503 with a category-specific code; never contains secrets or prompt text."""

    def __init__(self, category: str, *, status_code: int | None = None):
        code, message, transient = CATEGORIES[category]
        super().__init__(message, code=code, details={"category": category})
        self.category = category
        self.transient = transient
        self.provider_status = status_code
