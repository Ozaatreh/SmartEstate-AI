import type { ColumnDef } from "@tanstack/react-table";
import { FileText, Plus } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { Badge, StatusBadge } from "@/components/system/badges";
import { PriorityBadge } from "@/components/system/business";
import { MoneyText } from "@/components/system/data-display";
import { DataTable } from "@/components/system/data-table";
import { PageHeader } from "@/components/system/layout-blocks";
import { EmptyState } from "@/components/system/states";
import { useListState } from "@/components/system/use-list-state";
import { Button } from "@/components/ui/button";
import { Skeleton, Tabs, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { useCan } from "@/features/auth/auth-context";
import { formatDate, formatMoney, formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useRequests, useRequestStats, type PurchaseRequest } from "./api";

const FILTERS = ["scope", "status"] as const;
const STATUS_CHIPS = [
  { key: "draft", label: "Draft" },
  { key: "sourcing", label: "Sourcing" },
  { key: "pending_approval", label: "In approval" },
  { key: "approved", label: "Approved" },
  { key: "rejected", label: "Rejected" },
  { key: "closed", label: "Closed" },
] as const;

export default function RequestsPage() {
  const canReadAll = useCan("procurement.requests.read_all");
  const canReadApprovals = useCan("approvals.requests.read_all");
  const canAll = canReadAll || canReadApprovals;
  const canCreate = useCan("procurement.requests.create");
  const state = useListState({ filterKeys: FILTERS, defaultSort: "-created_at" });
  const scope = state.filters.scope ?? (canAll ? "all" : "mine");
  const list = useRequests({ ...state.query, scope });
  const stats = useRequestStats(scope);
  const navigate = useNavigate();

  const columns: ColumnDef<PurchaseRequest, unknown>[] = [
    {
      id: "code", header: "Request", meta: { sortKey: "code", label: "Request" }, enableHiding: false,
      cell: ({ row: { original: r } }) => (
        <div className="min-w-0 max-w-md">
          <div className="flex items-center gap-2"><span className="tabular text-small text-fg-muted">{r.code}</span><PriorityBadge priority={r.priority} /></div>
          <p className="truncate font-medium">{r.title}</p>
        </div>
      ),
    },
    { id: "requester", header: "Requested by", meta: { label: "Requested by", className: "hidden lg:table-cell" }, cell: ({ row }) => row.original.requester.full_name },
    {
      id: "charge", header: "Charged to", meta: { label: "Charged to", className: "hidden xl:table-cell" },
      cell: ({ row: { original: r } }) => <div><p className="truncate">{r.project ? r.project.code : r.department.name}</p><p className="text-caption text-fg-muted">{r.category}</p></div>,
    },
    {
      id: "status", header: "Status", meta: { label: "Status" },
      cell: ({ row: { original: r } }) => (
        <div className="space-y-0.5">
          <div className="flex flex-wrap gap-1"><StatusBadge status={r.status} label={r.status === "pending_approval" ? "In approval" : undefined} />{r.over_budget && r.status !== "cancelled" && <Badge tone="danger" dot={false}>Over budget</Badge>}</div>
          {r.waiting_on && <p className="text-caption text-fg-muted">{r.waiting_on}</p>}
        </div>
      ),
    },
    { id: "estimated_total", header: "Amount", meta: { sortKey: "estimated_total", label: "Amount", align: "right" }, cell: ({ row }) => <MoneyText value={row.original.approved_total ?? row.original.estimated_total} decimals={2} /> },
    { id: "needed_by", header: "Needed by", meta: { sortKey: "needed_by", label: "Needed by", className: "hidden md:table-cell" }, cell: ({ row }) => <span className="tabular text-small text-fg-secondary">{formatDate(row.original.needed_by)}</span> },
    { id: "created_at", header: "Created", meta: { sortKey: "created_at", label: "Created", align: "right", className: "hidden 2xl:table-cell" }, cell: ({ row }) => <span className="text-small text-fg-secondary">{formatRelative(row.original.created_at)}</span> },
  ];

  const s = stats.data;
  return (
    <>
      <PageHeader title="Purchase requests" description="From request to approved commitment: sourcing, quotations, approvals and budget checks."
        actions={canCreate && <Button asChild variant="primary"><Link to="/procurement/requests/new"><Plus /> New request</Link></Button>} />

      {canAll && (
        <Tabs value={scope} onValueChange={(v) => state.setFilter("scope", v === "all" ? undefined : v)} className="mb-4">
          <TabsList><TabsTrigger value="all">All requests</TabsTrigger><TabsTrigger value="mine">My requests</TabsTrigger></TabsList>
        </Tabs>
      )}

      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {STATUS_CHIPS.map((c) => {
          const active = state.filters.status === c.key;
          const count = s?.[c.key];
          return (
            <button key={c.key} type="button" onClick={() => state.setFilter("status", active ? undefined : c.key)} aria-pressed={active}
              className={cn("rounded-[var(--radius-panel)] border bg-surface px-3 py-2.5 text-left transition-colors hover:border-border-strong",
                active ? "border-brand shadow-[inset_0_0_0_1px_var(--brand)]" : "border-border")}>
              <p className="text-small text-fg-secondary">{c.label}</p>
              {stats.isPending ? <Skeleton className="mt-1 h-6 w-10" /> : <p className="tabular text-h3 font-semibold">{count ?? 0}</p>}
              {c.key === "pending_approval" && s && <p className="tabular truncate text-caption text-fg-muted">{formatMoney(s.in_approval_value)}</p>}
              {c.key === "approved" && s && <p className="tabular truncate text-caption text-fg-muted">{formatMoney(s.approved_value)}</p>}
            </button>
          );
        })}
      </div>

      <DataTable
        ariaLabel="Purchase requests"
        columns={columns}
        page={list.data}
        isLoading={list.isPending}
        isFetching={list.isFetching}
        error={list.error}
        onRetry={() => void list.refetch()}
        state={state}
        searchPlaceholder="Search code, title or requester"
        getRowId={(r) => r.id}
        onRowClick={(r) => navigate(`/procurement/requests/${r.id}`)}
        empty={<EmptyState icon={<FileText className="size-5" />} title="No purchase requests yet" description="Create a request to start the purchasing flow."
          action={canCreate && <Button asChild size="sm" variant="primary"><Link to="/procurement/requests/new"><Plus /> New request</Link></Button>} />}
        mobileRow={(r) => (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between gap-2"><span className="tabular text-small text-fg-muted">{r.code}</span><MoneyText value={r.approved_total ?? r.estimated_total} className="font-medium" /></div>
            <p className="font-medium">{r.title}</p>
            <div className="flex flex-wrap items-center gap-1.5"><StatusBadge status={r.status} label={r.status === "pending_approval" ? "In approval" : undefined} />{r.over_budget && <Badge tone="danger" dot={false}>Over budget</Badge>}<span className="text-caption text-fg-muted">{r.requester.full_name}</span></div>
          </div>
        )}
      />
    </>
  );
}
