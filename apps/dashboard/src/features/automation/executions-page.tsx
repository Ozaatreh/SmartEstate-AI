import type { ColumnDef } from "@tanstack/react-table";
import { History } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { DataTable } from "@/components/system/data-table";
import { PageHeader } from "@/components/system/layout-blocks";
import { EmptyState } from "@/components/system/states";
import { useListState } from "@/components/system/use-list-state";
import { Select } from "@/components/ui/menu";
import { formatDateTime, formatRelative } from "@/lib/format";
import { useExecutions, useWorkflows, type Execution } from "./api";
import { ExecutionStatusBadge, TriggerLabel } from "./shared";
import { formatDuration } from "./format";

const FILTERS = ["workflow_key", "status", "trigger_type"] as const;
const STATUSES = [
  { value: "all", label: "Any status" }, { value: "running", label: "Running" }, { value: "pending", label: "Queued" },
  { value: "retrying", label: "Retrying" }, { value: "succeeded", label: "Succeeded" }, { value: "failed", label: "Failed" },
  { value: "skipped", label: "Skipped" }, { value: "cancelled", label: "Cancelled" },
];

export default function ExecutionsPage() {
  return (
    <>
      <PageHeader breadcrumbs={[{ label: "Automation", to: "/automation" }, { label: "Executions" }]} title="Execution history"
        description="Every workflow run with its trigger, attempts, duration and outcome. Open a run for step details and logs." />
      <ExecutionsTable />
    </>
  );
}

export function ExecutionsTable({ fixedWorkflow }: { fixedWorkflow?: string }) {
  const state = useListState({ filterKeys: FILTERS, defaultSort: "-created_at" });
  const workflows = useWorkflows();
  const list = useExecutions({ ...state.query, workflow_key: fixedWorkflow ?? state.filters.workflow_key });
  const navigate = useNavigate();

  const columns: ColumnDef<Execution, unknown>[] = [
    {
      id: "workflow", header: "Workflow", meta: { label: "Workflow" }, enableHiding: false,
      cell: ({ row: { original: e } }) => (
        <div className="min-w-0">
          <p className="truncate font-medium">{e.workflow_name}</p>
          <p className="truncate text-caption text-fg-muted">{e.entity_label ? `${e.entity_label} · ` : ""}<span className="tabular">{e.id.slice(0, 8)}</span></p>
        </div>
      ),
    },
    { id: "trigger", header: "Trigger", meta: { label: "Trigger", className: "hidden lg:table-cell" }, cell: ({ row }) => <TriggerLabel execution={row.original} /> },
    {
      id: "status", header: "Status", meta: { sortKey: "status", label: "Status" },
      cell: ({ row: { original: e } }) => (
        <div className="space-y-0.5">
          <ExecutionStatusBadge status={e.status} attempt={e.attempt} maxAttempts={e.max_attempts} />
          {e.error_message && e.status !== "succeeded" && <p className="max-w-xs truncate text-caption text-danger" title={e.error_message}>{e.error_message}</p>}
        </div>
      ),
    },
    { id: "attempts", header: "Attempts", meta: { label: "Attempts", align: "right", className: "hidden md:table-cell" }, cell: ({ row }) => <span className="tabular text-small">{row.original.attempt}/{row.original.max_attempts}</span> },
    { id: "duration_ms", header: "Duration", meta: { sortKey: "duration_ms", label: "Duration", align: "right", className: "hidden md:table-cell" }, cell: ({ row }) => <span className="tabular text-small">{formatDuration(row.original.duration_ms)}</span> },
    {
      id: "created_at", header: "Created", meta: { sortKey: "created_at", label: "Created", align: "right" },
      cell: ({ row }) => <span className="text-small text-fg-secondary" title={formatDateTime(row.original.created_at)}>{formatRelative(row.original.created_at)}</span>,
    },
  ];

  return (
    <DataTable
      ariaLabel="Workflow executions"
      columns={columns}
      page={list.data}
      isLoading={list.isPending}
      isFetching={list.isFetching}
      error={list.error}
      onRetry={() => void list.refetch()}
      state={state}
      searchPlaceholder="Search document code, event or error"
      getRowId={(e) => e.id}
      onRowClick={(e) => navigate(`/automation/executions/${e.id}`)}
      filters={<>
        {!fixedWorkflow && (
          <Select aria-label="Workflow" className="h-8 w-52" value={state.filters.workflow_key ?? "all"} onValueChange={(v) => state.setFilter("workflow_key", v === "all" ? undefined : v)}
            options={[{ value: "all", label: "All workflows" }, ...(workflows.data ?? []).map((w) => ({ value: w.key, label: w.name }))]} />
        )}
        <Select aria-label="Status" className="h-8 w-36" value={state.filters.status ?? "all"} onValueChange={(v) => state.setFilter("status", v === "all" ? undefined : v)} options={STATUSES} />
        <Select aria-label="Trigger" className="h-8 w-32" value={state.filters.trigger_type ?? "all"} onValueChange={(v) => state.setFilter("trigger_type", v === "all" ? undefined : v)}
          options={[{ value: "all", label: "Any trigger" }, { value: "event", label: "Event" }, { value: "schedule", label: "Schedule" }, { value: "manual", label: "Manual" }]} />
      </>}
      empty={<EmptyState icon={<History className="size-5" />} title="No executions yet" description="Runs appear here as soon as a business event or schedule triggers a workflow." />}
      mobileRow={(e) => (
        <div className="space-y-1">
          <div className="flex items-center justify-between gap-2"><p className="truncate font-medium">{e.workflow_name}</p><span className="text-caption text-fg-muted">{formatRelative(e.created_at)}</span></div>
          <div className="flex flex-wrap items-center gap-2"><ExecutionStatusBadge status={e.status} attempt={e.attempt} maxAttempts={e.max_attempts} />
            {e.entity_label && <span className="text-small text-fg-muted">{e.entity_label}</span>}</div>
        </div>
      )}
    />
  );
}
