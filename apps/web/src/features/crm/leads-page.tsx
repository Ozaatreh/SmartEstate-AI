import type { ColumnDef } from "@tanstack/react-table";
import { AlarmClock, Contact, Plus } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { Badge, StatusBadge } from "@/components/system/badges";
import { DataTable } from "@/components/system/data-table";
import { PageHeader } from "@/components/system/layout-blocks";
import { EmptyState } from "@/components/system/states";
import { useListState } from "@/components/system/use-list-state";
import { Button } from "@/components/ui/button";
import { Skeleton, Tabs, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { useCan } from "@/features/auth/auth-context";
import { formatMoney, formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useLeadStats, useLeads, type Lead } from "./api";
import { STAGES, budgetLabel, stageLabel } from "./crm-logic";
import { NewLeadDialog } from "./lead-dialogs";
import { ScoreBadge } from "./shared";

const FILTERS = ["scope", "stage", "overdue"] as const;


export default function LeadsPage() {
  const canAll = useCan("crm.leads.read_all");
  const canCreate = useCan("crm.leads.create");
  const state = useListState({ filterKeys: FILTERS, defaultSort: "-created_at" });
  const scope = state.filters.scope ?? (canAll ? "all" : "mine");
  const list = useLeads({ ...state.query, scope });
  const stats = useLeadStats(scope);
  const navigate = useNavigate();
  const [creating, setCreating] = React.useState(false);

  const columns: ColumnDef<Lead, unknown>[] = [
    {
      id: "full_name", header: "Lead", meta: { sortKey: "full_name", label: "Lead" }, enableHiding: false,
      cell: ({ row: { original: l } }) => (
        <div className="min-w-0 max-w-xs">
          <span className="tabular text-small text-fg-muted">{l.code}</span>
          <p className="truncate font-medium">{l.full_name}</p>
        </div>
      ),
    },
    { id: "stage", header: "Stage", meta: { label: "Stage" }, cell: ({ row }) => <StatusBadge status={row.original.stage} label={stageLabel(row.original.stage)} /> },
    { id: "score", header: "Score", meta: { sortKey: "score", label: "Score" }, cell: ({ row }) => <ScoreBadge lead={row.original} /> },
    { id: "owner", header: "Owner", meta: { label: "Owner", className: "hidden lg:table-cell" }, cell: ({ row }) => row.original.owner?.full_name ?? <span className="text-fg-muted">Unassigned</span> },
    {
      id: "budget", header: "Budget", meta: { label: "Budget", className: "hidden xl:table-cell" },
      cell: ({ row: { original: l } }) => <span className="tabular text-small">{budgetLabel(l.budget_min, l.budget_max, (v) => formatMoney(v))}</span>,
    },
    {
      id: "next_follow_up_at", header: "Follow-up", meta: { sortKey: "next_follow_up_at", label: "Follow-up", className: "hidden md:table-cell" },
      cell: ({ row: { original: l } }) => l.next_follow_up_at
        ? <span className={cn("inline-flex items-center gap-1 text-small", l.follow_up_overdue ? "font-medium text-danger" : "text-fg-secondary")}>
            {l.follow_up_overdue && <AlarmClock className="size-3.5" aria-hidden />}{l.follow_up_overdue ? "Overdue · " : ""}{formatRelative(l.next_follow_up_at)}
          </span>
        : <span className="text-small text-fg-muted">—</span>,
    },
    { id: "created_at", header: "Created", meta: { sortKey: "created_at", label: "Created", align: "right", className: "hidden 2xl:table-cell" }, cell: ({ row }) => <span className="text-small text-fg-secondary">{formatRelative(row.original.created_at)}</span> },
  ];

  const s = stats.data;
  const chips: { key: string; label: string; count?: number; filter: () => void; active: boolean; tone?: string }[] = [
    ...STAGES.map((st) => ({
      key: st.key, label: st.label, count: s?.[st.key], active: state.filters.stage === st.key && !state.filters.overdue,
      filter: () => { state.setFilter("overdue", undefined); state.setFilter("stage", state.filters.stage === st.key ? undefined : st.key); },
    })),
    { key: "overdue", label: "Overdue", count: s?.overdue, active: state.filters.overdue === "true", tone: "danger",
      filter: () => state.setFilter("overdue", state.filters.overdue === "true" ? undefined : "true") },
  ];

  return (
    <>
      <PageHeader title="Leads" description="Every buyer enquiry, scored by transparent rules and assigned round-robin. Overdue follow-ups escalate automatically."
        actions={canCreate && <Button variant="primary" onClick={() => setCreating(true)}><Plus /> New lead</Button>} />

      {canAll && (
        <Tabs value={scope} onValueChange={(v) => state.setFilter("scope", v === "all" ? undefined : v)} className="mb-4">
          <TabsList><TabsTrigger value="all">All leads</TabsTrigger><TabsTrigger value="mine">My leads</TabsTrigger></TabsList>
        </Tabs>
      )}

      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-8" role="group" aria-label="Filter by stage">
        {chips.map((c) => (
          <button key={c.key} type="button" onClick={c.filter} aria-pressed={c.active}
            className={cn("rounded-[var(--radius-panel)] border bg-surface px-3 py-2 text-left transition-colors hover:border-border-strong",
              c.active ? "border-brand shadow-[inset_0_0_0_1px_var(--brand)]" : "border-border")}>
            <p className={cn("text-small", c.tone === "danger" && (c.count ?? 0) > 0 ? "text-danger" : "text-fg-secondary")}>{c.label}</p>
            {stats.isPending ? <Skeleton className="mt-1 h-6 w-8" /> : <p className="tabular text-h3 font-semibold">{c.count ?? 0}</p>}
          </button>
        ))}
      </div>

      <DataTable
        ariaLabel="Leads"
        columns={columns}
        page={list.data}
        isLoading={list.isPending}
        isFetching={list.isFetching}
        error={list.error}
        onRetry={() => void list.refetch()}
        state={state}
        searchPlaceholder="Search name, code, phone or email"
        getRowId={(l) => l.id}
        onRowClick={(l) => navigate(`/crm/leads/${l.id}`)}
        empty={<EmptyState icon={<Contact className="size-5" />} title={scope === "mine" ? "No leads assigned to you" : "No leads yet"}
          description="New leads are scored and assigned automatically as they arrive."
          action={canCreate && <Button size="sm" variant="primary" onClick={() => setCreating(true)}><Plus /> New lead</Button>} />}
        mobileRow={(l) => (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between gap-2"><span className="tabular text-small text-fg-muted">{l.code}</span><ScoreBadge lead={l} /></div>
            <p className="font-medium">{l.full_name}</p>
            <div className="flex flex-wrap items-center gap-1.5">
              <StatusBadge status={l.stage} label={stageLabel(l.stage)} />
              {l.follow_up_overdue && <Badge tone="danger" dot={false}>Follow-up overdue</Badge>}
              <span className="text-caption text-fg-muted">{l.owner?.full_name ?? "Unassigned"}</span>
            </div>
          </div>
        )}
      />
      {creating && <NewLeadDialog onClose={() => setCreating(false)} />}
    </>
  );
}
