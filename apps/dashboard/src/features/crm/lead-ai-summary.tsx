import { AlertTriangle, ArrowRight, RotateCw, Sparkles } from "lucide-react";
import * as React from "react";
import { AiBadge } from "@/components/system/badges";
import { Panel } from "@/components/system/layout-blocks";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/primitives";
import { ApiError } from "@/lib/api-client";
import { formatDateTime, formatRelative } from "@/lib/format";
import { useAIStatus, useGenerateLeadSummary, type LeadSummary } from "./api";

const UNAVAILABLE_CODES = new Set(["ai_disabled", "ai_misconfigured"]);

/** Advisory AI briefing for a lead. Generated on demand through the backend AI gateway; it never changes the lead,
 *  and the rest of the page works the same whether or not AI is available. */
export function LeadAISummary({ leadId }: { leadId: string }) {
  const status = useAIStatus();
  const generate = useGenerateLeadSummary(leadId);
  const [summary, setSummary] = React.useState<LeadSummary | null>(null);

  const run = () => generate.mutate(undefined, { onSuccess: (s) => setSummary(s) });
  const error = generate.error;
  const errorCode = error instanceof ApiError ? error.code : null;
  const unavailable = (status.data && !status.data.usable) || (errorCode !== null && UNAVAILABLE_CODES.has(errorCode) && !summary);
  const busy = generate.isPending;

  return (
    <Panel
      title={<span className="inline-flex items-center gap-2">AI lead summary <AiBadge /></span>}
      description="Advisory briefing from the recorded lead data. It never changes the lead."
      actions={!unavailable && summary && (
        <Button size="sm" variant="ghost" onClick={run} loading={busy} aria-label="Regenerate AI summary">
          <RotateCw /> Regenerate
        </Button>
      )}
      footer={summary && (
        <p className="text-caption text-fg-muted">
          <span title={formatDateTime(summary.generated_at)}>Generated {formatRelative(summary.generated_at)}</span>
          {" · "}based on {summary.interactions_considered} recorded {summary.interactions_considered === 1 ? "interaction" : "interactions"}
          {" · "}{summary.advisory_notice}
        </p>
      )}
    >
      {status.isPending ? (
        <div className="p-4"><Skeleton className="h-4 w-2/3" /></div>
      ) : unavailable ? (
        <p className="flex items-start gap-2 p-4 text-small text-fg-muted" role="status">
          <Sparkles className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>
            AI summaries are unavailable right now{status.data?.reason ? ` — ${status.data.reason.replace(/\.+$/, "")}` : ""}. Everything else on this lead works as usual.
          </span>
        </p>
      ) : busy && !summary ? (
        <div className="space-y-2 p-4" aria-busy="true" aria-label="Generating AI summary">
          <Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-5/6" /><Skeleton className="h-4 w-2/3" />
          <p className="pt-1 text-caption text-fg-muted">Generating summary… this can take up to a minute.</p>
        </div>
      ) : (
        <>
          {error && (
            <div role="alert" className="m-4 flex flex-wrap items-center gap-3 rounded-[var(--radius-control)] border border-danger/40 bg-danger/5 px-3 py-2 text-small">
              <AlertTriangle className="size-4 shrink-0 text-danger" aria-hidden />
              <span className="min-w-0 flex-1">
                {error instanceof ApiError ? error.message : "The summary could not be generated."}
                {summary && " The summary below is from the previous run."}
              </span>
              <Button size="sm" onClick={run} loading={busy}>Try again</Button>
            </div>
          )}
          {summary ? (
            <SummaryBody summary={summary} stale={busy} />
          ) : !error && (
            <div className="flex flex-col items-start gap-3 p-4">
              <p className="text-small text-fg-secondary">
                Get a quick briefing on this lead: overview, buying signals, concerns and a suggested next step. Contact details are not sent to the AI.
              </p>
              <Button variant="primary" size="sm" onClick={run} loading={busy}><Sparkles /> Generate summary</Button>
            </div>
          )}
        </>
      )}
    </Panel>
  );
}

function SummaryBody({ summary: s, stale }: { summary: LeadSummary; stale: boolean }) {
  return (
    <div className={stale ? "opacity-60 transition-opacity" : undefined} aria-busy={stale || undefined}>
      <p className="px-4 pt-4 text-body text-fg">{s.overview}</p>
      <div className="grid gap-4 p-4 sm:grid-cols-2">
        <SummaryList title="Buying signals" items={s.buying_signals} empty="No clear buying signals recorded yet." />
        <SummaryList title="Concerns & missing information" items={s.concerns} empty="Nothing flagged." />
      </div>
      <div className="mx-4 mb-4 rounded-[var(--radius-control)] border border-ai/30 bg-ai-subtle px-3 py-2.5">
        <p className="text-caption font-medium uppercase tracking-[0.04em] text-ai">Suggested next action</p>
        <p className="mt-0.5 flex items-start gap-1.5 text-body font-medium text-fg"><ArrowRight className="mt-1 size-4 shrink-0" aria-hidden />{s.next_action}</p>
        {s.next_action_reason && <p className="mt-0.5 text-small text-fg-secondary">{s.next_action_reason}</p>}
      </div>
    </div>
  );
}

function SummaryList({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div>
      <h3 className="mb-1.5 text-small font-semibold text-fg">{title}</h3>
      {items.length ? (
        <ul className="list-disc space-y-1 pl-5 text-small text-fg-secondary">
          {items.map((item, i) => <li key={i}>{item}</li>)}
        </ul>
      ) : <p className="text-small text-fg-muted">{empty}</p>}
    </div>
  );
}
