"""Tool-using chat loop shared by the BI agent and the property assistant.

One user message → up to ``MAX_TOOL_CALLS`` tool runs → a final answer. Every model call goes through the gateway
(kill switch, cost cap, usage row); every tool request goes through the registry (validation, permission, audit row).
The turn is stored only when it completes, so the stored history is always a valid conversation to replay.

Events yielded to the caller (sent to the browser as server-sent events):
``start`` · ``text`` (delta) · ``tool`` (label, status, summary, cards) · ``done`` · ``error`` (code, message).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.errors import AIError
from app.ai.gateway import AIGateway
from app.ai.models import AIConversation, AIMessage, AIToolCall
from app.ai.provider import ProviderTurn
from app.ai.tools.registry import ToolContext, ToolOutcome, ToolRegistry

log = logging.getLogger(__name__)
MAX_TOOL_CALLS = 8  # per user message (ARCHITECTURE § 7.2)
MAX_MODEL_CALLS = MAX_TOOL_CALLS + 2
TOOL_LIMIT_MESSAGE = '{"status": "error", "error": "Tool call limit reached for this question. Answer with what you have."}'

Event = dict[str, Any]


def history(session: Session, conversation_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = session.scalars(select(AIMessage).where(AIMessage.conversation_id == conversation_id).order_by(AIMessage.seq))
    return [{"role": m.role, "content": m.content} for m in rows]


def _complete_content(turn: ProviderTurn) -> list[dict[str, Any]]:
    """A turn cut off mid tool request can't be replayed with an unanswered tool_use: keep everything else."""
    if turn.tool_uses and turn.stop_reason != "tool_use":
        content = [b for b in turn.content if b.get("type") != "tool_use"]
        return content or [{"type": "text", "text": "(The answer was cut off.)"}]
    return turn.content


class ChatEngine:
    def __init__(self, session: Session, gateway: AIGateway, registry: ToolRegistry):
        self.session = session
        self.gateway = gateway
        self.registry = registry

    def run(
        self,
        conversation: AIConversation,
        user_text: str,
        *,
        capability: str,
        system: str,
        ctx: ToolContext,
        actor_user_id: uuid.UUID | None,
    ) -> Iterator[Event]:
        messages = history(self.session, conversation.id)
        user_msg = {"role": "user", "content": [{"type": "text", "text": user_text}]}
        messages.append(user_msg)
        new: list[dict[str, Any]] = [user_msg]
        outcomes: list[tuple[ToolOutcome, int]] = []  # (outcome, index in `new` of the assistant message that asked)
        specs = self.registry.specs(ctx.audience)
        used = 0
        turn: ProviderTurn | None = None
        yield {"type": "start", "conversation_id": str(conversation.id)}
        try:
            for _ in range(MAX_MODEL_CALLS):
                turn = None
                for item in self.gateway.stream_turn(
                    capability, system=system, messages=messages, tools=specs, actor_user_id=actor_user_id
                ):
                    if isinstance(item, ProviderTurn):
                        turn = item
                    else:
                        yield {"type": "text", "text": item}
                assert turn is not None  # noqa: S101 — stream_turn always ends with the turn or raises
                assistant = {"role": "assistant", "content": _complete_content(turn)}
                messages.append(assistant)
                new.append(assistant)
                if not turn.tool_uses or turn.stop_reason != "tool_use":
                    break
                asking = len(new) - 1
                results = []
                for tu in turn.tool_uses:
                    if used >= MAX_TOOL_CALLS:
                        outcome = ToolOutcome(tu.id, tu.name, tu.name, "error", "Tool call limit reached", TOOL_LIMIT_MESSAGE)
                    else:
                        used += 1
                        outcome = self.registry.run(ctx, tu.id, tu.name, tu.input)
                    outcomes.append((outcome, asking))
                    yield {
                        "type": "tool",
                        "name": outcome.name,
                        "label": outcome.label,
                        "status": outcome.status,
                        "summary": outcome.summary,
                        "cards": outcome.cards,
                    }
                    results.append({"type": "tool_result", "tool_use_id": tu.id, "content": outcome.content, "is_error": outcome.is_error})
                user_results = {"role": "user", "content": results}
                messages.append(user_results)
                new.append(user_results)
            else:
                raise AIError("truncated")  # the model kept asking for tools; nothing half-finished is stored
        except AIError as exc:
            self._save_tool_calls_only(outcomes)
            yield {"type": "error", "code": exc.code, "message": exc.message}
            return
        except Exception:
            log.exception("Assistant turn failed")
            self.session.rollback()
            yield {"type": "error", "code": "assistant_failed", "message": "The assistant could not finish this answer."}
            return
        self._save(conversation, new, outcomes, user_text)
        yield {
            "type": "done",
            "conversation_id": str(conversation.id),
            "truncated": bool(turn and turn.stop_reason == "max_tokens"),
            "tools": [{"name": o.name, "label": o.label, "status": o.status, "summary": o.summary} for o, _ in outcomes],
        }

    def _save(
        self, conversation: AIConversation, new: list[dict[str, Any]], outcomes: list[tuple[ToolOutcome, int]], user_text: str
    ) -> None:
        lead_id = conversation.lead_id  # may have been set by create_lead_with_consent during this turn
        conv = self.session.get(AIConversation, conversation.id, with_for_update=True, populate_existing=True)
        assert conv is not None  # noqa: S101
        rows = []
        for i, m in enumerate(new):
            row = AIMessage(id=uuid.uuid4(), conversation_id=conv.id, seq=conv.message_count + i, role=m["role"], content=m["content"])
            rows.append(row)
        self.session.add_all(rows)
        for outcome, idx in outcomes:
            record = outcome.record or AIToolCall(
                audience="internal", tool_name=outcome.name[:60], input={}, status=outcome.status, result_summary=outcome.summary[:500]
            )
            record.conversation_id = conv.id
            record.message_id = rows[idx].id
            self.session.add(record)
        conv.message_count += len(new)
        conv.updated_at = datetime.now(UTC)
        if conv.title in ("", "New conversation"):
            conv.title = user_text.strip().splitlines()[0][:120] or "Conversation"
        if lead_id and not conv.lead_id:
            conv.lead_id = lead_id
        self.session.commit()

    def _save_tool_calls_only(self, outcomes: list[tuple[ToolOutcome, int]]) -> None:
        """Failed turns aren't stored as messages, but the tools they ran stay on record."""
        try:
            for outcome, _ in outcomes:
                if outcome.record is not None:
                    self.session.add(outcome.record)
            self.session.commit()
        except Exception:
            log.warning("Tool-call records could not be written", exc_info=True)
            self.session.rollback()
