"""Anthropic provider — the ONLY module in ``app/`` that imports the ``anthropic`` SDK (enforced by a test).

It sends one Messages API request, validates the response shape and translates SDK exceptions into
``AIError`` categories. It knows nothing about users, permissions, the database or business records: callers
pass plain text in and get text / a validated Pydantic object out. For the assistants (Phase 6C) it can also
*describe* tools and return the model's tool requests; it never executes a tool — the tool registry does that,
under the caller's permissions.

Retries: the SDK's own bounded retry (``max_retries``) covers only transient failures — connection errors,
timeouts, 408/409/429 and 5xx. Authentication, permission, validation (400/404/422) and malformed responses are
never retried.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import anthropic
from pydantic import BaseModel, ValidationError

from app.ai.config import SERVER_FALLBACK_BETA, ModelProfile
from app.ai.errors import AIError


@dataclass(frozen=True)
class ProviderResponse:
    model: str  # the model that actually answered (a server-side fallback may differ from the requested one)
    text: str
    parsed: BaseModel | None
    stop_reason: str | None
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    cache_write_tokens: int | None
    provider_request_id: str | None


@dataclass(frozen=True)
class ToolSpec:
    """A tool the model may *ask* to run. The provider only describes it; running it (with validation and
    permission checks) is the tool registry's job, never the provider's."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolUse:
    id: str
    name: str
    input: Any


@dataclass(frozen=True)
class ProviderTurn:
    """One assistant turn of a tool-using conversation."""

    model: str
    content: list[dict[str, Any]]  # API content blocks, replayed unchanged on the next turn (thinking included)
    text: str
    tool_uses: list[ToolUse] = field(default_factory=list)
    stop_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    provider_request_id: str | None = None


@contextmanager
def _translate() -> Iterator[None]:
    """SDK exception → AIError. Order matters: most specific first."""
    try:
        yield
    except AIError:
        raise
    except anthropic.AuthenticationError as exc:
        raise AIError("authentication", status_code=exc.status_code) from None
    except anthropic.PermissionDeniedError as exc:
        raise AIError("permission", status_code=exc.status_code) from None
    except anthropic.NotFoundError as exc:
        raise AIError("model_not_found", status_code=exc.status_code) from None
    except anthropic.RateLimitError as exc:
        raise AIError("rate_limited", status_code=exc.status_code) from None
    except anthropic.APITimeoutError:
        raise AIError("timeout") from None
    except anthropic.APIConnectionError:
        raise AIError("connection") from None
    except anthropic.BadRequestError as exc:
        raise AIError("bad_request", status_code=exc.status_code) from None
    except anthropic.InternalServerError as exc:
        category = "overloaded" if exc.status_code == 529 else "provider_error"
        raise AIError(category, status_code=exc.status_code) from None
    except anthropic.APIStatusError as exc:
        category = "provider_error" if exc.status_code >= 500 else "bad_request"
        raise AIError(category, status_code=exc.status_code) from None
    except (ValidationError, ValueError, anthropic.APIResponseValidationError):
        raise AIError("invalid_response") from None
    except anthropic.AnthropicError:
        raise AIError("provider_error") from None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, *, timeout: float, max_retries: int, http_client: Any = None):
        # The key is passed explicitly so ambient credentials (other env vars, CLI profiles) are never picked up.
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=max_retries, http_client=http_client)

    def create(
        self,
        profile: ModelProfile,
        *,
        system: str | None,
        messages: list[dict[str, str]],
        max_tokens: int,
        output_schema: type[BaseModel] | None = None,
    ) -> ProviderResponse:
        params: dict[str, Any] = {
            "model": profile.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": profile.effort},
        }
        if system:
            params["system"] = system
        if profile.server_fallback:
            params["betas"] = [SERVER_FALLBACK_BETA]
            params["fallbacks"] = "default"
        with _translate():
            if output_schema is not None:
                response = self._client.beta.messages.parse(output_format=output_schema, **params)
            else:
                response = self._client.beta.messages.create(**params)
        return self._validate(response, output_schema)

    def stream_turn(
        self,
        profile: ModelProfile,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec],
        max_tokens: int,
    ) -> Iterator[str | ProviderTurn]:
        """Streams one assistant turn: yields text deltas (``str``), then the complete ``ProviderTurn``.
        Tools are strict (``tool_choice`` stays ``auto``); their inputs are validated again by the registry."""
        params: dict[str, Any] = {
            "model": profile.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": profile.effort},
        }
        if tools:
            params["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": anthropic.transform_schema(t.input_schema),
                    "strict": True,
                    "eager_input_streaming": True,
                }
                for t in tools
            ]
        if profile.server_fallback:
            params["betas"] = [SERVER_FALLBACK_BETA]
            params["fallbacks"] = "default"
        with _translate(), self._client.beta.messages.stream(**params) as stream:
            for event in stream:
                if getattr(event, "type", None) == "text" and isinstance(getattr(event, "text", None), str):
                    yield event.text
            final = stream.get_final_message()
            response = getattr(stream, "response", None)
            request_id = response.headers.get("request-id") if response is not None else None
        yield self._turn(final, request_id)

    @staticmethod
    def _turn(message: Any, stream_request_id: str | None = None) -> ProviderTurn:
        content = getattr(message, "content", None)
        usage = getattr(message, "usage", None)
        model = getattr(message, "model", None)
        if not isinstance(content, list) or usage is None or not isinstance(model, str):
            raise AIError("invalid_response")
        blocks: list[dict[str, Any]] = []
        tool_uses: list[ToolUse] = []
        texts: list[str] = []
        for b in content:
            data = b.model_dump(mode="json", exclude_none=True) if hasattr(b, "model_dump") else None
            if not isinstance(data, dict) or not isinstance(data.get("type"), str):
                raise AIError("invalid_response")
            blocks.append(data)
            if data["type"] == "text":
                texts.append(data.get("text") or "")
            elif data["type"] == "tool_use":
                if not isinstance(data.get("id"), str) or not isinstance(data.get("name"), str):
                    raise AIError("invalid_response")
                tool_uses.append(ToolUse(data["id"], data["name"], data.get("input")))
        stop_reason = getattr(message, "stop_reason", None)
        request_id = stream_request_id or getattr(message, "_request_id", None)
        return ProviderTurn(
            model=model,
            content=blocks,
            text="".join(texts),
            tool_uses=tool_uses,
            stop_reason=stop_reason if isinstance(stop_reason, str) else None,
            input_tokens=_int(getattr(usage, "input_tokens", None)),
            output_tokens=_int(getattr(usage, "output_tokens", None)),
            cache_read_tokens=_int(getattr(usage, "cache_read_input_tokens", None)),
            cache_write_tokens=_int(getattr(usage, "cache_creation_input_tokens", None)),
            provider_request_id=request_id if isinstance(request_id, str) else None,
        )

    def retrieve_model(self, model_id: str) -> str:
        with _translate():
            info = self._client.models.retrieve(model_id)
        model = getattr(info, "id", None)
        if not isinstance(model, str) or not model:
            raise AIError("invalid_response")
        return model

    @staticmethod
    def _validate(response: Any, output_schema: type[BaseModel] | None) -> ProviderResponse:
        """The SDK is lenient with malformed 200 responses (it can return a bare string or a message whose fields
        are None), so the shape is checked here before anything is trusted."""
        content = getattr(response, "content", None)
        usage = getattr(response, "usage", None)
        model = getattr(response, "model", None)
        if not isinstance(content, list) or usage is None or not isinstance(model, str):
            raise AIError("invalid_response")
        text = "".join(getattr(b, "text", "") or "" for b in content if getattr(b, "type", None) == "text")
        parsed = getattr(response, "parsed_output", None) if output_schema is not None else None
        stop_reason = getattr(response, "stop_reason", None)
        if output_schema is not None and stop_reason not in ("refusal", "max_tokens") and not isinstance(parsed, output_schema):
            raise AIError("invalid_response")
        request_id = getattr(response, "_request_id", None)
        return ProviderResponse(
            model=model,
            text=text,
            parsed=parsed if isinstance(parsed, BaseModel) else None,
            stop_reason=stop_reason if isinstance(stop_reason, str) else None,
            input_tokens=_int(getattr(usage, "input_tokens", None)),
            output_tokens=_int(getattr(usage, "output_tokens", None)),
            cache_read_tokens=_int(getattr(usage, "cache_read_input_tokens", None)),
            cache_write_tokens=_int(getattr(usage, "cache_creation_input_tokens", None)),
            provider_request_id=request_id if isinstance(request_id, str) else None,
        )
