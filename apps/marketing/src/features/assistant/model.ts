import * as React from "react";
import { ApiError, apiStream, type PublicUnit, type StreamEvent } from "@/lib/api";
import { humanize } from "@/lib/status";

/* Visitor chat model — moved from the dashboard with the public assistant (Phase 7A). The assistant's behaviour
   (tools, consent, lead registration) lives entirely in the backend: app/ai/features/property_assistant.py. */

// --- wire types (backend app/ai/features/*) ------------------------------------------------------------------
export type ResultCard =
  | { kind: "units"; units: PublicUnit[] }
  | { kind: "table"; title: string; columns: string[]; rows: Record<string, unknown>[] }
  | { kind: "lead_created" };

export interface ToolActivity { name: string; label: string; status: "ok" | "denied" | "error"; summary: string | null }


// --- UI model ------------------------------------------------------------------------------------------------
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  tools: ToolActivity[];
  cards: ResultCard[];
  status: "streaming" | "done" | "error";
  error?: string;
  truncated?: boolean;
}

/** "allocated_sar" → "Allocated (SAR)", "utilisation_pct" → "Utilisation (%)". */
export function columnLabel(key: string): string {
  const unit = key.endsWith("_sar") ? " (SAR)" : key.endsWith("_pct") ? " (%)" : "";
  return humanize(key.replace(/_(sar|pct)$/, "")) + unit;
}

let seq = 0;
const nextId = () => `m${++seq}`;

/** Applies one server-sent event to the assistant message being streamed. Pure; exported for tests. */
export function applyEvent(msg: ChatMessage, e: StreamEvent): ChatMessage {
  switch (e.type) {
    case "text":
      return { ...msg, text: msg.text + String(e.text ?? "") };
    case "tool": {
      const tool: ToolActivity = { name: String(e.name), label: String(e.label), status: e.status as ToolActivity["status"], summary: (e.summary as string) ?? null };
      const cards = Array.isArray(e.cards) ? (e.cards as ResultCard[]) : [];
      return { ...msg, tools: [...msg.tools, tool], cards: [...msg.cards, ...cards] };
    }
    case "done":
      return { ...msg, status: "done", truncated: Boolean(e.truncated) };
    case "error":
      return { ...msg, status: "error", error: String(e.message ?? "The assistant could not answer.") };
    default:
      return msg;
  }
}

/**
 * Chat state + streaming for one conversation. `endpoint` is the streaming POST; `extra` adds fields
 * (e.g. the visitor's consent flag) to each message.
 */
export function useChatStream(endpoint: string, opts: { onConversation?: (id: string) => void } = {}) {
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const abort = React.useRef<AbortController | null>(null);
  React.useEffect(() => () => abort.current?.abort(), []);

  const update = (id: string, fn: (m: ChatMessage) => ChatMessage) => setMessages((all) => all.map((m) => (m.id === id ? fn(m) : m)));

  const send = async (text: string, extra: Record<string, unknown> = {}) => {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    const assistantId = nextId();
    setMessages((all) => [
      ...all,
      { id: nextId(), role: "user", text: trimmed, tools: [], cards: [], status: "done" },
      { id: assistantId, role: "assistant", text: "", tools: [], cards: [], status: "streaming" },
    ]);
    setBusy(true);
    abort.current = new AbortController();
    try {
      await apiStream(endpoint, { conversation_id: conversationId, message: trimmed, ...extra }, (e) => {
        if (e.type === "start" && typeof e.conversation_id === "string") {
          setConversationId(e.conversation_id);
          opts.onConversation?.(e.conversation_id);
        }
        update(assistantId, (m) => applyEvent(m, e));
      }, abort.current.signal);
      update(assistantId, (m) => (m.status === "streaming" ? { ...m, status: "done" } : m));
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      const message = err instanceof ApiError ? err.message : "The assistant could not answer.";
      update(assistantId, (m) => ({ ...m, status: "error", error: message }));
    } finally {
      setBusy(false);
    }
  };

  const reset = (id: string | null = null, initial: ChatMessage[] = []) => {
    abort.current?.abort();
    setBusy(false);
    setConversationId(id);
    setMessages(initial);
  };

  return { messages, conversationId, busy, send, reset };
}

