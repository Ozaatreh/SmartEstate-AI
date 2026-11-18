"""Test doubles for the AI gateway: the REAL Anthropic SDK over a scripted HTTP transport (no network).

These prove request building, response parsing, retries and error translation against the SDK itself.
They are not proof of a working integration with the real API — that is a separate, opt-in smoke test.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import anthropic
import httpx2

from app.ai.config import AIConfig
from app.ai.provider import AnthropicProvider

FAKE_KEY = "sk-ant-test-0123456789abcdefSECRET"


def message(text: str = "Hello from the fake model.", *, model: str = "claude-opus-5-5", stop: str = "end_turn",
            usage: dict[str, int] | None = None) -> dict[str, Any]:
    return {
        "id": "msg_test", "type": "message", "role": "assistant", "model": model,
        "content": [{"type": "text", "text": text}], "stop_reason": stop, "stop_sequence": None,
        "usage": usage or {"input_tokens": 1200, "output_tokens": 300, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 0},
    }


def error(status: int, kind: str = "api_error", msg: str = "boom", headers: dict[str, str] | None = None) -> httpx2.Response:
    return httpx2.Response(status, json={"type": "error", "error": {"type": kind, "message": msg}}, headers={"request-id": "req_err", **(headers or {})})


class Script:
    """Scripted transport: a list of responses (or exceptions / callables) consumed in order; the last one repeats."""

    def __init__(self, *steps: Any):
        self.steps = list(steps)
        self.requests: list[dict[str, Any]] = []
        self.paths: list[str] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.paths.append(request.url.path)
        self.requests.append(json.loads(request.content) if request.content else {})
        step = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        if isinstance(step, Exception):
            raise step
        if callable(step) and not isinstance(step, httpx2.Response):
            return step(request)
        if isinstance(step, httpx2.Response):
            return step
        return httpx2.Response(200, json=step, headers={"request-id": "req_ok_123"})

    @property
    def calls(self) -> int:
        return len(self.requests)


def provider(script: Script, *, retries: int = 0, timeout: float = 30.0) -> AnthropicProvider:
    http = anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(script))
    return AnthropicProvider(FAKE_KEY, timeout=timeout, max_retries=retries, http_client=http)


def factory(script: Script, *, retries: int | None = None) -> Callable[[AIConfig, str], AnthropicProvider]:
    def make(cfg: AIConfig, key: str) -> AnthropicProvider:
        assert key == FAKE_KEY  # the gateway passes the configured key, nothing ambient
        return provider(script, retries=cfg.max_retries if retries is None else retries, timeout=cfg.timeout_seconds)

    return make


def timeout_error(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ReadTimeout("timed out", request=request)


def connect_error(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ConnectError("unreachable", request=request)


# --- streaming (Phase 6C) ----------------------------------------------------------------------------------------
def text_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def tool_block(name: str, tool_input: dict[str, Any], tool_id: str | None = None) -> dict[str, Any]:
    return {"type": "tool_use", "id": tool_id or f"toolu_{name}", "name": name, "input": tool_input}


def thinking_block(thinking: str = "Considering the data.", signature: str = "sig_abc") -> dict[str, Any]:
    return {"type": "thinking", "thinking": thinking, "signature": signature}


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def stream(*blocks: dict[str, Any], stop: str | None = None, model: str = "claude-opus-5-5",
           usage: dict[str, int] | None = None) -> Callable[[httpx2.Request], httpx2.Response]:
    """A streamed Messages API response (server-sent events) built from content blocks. Returns a factory so a
    Script can serve a fresh body each time."""
    u = usage or {"input_tokens": 900, "output_tokens": 120, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    stop_reason = stop or ("tool_use" if any(b["type"] == "tool_use" for b in blocks) else "end_turn")
    parts = [_sse("message_start", {"type": "message_start", "message": {
        "id": "msg_stream", "type": "message", "role": "assistant", "model": model, "content": [], "stop_reason": None,
        "stop_sequence": None, "usage": {**u, "output_tokens": 1}}})]
    for i, b in enumerate(blocks):
        if b["type"] == "text":
            parts.append(_sse("content_block_start", {"type": "content_block_start", "index": i, "content_block": {"type": "text", "text": ""}}))
            for chunk in (b["text"][: len(b["text"]) // 2], b["text"][len(b["text"]) // 2:]):
                if chunk:
                    parts.append(_sse("content_block_delta", {"type": "content_block_delta", "index": i,
                                                              "delta": {"type": "text_delta", "text": chunk}}))
        elif b["type"] == "tool_use":
            parts.append(_sse("content_block_start", {"type": "content_block_start", "index": i, "content_block": {
                "type": "tool_use", "id": b["id"], "name": b["name"], "input": {}}}))
            parts.append(_sse("content_block_delta", {"type": "content_block_delta", "index": i,
                                                      "delta": {"type": "input_json_delta", "partial_json": json.dumps(b["input"])}}))
        elif b["type"] == "thinking":
            parts.append(_sse("content_block_start", {"type": "content_block_start", "index": i, "content_block": {
                "type": "thinking", "thinking": "", "signature": ""}}))
            parts.append(_sse("content_block_delta", {"type": "content_block_delta", "index": i,
                                                      "delta": {"type": "thinking_delta", "thinking": b["thinking"]}}))
            parts.append(_sse("content_block_delta", {"type": "content_block_delta", "index": i,
                                                      "delta": {"type": "signature_delta", "signature": b["signature"]}}))
        parts.append(_sse("content_block_stop", {"type": "content_block_stop", "index": i}))
    parts.append(_sse("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                                        "usage": {"output_tokens": u["output_tokens"]}}))
    parts.append(_sse("message_stop", {"type": "message_stop"}))
    body = "".join(parts).encode()

    def respond(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=body, headers={"content-type": "text/event-stream", "request-id": "req_stream_1"})

    return respond
