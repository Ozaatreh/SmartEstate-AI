import { CalendarClock, Hand, Zap } from "lucide-react";
import { Badge, StatusBadge } from "@/components/system/badges";
import { humanize } from "@/lib/status";
import type { Execution, ExecutionStatus, Workflow } from "./api";

export function ExecutionStatusBadge({ status, attempt, maxAttempts }: { status: ExecutionStatus; attempt?: number; maxAttempts?: number }) {
  if (status === "pending" && attempt && attempt > 0) {
    return <Badge tone="warning">Retry {attempt + 1}/{maxAttempts}</Badge>;
  }
  return <StatusBadge status={status === "pending" ? "waiting" : status} label={status === "pending" ? "Queued" : undefined} />;
}

export function TriggerLabel({ execution }: { execution: Pick<Execution, "trigger_type" | "event_type"> }) {
  const Icon = execution.trigger_type === "event" ? Zap : execution.trigger_type === "schedule" ? CalendarClock : Hand;
  return (
    <span className="inline-flex items-center gap-1.5 text-small text-fg-secondary">
      <Icon className="size-3.5 text-fg-muted" aria-hidden />
      {execution.trigger_type === "event" ? <code className="text-caption">{execution.event_type}</code> : humanize(execution.trigger_type)}
    </span>
  );
}

export function TriggerSummary({ workflow }: { workflow: Pick<Workflow, "event_types" | "schedule_minutes"> }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {workflow.event_types.map((e) => (
        <span key={e} className="inline-flex h-6 items-center gap-1 rounded-[var(--radius-control)] bg-surface-sunken px-2 text-caption text-fg-secondary">
          <Zap className="size-3" aria-hidden /><code>{e}</code>
        </span>
      ))}
      {workflow.schedule_minutes && (
        <span className="inline-flex h-6 items-center gap-1 rounded-[var(--radius-control)] bg-surface-sunken px-2 text-caption text-fg-secondary">
          <CalendarClock className="size-3" aria-hidden />Every {workflow.schedule_minutes} min
        </span>
      )}
    </div>
  );
}
