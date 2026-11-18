import { MessageSquarePlus, Sparkles } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/system/layout-blocks";
import { ListSkeleton } from "@/components/system/states";
import { Button } from "@/components/ui/button";
import { useAIStatus } from "@/features/crm/api";
import { ApiError } from "@/lib/api-client";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import { fromDetail, loadBIConversation, useBIConversations, useChatStream, useRefreshBIConversations } from "./api";
import { Composer, SuggestedPrompts, Transcript } from "./chat";

const PROMPTS = [
  "Which department is closest to its budget limit?",
  "How many approvals are waiting, and which are the oldest?",
  "How does the lead funnel look right now?",
  "How many units are still available in each project?",
  "Did any automation workflows fail in the last 24 hours?",
];

export default function BIAgentPage() {
  const status = useAIStatus();
  const conversations = useBIConversations();
  const refresh = useRefreshBIConversations();
  const chat = useChatStream("/ai/bi/messages", { onConversation: () => refresh() });
  const [opening, setOpening] = React.useState<string | null>(null);
  const unavailable = status.data && !status.data.usable;

  const open = async (id: string) => {
    if (id === chat.conversationId) return;
    setOpening(id);
    try {
      chat.reset(id, fromDetail(await loadBIConversation(id)));
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Couldn't open the conversation");
    } finally {
      setOpening(null);
    }
  };

  return (
    <div className="flex min-h-[calc(100dvh-8rem)] flex-col">
      <PageHeader
        title="BI Agent"
        description="Ask about budgets, approvals, purchase orders, leads, inventory and workflows. Answers come from live data you are allowed to see; the agent can't change anything."
        actions={<Button onClick={() => chat.reset()} disabled={chat.busy}><MessageSquarePlus /> New conversation</Button>}
      />
      <div className="grid flex-1 gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="hidden rounded-[var(--radius-panel)] border border-border bg-surface lg:block" aria-label="Conversations">
          <p className="border-b border-border-subtle px-4 py-3 text-small font-semibold">Your conversations</p>
          {conversations.isPending ? <ListSkeleton rows={4} /> : conversations.data?.length ? (
            <ul className="max-h-[60vh] overflow-y-auto p-1.5">
              {conversations.data.map((c) => (
                <li key={c.id}>
                  <button type="button" onClick={() => void open(c.id)} disabled={chat.busy || opening !== null}
                    aria-current={c.id === chat.conversationId ? "true" : undefined}
                    className={cn("w-full rounded-[var(--radius-control)] px-2.5 py-2 text-left transition-colors hover:bg-surface-subtle disabled:opacity-60",
                      c.id === chat.conversationId && "bg-surface-subtle")}>
                    <span className="line-clamp-2 text-small text-fg">{c.title}</span>
                    <span className="text-caption text-fg-muted">{formatRelative(c.updated_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : <p className="p-4 text-small text-fg-muted">No conversations yet.</p>}
        </aside>

        <section className="flex min-h-[480px] flex-col rounded-[var(--radius-panel)] border border-border bg-surface" aria-label="Chat">
          <div className="flex-1 overflow-y-auto p-4 sm:p-6">
            {unavailable ? (
              <p role="status" className="flex items-start gap-2 text-small text-fg-muted">
                <Sparkles className="mt-0.5 size-4 shrink-0" aria-hidden />
                The BI agent is unavailable right now — {status.data?.reason.replace(/\.+$/, "")}. All other screens work as usual.
              </p>
            ) : (
              <Transcript messages={chat.messages} empty={
                <div className="mx-auto max-w-xl py-8 text-center">
                  <Sparkles className="mx-auto mb-3 size-6 text-ai" aria-hidden />
                  <p className="text-body font-medium">Ask a question about the business</p>
                  <p className="mb-5 mt-1 text-small text-fg-muted">Each answer shows the data it used. Areas you don't have access to are refused.</p>
                  <SuggestedPrompts prompts={PROMPTS} onPick={(p) => void chat.send(p)} disabled={chat.busy} />
                </div>
              } />
            )}
          </div>
          <div className="border-t border-border-subtle p-3">
            <Composer onSend={(t) => void chat.send(t)} busy={chat.busy} disabled={Boolean(unavailable)} maxLength={4000}
              placeholder="Ask about budgets, approvals, leads, inventory…"
              footer="AI-generated answers from live data. Check important figures in the source screen." />
          </div>
        </section>
      </div>
    </div>
  );
}
