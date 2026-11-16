import { AlertTriangle, ArrowUpRight, Ban, Check, ChevronRight, Circle, CircleDashed, Lightbulb, Loader2, RotateCw, X } from "lucide-react";
import * as React from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Badge } from "@/components/system/badges";
import { ConfirmDialog } from "@/components/system/forms";
import { DescriptionList, Panel } from "@/components/system/layout-blocks";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/system/states";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api-client";
import { formatDateTime, formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useExecution, useExecutionAction, type ExecutionDetail, type LogEntry, type StepDef, type StepRun } from "./api";
import { ExecutionStatusBadge, TriggerLabel } from "./shared";
import { entityLink, formatDuration } from "./format";

export default function ExecutionDetailPage() {
  const { id } = useParams();
  const q = useExecution(id);
  if (q.isPending) return <div className="rounded-[var(--radius-panel)] border border-border bg-surface"><ListSkeleton rows={6} /></div>;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} className="min-h-[50vh]" />;
  return <Detail e={q.data} />;
}

function Detail({ e }: { e: ExecutionDetail }) {
  const act = useExecutionAction(e.id);
  const [confirm, setConfirm] = React.useState<"retry" | "cancel" | null>(null);
  const link = entityLink(e.entity_type, e.entity_id);
  const live = e.status === "pending" || e.status === "running";

  const run = (a: "retry" | "cancel") => act.mutate(a, {
    onSuccess: () => { toast.success(a === "retry" ? "Retry queued" : "Execution cancelled", { description: a === "retry" ? "Completed steps won't run again." : undefined }); setConfirm(null); },
    onError: (err) => { toast.error(err instanceof ApiError ? err.message : "Action failed"); setConfirm(null); },
  });

  return (
    <>
      <Link to="/automation/executions" className="mb-3 inline-flex items-center gap-1 text-small text-fg-muted hover:text-fg">← Execution history</Link>
      <header className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <ExecutionStatusBadge status={e.status} attempt={e.attempt} maxAttempts={e.max_attempts} />
            {live && <span className="inline-flex items-center gap-1 text-caption text-fg-muted"><Loader2 className="size-3 animate-spin" /> Live</span>}
            <code className="break-all text-caption text-fg-muted">{e.id}</code>
          </div>
          <h1 className="mt-1 text-h2 font-semibold tracking-[-0.015em]">
            <Link className="hover:text-brand" to={`/automation/workflows/${e.workflow_key}`}>{e.workflow_name}</Link>
            {e.entity_label && <span className="text-fg-muted"> · {e.entity_label}</span>}
          </h1>
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-small text-fg-secondary">
            <TriggerLabel execution={e} />
            {link && <Link to={link} className="inline-flex items-center gap-0.5 font-medium text-brand hover:underline">Open {e.entity_type?.replace("_", " ")}<ArrowUpRight className="size-3.5" /></Link>}
            <span>Created {formatRelative(e.created_at)}</span>
          </div>
        </div>
        <div className="flex gap-2">
          {e.allowed_actions.includes("cancel") && <Button onClick={() => setConfirm("cancel")}><Ban /> Cancel</Button>}
          {e.allowed_actions.includes("retry") && <Button variant="primary" onClick={() => setConfirm("retry")}><RotateCw /> Retry</Button>}
        </div>
      </header>

      {e.error_message && e.status !== "succeeded" && (
        <div role="alert" className={cn("mb-6 flex items-start gap-3 rounded-[var(--radius-panel)] border px-4 py-3",
          e.status === "failed" ? "border-danger/25 bg-danger-subtle text-danger" : "border-warning/30 bg-warning-subtle text-warning")}>
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <div className="text-body">
            <p className="font-medium">{e.status === "failed" ? "Execution failed" : `Attempt ${e.attempt} failed — retrying ${formatRelative(e.available_at).replace(" ago", "")}`}</p>
            <p className="mt-0.5 text-small"><code>{e.error_code}</code> · {e.error_message}</p>
          </div>
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-4">
          <Panel title="Steps" description="Each step commits on its own; on retry, completed steps are reused.">
            <StepsTimeline planned={e.planned_steps} runs={e.steps} status={e.status} />
          </Panel>
          <Panel title="Logs" description={`${e.logs.length} entries`}>
            {e.logs.length ? <LogList logs={e.logs} /> : <EmptyState title="No log entries yet" description="Logs appear once a worker starts this execution." />}
          </Panel>
        </div>
        <aside className="min-w-0 space-y-4">
          <Panel title="Execution">
            <DescriptionList items={[
              { label: "Attempts", value: <span className="tabular">{e.attempt} of {e.max_attempts}</span> },
              { label: "Started", value: formatDateTime(e.started_at) },
              { label: "Finished", value: formatDateTime(e.finished_at) },
              { label: "Duration", value: <span className="tabular">{formatDuration(e.duration_ms)}</span> },
              { label: e.status === "pending" ? "Runs at" : "Available at", value: formatDateTime(e.available_at) },
              { label: "Worker", value: e.lease_owner ? <code className="text-caption">{e.lease_owner}</code> : "—" },
              { label: "Requested by", value: e.triggered_by ?? (e.trigger_type === "manual" ? "—" : "System") },
            ]} />
          </Panel>
          <Panel title="Trigger payload"><Json value={e.context} /></Panel>
          {e.result && <Panel title="Result"><Json value={e.result} /></Panel>}
        </aside>
      </div>

      <ConfirmDialog open={confirm !== null} onOpenChange={(o) => !o && setConfirm(null)} loading={act.isPending} tone={confirm === "cancel" ? "danger" : "primary"}
        title={confirm === "retry" ? "Retry this execution?" : "Cancel this execution?"} confirmLabel={confirm === "retry" ? "Queue retry" : "Cancel execution"}
        description={confirm === "retry" ? "It gets one more attempt. Steps that already succeeded are not repeated, so nothing happens twice." : "It won't run. You can retry it later."}
        onConfirm={() => confirm && run(confirm)} />
    </>
  );
}

const STEP_LOOK = {
  succeeded: { icon: <Check className="size-3.5" />, cls: "border-success bg-success text-white" },
  failed: { icon: <X className="size-3.5" />, cls: "border-danger bg-danger text-white" },
  skipped: { icon: <CircleDashed className="size-3.5" />, cls: "border-border bg-surface-sunken text-fg-muted" },
  running: { icon: <Loader2 className="size-3.5 animate-spin" />, cls: "border-info bg-info-subtle text-info" },
  waiting: { icon: <Circle className="size-3" />, cls: "border-border-strong bg-surface text-fg-muted" },
} as const;

function StepsTimeline({ planned, runs, status }: { planned: StepDef[]; runs: StepRun[]; status: string }) {
  return (
    <ol className="p-4">
      {planned.map((p, i) => {
        const attempts = runs.filter((r) => r.step_key === p.key);
        const last = attempts.at(-1);
        const state = last?.status ?? (status === "running" && (i === 0 || runs.some((r) => r.step_key === planned[i - 1]?.key && r.status !== "failed")) ? "running" : "waiting");
        const look = STEP_LOOK[state as keyof typeof STEP_LOOK];
        return (
          <li key={p.key} className="relative flex gap-3 pb-5 last:pb-0">
            {i < planned.length - 1 && <span aria-hidden className="absolute left-[13px] top-7 h-[calc(100%-24px)] w-px bg-border" />}
            <span className={cn("relative z-10 grid size-7 shrink-0 place-items-center rounded-full border", look.cls)}>{look.icon}</span>
            <div className="min-w-0 flex-1 pt-0.5">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-medium">{p.label}</p>
                {p.advisory && <Badge tone="ai" dot={false}><Lightbulb className="size-3" /> Advisory</Badge>}
                {last && <span className="tabular text-caption text-fg-muted">{formatDuration(last.duration_ms)}</span>}
                {attempts.length > 1 && <span className="text-caption text-fg-muted">{attempts.length} attempts</span>}
              </div>
              <p className="text-small text-fg-muted"><code>{p.action}</code>{state === "skipped" && last?.output?.reason ? ` · skipped: ${String(last.output.reason)}` : ""}</p>
              {attempts.filter((a) => a.status === "failed").map((a) => (
                <p key={a.id} className="mt-1 text-small text-danger">Attempt {a.attempt}: <code>{a.error_code}</code> {a.error_message}</p>
              ))}
              {last && (last.input || (last.output && state !== "skipped")) && (
                <details className="group mt-2 rounded-[var(--radius-control)] border border-border-subtle">
                  <summary className="flex cursor-pointer list-none items-center gap-1 px-2.5 py-1.5 text-small text-fg-secondary hover:text-fg">
                    <ChevronRight className="size-3.5 transition-transform group-open:rotate-90" /> Input &amp; output
                  </summary>
                  <div className="grid gap-2 border-t border-border-subtle p-2.5 md:grid-cols-2">
                    <div><p className="mb-1 text-caption font-medium uppercase tracking-[0.04em] text-fg-muted">Input</p><Json value={last.input} bare /></div>
                    <div><p className="mb-1 text-caption font-medium uppercase tracking-[0.04em] text-fg-muted">Output</p><Json value={last.output} bare /></div>
                  </div>
                </details>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

const LEVEL_TONE = { debug: "text-fg-muted", info: "text-fg-secondary", warning: "text-warning", error: "text-danger" } as const;

function LogList({ logs }: { logs: LogEntry[] }) {
  return (
    <ol className="max-h-[420px] divide-y divide-border-subtle overflow-auto font-mono text-[12.5px]">
      {logs.map((l) => (
        <li key={l.seq} className="flex flex-wrap gap-x-3 gap-y-0.5 px-4 py-1.5 sm:flex-nowrap">
          <span className="tabular shrink-0 text-fg-muted" title={formatDateTime(l.created_at)}>{new Date(l.created_at).toLocaleTimeString("en-GB")}</span>
          <span className={cn("w-14 shrink-0 uppercase", LEVEL_TONE[l.level])}>{l.level}</span>
          <span className="shrink-0 text-fg-muted">#{l.attempt}</span>
          {l.step_key && <span className="shrink-0 text-brand">{l.step_key}</span>}
          <span className={cn("min-w-0 break-words", l.level === "error" ? "text-danger" : "text-fg")}>{l.message}</span>
        </li>
      ))}
    </ol>
  );
}

function Json({ value, bare }: { value: unknown; bare?: boolean }) {
  if (value === null || value === undefined) return <p className={cn("text-small text-fg-muted", !bare && "p-4")}>—</p>;
  return <pre className={cn("max-h-72 overflow-auto rounded-[var(--radius-control)] bg-surface-sunken p-3 text-caption leading-5", !bare && "m-4")}>{JSON.stringify(value, null, 2)}</pre>;
}

