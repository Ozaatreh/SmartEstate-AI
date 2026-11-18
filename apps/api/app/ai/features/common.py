"""Shared pieces of the assistant endpoints: SSE encoding and the display form of a stored conversation."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.models import AIMessage, AIToolCall


class ToolUsed(BaseModel):
    name: str
    label: str
    status: str
    summary: str | None


class DisplayMessage(BaseModel):
    role: str  # user | assistant
    text: str
    tools: list[ToolUsed] = []


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[DisplayMessage]


def sse(events: Iterator[dict[str, Any]]) -> StreamingResponse:
    def encode() -> Iterator[str]:
        for event in events:
            yield f"event: {event['type']}\ndata: {json.dumps(event, default=str, ensure_ascii=False)}\n\n"

    return StreamingResponse(encode(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def display_messages(session: Session, conversation_id: uuid.UUID, labels: dict[str, str]) -> list[DisplayMessage]:
    """User questions and assistant answers (text only), with the tools each answer used. Tool plumbing is hidden."""
    rows = list(session.scalars(select(AIMessage).where(AIMessage.conversation_id == conversation_id).order_by(AIMessage.seq)))
    calls: dict[uuid.UUID, list[AIToolCall]] = {}
    for c in session.scalars(select(AIToolCall).where(AIToolCall.conversation_id == conversation_id).order_by(AIToolCall.created_at)):
        if c.message_id:
            calls.setdefault(c.message_id, []).append(c)
    out: list[DisplayMessage] = []
    for m in rows:
        texts = [b.get("text", "") for b in m.content if b.get("type") == "text"]
        if m.role == "user":
            if texts:  # tool_result messages carry no text and are not shown
                out.append(DisplayMessage(role="user", text="\n".join(texts)))
            continue
        if not out or out[-1].role != "assistant":
            out.append(DisplayMessage(role="assistant", text=""))
        cur = out[-1]
        joined = "".join(texts)
        cur.text = f"{cur.text}{joined}" if cur.text and joined else cur.text or joined
        cur.tools.extend(
            ToolUsed(name=c.tool_name, label=labels.get(c.tool_name, c.tool_name), status=c.status, summary=c.result_summary)
            for c in calls.get(m.id, [])
        )
    return out
