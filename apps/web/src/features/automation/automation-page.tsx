import { Activity, AlertTriangle, ArrowRight, Cpu, History, Workflow as WorkflowIcon } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge, Chip } from "@/components/system/badges";
import { KpiCard } from "@/components/system/data-display";
import { PageHeader } from "@/components/system/layout-blocks";
import { EmptyState, ErrorState } from "@/components/system/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/primitives";
import { formatNumber, formatPercent, formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useOverview, useWorkflows, type Workflow } from "./api";
import { ExecutionStatusBadge, TriggerSummary } from "./shared";
import { formatDuration } from "./format";

export default function AutomationPage() {
  const overview = useOverview();
  const workflows = useWorkflows();
  const o = overview.data;

  return (
    <>
      <PageHeader
        title="Automation"
        description="Deterministic Python workflows that react to business events and schedules. People still make every approval and financial decision."
        actions={<Button asChild><Link to="/automation/executions"><History /> Execution history</Link></Button>}
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="Executions (24 h)" loading={overview.isPending} value={o ? formatNumber(o.executions) : ""}
          hint={o ? `${o.succeeded} succeeded · ${o.skipped} skipped` : undefined} to="/automation/executions" />
        <KpiCard label="Success rate" loading={overview.isPending} value={o ? (o.success_rate === null ? "—" : formatPercent(o.success_rate)) : ""}
          hint={o ? `${o.failed} failed` : undefined} to="/automation/executions?status=failed" />
        <KpiCard label="In progress" loading={overview.isPending} value={o ? formatNumber(o.in_progress) : ""}
          hint={o ? `${o.queued_events} events queued · ${o.retry_scheduled} retrying` : undefined} />
        <WorkerCard loading={overview.isPending} online={o?.workers_online ?? 0} lastSeen={o?.workers[0]?.last_seen_at ?? null} />
      </div>

      <h2 className="mb-3 text-body font-semibold">Workflows</h2>
      {workflows.isPending ? (
        <div className="grid gap-4 lg:grid-cols-2">{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-48 rounded-[var(--radius-panel)]" />)}</div>
      ) : workflows.isError ? <ErrorState error={workflows.error} onRetry={() => void workflows.refetch()} /> : !workflows.data.length ? (
        <div className="rounded-[var(--radius-panel)] border border-border bg-surface">
          <EmptyState icon={<WorkflowIcon className="size-5" />} title="No workflows registered" description="Workflows are registered when the worker or the seed runs." />
        </div>
      ) : (
        <ul className="grid gap-4 lg:grid-cols-2">{workflows.data.map((w) => <WorkflowCard key={w.key} workflow={w} />)}</ul>
      )}
    </>
  );
}

function WorkerCard({ loading, online, lastSeen }: { loading: boolean; online: number; lastSeen: string | null }) {
  return (
    <div className={cn("rounded-[var(--radius-panel)] border bg-surface p-4", !loading && online === 0 ? "border-warning/40" : "border-border")}>
      <p className="flex items-center gap-1.5 text-small font-medium text-fg-secondary"><Cpu className="size-3.5" /> Workers</p>
      {loading ? <div className="mt-3 space-y-2"><Skeleton className="h-7 w-24" /><Skeleton className="h-3 w-32" /></div> : online > 0 ? (
        <div className="mt-3">
          <p className="flex items-center gap-2 text-h2 font-semibold tracking-[-0.02em]"><span className="size-2.5 rounded-full bg-success" aria-hidden />{online} online</p>
          <p className="mt-1 text-small text-fg-muted">Heartbeat {formatRelative(lastSeen)}</p>
        </div>
      ) : (
        <div className="mt-3">
          <p className="flex items-center gap-2 text-h3 font-semibold text-warning"><AlertTriangle className="size-4" /> No worker running</p>
          <p className="mt-1 text-small text-fg-muted">Events queue until a worker starts: <code className="text-caption">python -m app.automation.worker</code></p>
        </div>
      )}
    </div>
  );
}

function WorkflowCard({ workflow: w }: { workflow: Workflow }) {
  const s = w.stats;
  return (
    <li>
      <Link to={`/automation/workflows/${w.key}`}
        className="group flex h-full flex-col rounded-[var(--radius-panel)] border border-border bg-surface p-5 transition-colors hover:border-border-strong">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2"><Chip>{w.category}</Chip><code className="text-caption text-fg-muted">{w.key}</code></div>
            <h3 className="mt-2 text-lead font-semibold group-hover:text-brand">{w.name}</h3>
          </div>
          {w.is_enabled ? <Badge tone="success">Enabled</Badge> : <Badge tone="neutral">Disabled</Badge>}
        </div>
        <p className="mt-1 line-clamp-2 text-small text-fg-secondary">{w.description}</p>
        <div className="mt-3"><TriggerSummary workflow={w} /></div>
        <div className="mt-auto grid grid-cols-3 gap-3 border-t border-border-subtle pt-3 text-small">
          <div><p className="text-caption text-fg-muted">Last 24 h</p>
            <p className="tabular"><span className="text-success">{s.succeeded} ok</span>{s.failed ? <span className="text-danger"> · {s.failed} failed</span> : null}{s.skipped ? <span className="text-fg-muted"> · {s.skipped} skipped</span> : null}</p></div>
          <div><p className="text-caption text-fg-muted">Last run</p>
            {s.last_status ? <div className="flex items-center gap-1.5"><ExecutionStatusBadge status={s.last_status} /><span className="text-caption text-fg-muted">{formatRelative(s.last_finished_at)}</span></div> : <p className="text-fg-muted">Never</p>}</div>
          <div><p className="text-caption text-fg-muted">Avg. duration</p><p className="tabular">{formatDuration(s.avg_duration_ms)}</p></div>
        </div>
        <span className="mt-3 inline-flex items-center gap-1 text-small font-medium text-brand opacity-0 transition-opacity group-hover:opacity-100">
          <Activity className="size-3.5" /> Details <ArrowRight className="size-3.5" />
        </span>
      </Link>
    </li>
  );
}
