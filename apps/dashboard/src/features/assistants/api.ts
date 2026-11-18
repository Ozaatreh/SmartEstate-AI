import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { api, apiStream, ApiError, type StreamEvent } from "@/lib/api-client";
import { humanize } from "@/lib/status";

// --- wire types (backend app/ai/features/*) ------------------------------------------------------------------
export interface PublicUnit {
  code: string; project: string; project_code: string; type: string; bedrooms: number; bathrooms: number; floor: number;
  area_sqm: string; view: string | null; list_price_sar: string; status: string;
}
export type ResultCard =
  | { kind: "units"; units: PublicUnit[] }
  | { kind: "table"; title: string; columns: string[]; rows: Record<string, unknown>[] }
  | { kind: "lead_created" };

export interface ToolActivity { name: string; label: string; status: "ok" | "denied" | "error"; summary: string | null }

export interface ConversationSummary { id: string; title: string; message_count: number; created_at: string; updated_at: string }
export interface ConversationDetail extends ConversationSummary {
  messages: { role: "user" | "assistant"; text: string; tools: ToolActivity[] }[];
}

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

export function fromDetail(d: ConversationDetail): ChatMessage[] {
  return d.messages.map((m) => ({ id: nextId(), role: m.role, text: m.text, tools: m.tools, cards: [], status: "done" }));
}

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

// --- BI agent ------------------------------------------------------------------------------------------------
export function useBIConversations() {
  return useQuery({ queryKey: ["ai", "bi", "conversations"], queryFn: () => api.get<ConversationSummary[]>("/ai/bi/conversations") });
}

export function useRefreshBIConversations() {
  const qc = useQueryClient();
  return () => void qc.invalidateQueries({ queryKey: ["ai", "bi", "conversations"] });
}

export const loadBIConversation = (id: string) => api.get<ConversationDetail>(`/ai/bi/conversations/${id}`);
