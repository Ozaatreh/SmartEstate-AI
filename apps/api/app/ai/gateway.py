"""AI Gateway — the single entry point for every AI capability in SmartEstate.

Responsibilities: capability → model profile, kill switch, daily cost cap, request validation, provider call
(through ``provider.py``, the only SDK importer), stop-reason handling, structured-output validation, usage
tracking and availability reporting.

Security principles (non-negotiable):
- The gateway takes plain text and returns text or a validated Pydantic object. It exposes no tools, no
  database session and no SQL to the model; the model cannot read or change business records.
- Authorization stays in deterministic service code *before* a capability calls the gateway. The model never
  decides who may see or do what. Outputs are advisory.
- Prompts and responses are not persisted; ``ai_usage`` keeps operational metadata only. Credentials never
  appear in usage rows, logs, errors or API responses.
- An AI failure raises ``AIError`` (HTTP 503) for that call only. Startup makes no network call, and nothing
  outside the AI features depends on the provider.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from app.ai.config import PROVIDER, AIConfig, ModelProfile, estimate_cost, resolve_ai_config
from app.ai.errors import AIError
from app.ai.models import AIUsage
from app.ai.provider import AnthropicProvider, ProviderResponse, ProviderTurn, ToolSpec
from app.ai.repository import AIUsageRepository
from app.core.config import Settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)
MAX_INPUT_CHARS = 400_000
ROLES = ("user", "assistant")
# Content block types a conversation may carry back to the provider (assistant blocks are replayed unchanged).
CONVERSATION_BLOCKS = frozenset({"text", "tool_use", "tool_result", "thinking", "redacted_thinking", "fallback"})
MAX_CONVERSATION_CHARS = 600_000
AvailabilityState = Literal["disabled", "misconfigured", "unverified", "operational", "degraded"]


@dataclass(frozen=True)
class AIUsageInfo:
    request_id: uuid.UUID
    model: str
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: Decimal | None
    duration_ms: int


@dataclass(frozen=True)
class AIResult:
    text: str
    stop_reason: str | None
    truncated: bool
    usage: AIUsageInfo


@dataclass(frozen=True)
class AIStructuredResult(Generic[T]):
    data: T
    usage: AIUsageInfo


@dataclass(frozen=True)
class AIAvailability:
    state: AvailabilityState
    reason: str
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_error_category: str | None = None

    @property
    def usable(self) -> bool:
        """Calls may be attempted (the provider may still fail them)."""
        return self.state in ("unverified", "operational", "degraded")


@dataclass(frozen=True)
class ModelCheck:
    model: str
    ok: bool
    error_category: str | None


def start_of_day(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


class AIGateway:
    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: Callable[[], Session] | sessionmaker | None = None,
        provider_factory: Callable[[AIConfig, str], AnthropicProvider] | None = None,
        environ: dict[str, str] | None = None,
    ):
        try:
            self.config = resolve_ai_config(settings, environ)
        except Exception:  # resilience: a broken AI setting never breaks the app
            log.exception("AI configuration could not be evaluated")
            self.config = AIConfig("misconfigured", "AI configuration could not be evaluated.")
        self._api_key = settings.anthropic_api_key
        self._session_factory = session_factory
        self._provider_factory = provider_factory or (
            lambda cfg, key: AnthropicProvider(key, timeout=cfg.timeout_seconds, max_retries=cfg.max_retries)
        )
        self._provider: AnthropicProvider | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ public API (for AI capabilities)
    def generate_text(
        self,
        capability: str,
        *,
        messages: list[dict[str, str]],
        system: str | None = None,
        actor_user_id: uuid.UUID | None = None,
        max_tokens: int | None = None,
    ) -> AIResult:
        response, info = self._call(capability, messages, system, actor_user_id, max_tokens, None)
        return AIResult(text=response.text, stop_reason=response.stop_reason, truncated=response.stop_reason == "max_tokens", usage=info)

    def generate_structured(
        self,
        capability: str,
        schema: type[T],
        *,
        messages: list[dict[str, str]],
        system: str | None = None,
        actor_user_id: uuid.UUID | None = None,
        max_tokens: int | None = None,
    ) -> AIStructuredResult[T]:
        response, info = self._call(capability, messages, system, actor_user_id, max_tokens, schema)
        if not isinstance(response.parsed, schema):  # defensive: _call already rejects invalid output
            raise AIError("invalid_response")
        return AIStructuredResult(data=response.parsed, usage=info)

    def stream_turn(
        self,
        capability: str,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec],
        actor_user_id: uuid.UUID | None = None,
        max_tokens: int | None = None,
    ) -> Iterator[str | ProviderTurn]:
        """One streamed assistant turn of a tool-using conversation (BI agent, property assistant).

        Yields text deltas, then the complete ``ProviderTurn`` (whose ``tool_uses`` the caller may run through the
        tool registry). Same guarantees as the other calls: kill switch, cost cap, refusal → ``AIError``, one
        metadata-only usage row per turn."""
        self._validate_conversation(capability, messages, system)
        if not self.config.enabled:
            self._record_rejection(capability, None, actor_user_id, self.config.state)
            raise AIError(self.config.state)
        if not self.config.capability_enabled(capability):
            self._record_rejection(capability, None, actor_user_id, "feature_disabled")
            raise AIError("feature_disabled")
        profile = self.config.profile(capability)
        if self._over_budget():
            self._record_rejection(capability, profile.model, actor_user_id, "budget_exceeded")
            raise AIError("budget_exceeded")
        limit = min(max_tokens or profile.max_tokens, self.config.max_output_tokens)
        started, request_id = time.monotonic(), uuid.uuid4()
        turn: ProviderTurn | None = None
        try:
            for item in self._get_provider().stream_turn(profile, system=system, messages=messages, tools=tools, max_tokens=limit):
                if isinstance(item, ProviderTurn):
                    turn = item
                else:
                    yield item
            if turn is None:
                raise AIError("invalid_response")
        except AIError as exc:
            self._record(
                request_id,
                capability,
                profile.model,
                actor_user_id,
                started,
                status="failed",
                error_category=exc.category,
                provider_status=exc.provider_status,
            )
            log.warning("AI turn failed", extra={"ai_capability": capability, "ai_error": exc.category, "ai_request_id": str(request_id)})
            raise
        cost = estimate_cost(
            turn.model, turn.input_tokens or 0, turn.output_tokens or 0, turn.cache_read_tokens or 0, turn.cache_write_tokens or 0
        )
        refused = turn.stop_reason == "refusal"
        self._record(
            request_id,
            capability,
            profile.model,
            actor_user_id,
            started,
            status="failed" if refused else "succeeded",
            error_category="refusal" if refused else None,
            response=turn,
            cost=cost,
        )
        if refused:
            raise AIError("refusal")
        yield turn

    def ensure_enabled(self, capability: str, *, actor_user_id: uuid.UUID | None = None) -> None:
        """Lets a streaming feature fail with a normal 503 *before* it starts streaming (records the rejection)."""
        if not self.config.enabled:
            self._record_rejection(capability, None, actor_user_id, self.config.state)
            raise AIError(self.config.state)
        if not self.config.capability_enabled(capability):
            self._record_rejection(capability, None, actor_user_id, "feature_disabled")
            raise AIError("feature_disabled")

    def availability(self) -> AIAvailability:
        """Configuration + the latest real outcome. A valid configuration alone is ``unverified``, never operational."""
        if self.config.state == "disabled":
            return AIAvailability("disabled", self.config.reason)
        if self.config.state == "misconfigured":
            return AIAvailability("misconfigured", self.config.reason)
        try:
            with self._session() as s:
                success, failure = AIUsageRepository(s).last_outcomes()
        except Exception:
            log.warning("AI usage history unavailable for the availability check", exc_info=True)
            return AIAvailability("unverified", "AI is configured; its usage history is unavailable right now.")
        if success is None and failure is None:
            return AIAvailability("unverified", "AI is configured but has not reached the provider yet. Run the AI health check.")
        last_ok, last_bad = (success.created_at if success else None), (failure.created_at if failure else None)
        if last_bad and (last_ok is None or last_bad > last_ok):
            return AIAvailability(
                "degraded", f"The last AI request failed ({failure.error_category}).", last_ok, last_bad, failure.error_category
            )
        return AIAvailability(
            "operational", "The last AI request succeeded.", last_ok, last_bad, failure.error_category if failure else None
        )

    def check_health(self, *, actor_user_id: uuid.UUID | None = None) -> list[ModelCheck]:
        """Looks up each configured model through the Models API (no tokens spent). Records one usage row per model."""
        if not self.config.enabled:
            self._record_rejection("system_check", None, actor_user_id, self.config.state)
            raise AIError(self.config.state)
        results: list[ModelCheck] = []
        for model in self.config.models:
            started, request_id = time.monotonic(), uuid.uuid4()
            try:
                self._get_provider().retrieve_model(model)
                results.append(ModelCheck(model, True, None))
                self._record(request_id, "system_check", model, actor_user_id, started, status="succeeded")
            except AIError as exc:
                results.append(ModelCheck(model, False, exc.category))
                self._record(
                    request_id,
                    "system_check",
                    model,
                    actor_user_id,
                    started,
                    status="failed",
                    error_category=exc.category,
                    provider_status=exc.provider_status,
                )
        return results

    def cost_today(self) -> Decimal:
        with self._session() as s:
            return AIUsageRepository(s).cost_since(start_of_day(datetime.now(UTC)))

    # ------------------------------------------------------------------ internals
    def _call(
        self,
        capability: str,
        messages: list[dict[str, str]],
        system: str | None,
        actor_user_id: uuid.UUID | None,
        max_tokens: int | None,
        schema: type[BaseModel] | None,
    ) -> tuple[ProviderResponse, AIUsageInfo]:
        self._validate_input(capability, messages, system)
        if not self.config.enabled:
            self._record_rejection(capability, None, actor_user_id, self.config.state)
            raise AIError(self.config.state)
        if not self.config.capability_enabled(capability):
            self._record_rejection(capability, None, actor_user_id, "feature_disabled")
            raise AIError("feature_disabled")
        profile = self.config.profile(capability)
        if self._over_budget():
            self._record_rejection(capability, profile.model, actor_user_id, "budget_exceeded")
            raise AIError("budget_exceeded")
        limit = min(max_tokens or profile.max_tokens, self.config.max_output_tokens)
        started, request_id = time.monotonic(), uuid.uuid4()
        try:
            response = self._get_provider().create(profile, system=system, messages=messages, max_tokens=limit, output_schema=schema)
        except AIError as exc:
            self._record(
                request_id,
                capability,
                profile.model,
                actor_user_id,
                started,
                status="failed",
                error_category=exc.category,
                provider_status=exc.provider_status,
            )
            log.warning(
                "AI request failed", extra={"ai_capability": capability, "ai_error": exc.category, "ai_request_id": str(request_id)}
            )
            raise
        failure = (
            "refusal" if response.stop_reason == "refusal" else ("truncated" if schema and response.stop_reason == "max_tokens" else None)
        )
        cost = estimate_cost(
            response.model,
            response.input_tokens or 0,
            response.output_tokens or 0,
            response.cache_read_tokens or 0,
            response.cache_write_tokens or 0,
        )
        duration = self._record(
            request_id,
            capability,
            profile.model,
            actor_user_id,
            started,
            status="failed" if failure else "succeeded",
            error_category=failure,
            response=response,
            cost=cost,
        )
        if failure:
            raise AIError(failure)
        info = AIUsageInfo(request_id, response.model, response.input_tokens, response.output_tokens, cost, duration)
        return response, info

    @staticmethod
    def _validate_input(capability: str, messages: list[dict[str, str]], system: str | None) -> None:
        """Programming errors in a capability, not user errors: raise ValueError before anything is sent."""
        from app.ai.config import CAPABILITIES

        if capability not in CAPABILITIES:
            raise ValueError(f"Unknown AI capability {capability!r}")
        if not messages or messages[0].get("role") != "user":
            raise ValueError("Messages must start with a user message.")
        total = len(system or "")
        for m in messages:
            if set(m) != {"role", "content"} or m["role"] not in ROLES or not isinstance(m["content"], str) or not m["content"].strip():
                raise ValueError("Each message needs a role (user|assistant) and non-empty text content only.")
            total += len(m["content"])
        if total > MAX_INPUT_CHARS:
            raise ValueError(f"AI input exceeds {MAX_INPUT_CHARS} characters.")

    @staticmethod
    def _validate_conversation(capability: str, messages: list[dict[str, Any]], system: str) -> None:
        from app.ai.config import CAPABILITIES

        if capability not in CAPABILITIES:
            raise ValueError(f"Unknown AI capability {capability!r}")
        if not messages or messages[0].get("role") != "user":
            raise ValueError("Messages must start with a user message.")
        for m in messages:
            if set(m) != {"role", "content"} or m["role"] not in ROLES:
                raise ValueError("Each message needs a role (user|assistant) and content only.")
            content = m["content"]
            if isinstance(content, str):
                if not content.strip():
                    raise ValueError("Message text can't be empty.")
            elif not (
                isinstance(content, list) and content and all(isinstance(b, dict) and b.get("type") in CONVERSATION_BLOCKS for b in content)
            ):
                raise ValueError("Message content must be text or known content blocks.")
        if len(system) + len(json.dumps(messages, default=str)) > MAX_CONVERSATION_CHARS:
            raise ValueError("The conversation is too long.")

    def _over_budget(self) -> bool:
        try:
            return self.cost_today() >= self.config.daily_cost_cap_usd
        except Exception:
            log.warning("AI cost cap could not be checked; refusing the call", exc_info=True)
            return True  # fail closed: never spend without being able to enforce the cap

    def _get_provider(self) -> AnthropicProvider:
        with self._lock:
            if self._provider is None:
                key = self._api_key.get_secret_value().strip() if self._api_key else ""
                if not key:
                    raise AIError("misconfigured")
                self._provider = self._provider_factory(self.config, key)
            return self._provider

    def _session(self) -> Session:
        if self._session_factory is None:
            from app.db.session import get_sessionmaker

            self._session_factory = get_sessionmaker()
        return self._session_factory()

    def _record_rejection(self, capability: str, model: str | None, actor_user_id: uuid.UUID | None, category: str) -> None:
        self._record(uuid.uuid4(), capability, model, actor_user_id, time.monotonic(), status="rejected", error_category=category)

    def _record(
        self,
        request_id: uuid.UUID,
        capability: str,
        model: str | None,
        actor_user_id: uuid.UUID | None,
        started: float,
        *,
        status: str,
        error_category: str | None = None,
        provider_status: int | None = None,
        response: ProviderResponse | ProviderTurn | None = None,
        cost: Decimal | None = None,
    ) -> int:
        """Writes the usage row in its own short transaction, so it survives a caller's rollback. A failure to write
        it is logged and never breaks the AI call (or anything else)."""
        duration = max(0, int((time.monotonic() - started) * 1000))
        row = AIUsage(
            request_id=request_id,
            provider_request_id=response.provider_request_id if response else None,
            actor_type="user" if actor_user_id else "system",
            actor_user_id=actor_user_id,
            capability=capability,
            provider=PROVIDER,
            model=model,
            served_model=response.model if response else None,
            status=status,
            error_category=error_category,
            provider_status=provider_status,
            stop_reason=response.stop_reason if response else None,
            input_tokens=response.input_tokens if response else None,
            output_tokens=response.output_tokens if response else None,
            cache_read_tokens=response.cache_read_tokens if response else None,
            cache_write_tokens=response.cache_write_tokens if response else None,
            estimated_cost_usd=cost,
            duration_ms=duration,
            created_at=datetime.now(UTC),
        )
        try:
            with self._session() as s:
                AIUsageRepository(s).add(row)
                s.commit()
        except Exception:
            log.warning("AI usage row could not be written", exc_info=True, extra={"ai_request_id": str(request_id)})
        return duration

    def profiles(self) -> list[ModelProfile]:
        return list(self.config.profiles.values())
