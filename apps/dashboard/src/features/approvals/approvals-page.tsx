import type { ColumnDef } from "@tanstack/react-table";
import { Inbox } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Badge, StatusBadge } from "@/components/system/badges";
import { MoneyText } from "@/components/system/data-display";
import { DataTable } from "@/components/system/data-table";
import { PageHeader } from "@/components/system/layout-blocks";
import { EmptyState } from "@/components/system/states";
import { useListState } from "@/components/system/use-list-state";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { useCan } from "@/features/auth/auth-context";
import { formatDateTime, formatRelative } from "@/lib/format";
import { isMonetary, useApprovals, usePendingApprovals, type Approval } from "./api";

const FILTERS = ["box"] as const;
const EMPTY: Record<string, { title: string; description: string }> = {
  pending: { title: "You're all caught up", description: "Requests waiting for your decision appear here." },
  decided: { title: "No decisions yet", description: "Requests you approve or reject are kept here for reference." },
  mine: { title: "Nothing submitted for approval", description: "Your requests appear here once procurement sends them for approval." },
  all: { title: "No approval requests", description: "Approval requests across the company appear here." },
};

export default function ApprovalsPage() {
  const state = useListState({ filterKeys: FILTERS });
  const box = state.filters.box ?? "pending";
  const list = useApprovals({ ...state.query, box, sort: state.sort ?? (box === "pending" ? "created_at" : "-created_at") });
  const pending = usePendingApprovals();
  const canAll = useCan("approvals.requests.read_all");
  const navigate = useNavigate();

  const columns: ColumnDef<Approval, unknown>[] = [
    {
      id: "code", header: "Request", meta: { sortKey: "code", label: "Request" }, enableHiding: false,
      cell: ({ row: { original: a } }) => (
        <div className="min-w-0 max-w-md">
          <div className="flex items-center gap-2"><span className="tabular text-small text-fg-muted">{a.entity_code}</span>{a.flags.over_budget && <Badge tone="danger" dot={false}>Over budget</Badge>}</div>
          <p className="truncate font-medium">{a.title}</p>
        </div>
      ),
    },
    { id: "requester", header: "Requested by", meta: { label: "Requested by", className: "hidden lg:table-cell" }, cell: ({ row }) => row.original.requester.full_name },
    {
      id: "step", header: box === "pending" ? "Your step" : "Status", meta: { label: "Step" },
      cell: ({ row: { original: a } }) => a.status === "pending"
        ? <div><StatusBadge status="pending" label={a.current_step_label ?? "Pending"} />{box !== "pending" && a.waiting_on && <p className="mt-0.5 text-caption text-fg-muted">{a.waiting_on}</p>}</div>
        : <StatusBadge status={a.status} />,
    },
    { id: "amount", header: "Amount", meta: { sortKey: "amount", label: "Amount", align: "right" }, cell: ({ row }) => isMonetary(row.original) ? <MoneyText value={row.original.amount} decimals={2} className="font-medium" /> : <span className="text-small text-fg-muted">{row.original.entity_label}</span> },
    {
      id: "created_at", header: box === "pending" ? "Waiting" : "Submitted", meta: { sortKey: "created_at", label: "Submitted", align: "right", className: "hidden md:table-cell" },
      cell: ({ row }) => <span className="text-small text-fg-secondary" title={formatDateTime(row.original.created_at)}>{formatRelative(row.original.created_at)}</span>,
    },
  ];

  return (
    <>
      <PageHeader title="Approvals" description="Decide on requests routed to you. Every decision is recorded with your comment." />
      <Tabs value={box} onValueChange={(v) => state.setFilter("box", v === "pending" ? undefined : v)} className="mb-4">
        <TabsList>
          <TabsTrigger value="pending">Waiting for me {pending.data?.pending ? <span className="tabular ml-1 rounded-full bg-brand-subtle px-1.5 text-caption font-semibold text-brand">{pending.data.pending}</span> : null}</TabsTrigger>
          <TabsTrigger value="decided">Decided by me</TabsTrigger>
          <TabsTrigger value="mine">My requests</TabsTrigger>
          {canAll && <TabsTrigger value="all">All</TabsTrigger>}
        </TabsList>
      </Tabs>
      <DataTable
        ariaLabel="Approval requests"
        columns={columns}
        page={list.data}
        isLoading={list.isPending}
        isFetching={list.isFetching}
        error={list.error}
        onRetry={() => void list.refetch()}
        state={state}
        searchPlaceholder="Search code, title or requester"
        getRowId={(a) => a.id}
        onRowClick={(a) => navigate(a.link)}
        empty={<EmptyState icon={<Inbox className="size-5" />} {...EMPTY[box]} />}
        mobileRow={(a) => (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between gap-2"><span className="tabular text-small text-fg-muted">{a.entity_code}</span>{isMonetary(a) ? <MoneyText value={a.amount} className="font-medium" /> : <span className="text-caption text-fg-muted">{a.entity_label}</span>}</div>
            <p className="font-medium">{a.title}</p>
            <div className="flex flex-wrap items-center gap-1.5">
              {a.status === "pending" ? <StatusBadge status="pending" label={a.current_step_label ?? "Pending"} /> : <StatusBadge status={a.status} />}
              <span className="text-caption text-fg-muted">{a.requester.full_name} · {formatRelative(a.created_at)}</span>
            </div>
          </div>
        )}
      />
    </>
  );
}
