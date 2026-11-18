import type { ColumnDef } from "@tanstack/react-table";
import { ClipboardCheck } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { Badge, StatusBadge } from "@/components/system/badges";
import { MoneyText } from "@/components/system/data-display";
import { DataTable } from "@/components/system/data-table";
import { PageHeader } from "@/components/system/layout-blocks";
import { EmptyState } from "@/components/system/states";
import { useListState } from "@/components/system/use-list-state";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { useCan } from "@/features/auth/auth-context";
import { formatDate, formatRelative } from "@/lib/format";
import { useOrders, type PurchaseOrder } from "./api";

const FILTERS = ["status"] as const;

export default function OrdersPage() {
  const canManage = useCan("procurement.orders.manage");
  const state = useListState({ filterKeys: FILTERS, defaultSort: "-created_at" });
  const list = useOrders({ ...state.query, status: state.filters.status });
  const navigate = useNavigate();

  const columns: ColumnDef<PurchaseOrder, unknown>[] = [
    {
      id: "code", header: "Order", meta: { sortKey: "code", label: "Order" }, enableHiding: false,
      cell: ({ row: { original: o } }) => (
        <div className="min-w-0 max-w-md">
          <span className="tabular text-small text-fg-muted">{o.code}</span>
          <p className="truncate font-medium">{o.supplier.name}</p>
        </div>
      ),
    },
    {
      id: "request", header: "Purchase request", meta: { label: "Purchase request", className: "hidden md:table-cell" },
      cell: ({ row: { original: o } }) => <div className="min-w-0"><p className="tabular text-small text-fg-muted">{o.request_code}</p><p className="truncate">{o.request_title}</p></div>,
    },
    {
      id: "status", header: "Status", meta: { label: "Status" },
      cell: ({ row: { original: o } }) => (
        <div className="flex flex-wrap gap-1">
          <StatusBadge status={o.status} />
          {o.status === "cancelled" && <Badge tone={o.budget_released ? "neutral" : "info"} dot={false}>{o.budget_released ? "Budget released" : "Budget kept"}</Badge>}
        </div>
      ),
    },
    { id: "total_amount", header: "Amount", meta: { sortKey: "total_amount", label: "Amount", align: "right" }, cell: ({ row }) => <MoneyText value={row.original.total_amount} decimals={2} /> },
    { id: "delivery", header: "Delivery", meta: { label: "Delivery", className: "hidden lg:table-cell" }, cell: ({ row }) => <span className="tabular text-small text-fg-secondary">{formatDate(row.original.expected_delivery_date)}</span> },
    { id: "created_at", header: "Created", meta: { sortKey: "created_at", label: "Created", align: "right", className: "hidden xl:table-cell" }, cell: ({ row }) => <span className="text-small text-fg-secondary">{formatRelative(row.original.created_at)}</span> },
  ];

  const status = state.filters.status ?? "all";
  return (
    <>
      <PageHeader title="Purchase orders" description="Orders issued to suppliers from fully approved purchase requests. The budget is committed once, at request approval." />
      <Tabs value={status} onValueChange={(v) => state.setFilter("status", v === "all" ? undefined : v)} className="mb-4">
        <TabsList>
          <TabsTrigger value="all">All</TabsTrigger>
          <TabsTrigger value="draft">Draft</TabsTrigger>
          <TabsTrigger value="issued">Issued</TabsTrigger>
          <TabsTrigger value="cancelled">Cancelled</TabsTrigger>
        </TabsList>
      </Tabs>
      <DataTable
        ariaLabel="Purchase orders"
        columns={columns}
        page={list.data}
        isLoading={list.isPending}
        isFetching={list.isFetching}
        error={list.error}
        onRetry={() => void list.refetch()}
        state={state}
        searchPlaceholder="Search order, request code or title"
        getRowId={(o) => o.id}
        onRowClick={(o) => navigate(`/procurement/orders/${o.id}`)}
        empty={<EmptyState icon={<ClipboardCheck className="size-5" />} title={status === "all" ? "No purchase orders yet" : `No ${status} orders`}
          description={canManage ? "Open a fully approved purchase request and create its order." : "Orders appear here once procurement creates them for approved requests."}
          action={canManage && <Button asChild size="sm"><Link to="/procurement/requests?status=approved">Approved requests</Link></Button>} />}
        mobileRow={(o) => (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between gap-2"><span className="tabular text-small text-fg-muted">{o.code}</span><MoneyText value={o.total_amount} decimals={2} className="font-medium" /></div>
            <p className="font-medium">{o.supplier.name}</p>
            <div className="flex flex-wrap items-center gap-1.5"><StatusBadge status={o.status} /><span className="tabular text-caption text-fg-muted">{o.request_code}</span></div>
          </div>
        )}
      />
    </>
  );
}
