import type { ColumnDef } from "@tanstack/react-table";
import { CalendarCheck } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { StatusBadge } from "@/components/system/badges";
import { MoneyText } from "@/components/system/data-display";
import { DataTable } from "@/components/system/data-table";
import { ConfirmDialog } from "@/components/system/forms";
import { PageHeader } from "@/components/system/layout-blocks";
import { EmptyState } from "@/components/system/states";
import { useListState } from "@/components/system/use-list-state";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { useCan } from "@/features/auth/auth-context";
import { ApiError } from "@/lib/api-client";
import { formatDateTime, formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useReservationMutations, useReservations, type Reservation } from "./api";
import { CancelReservationDialog } from "./reservation-dialogs";

const FILTERS = ["scope", "status"] as const;
const STATUSES = ["active", "converted", "cancelled", "expired"] as const;

export default function ReservationsPage() {
  const canAll = useCan("crm.leads.read_all");
  const state = useListState({ filterKeys: FILTERS, defaultSort: "-reserved_at" });
  const scope = state.filters.scope ?? (canAll ? "all" : "mine");
  const list = useReservations({ ...state.query, scope });
  const [acting, setActing] = React.useState<{ r: Reservation; mode: "cancel" | "convert" } | null>(null);

  const columns: ColumnDef<Reservation, unknown>[] = [
    {
      id: "code", header: "Reservation", meta: { sortKey: "code", label: "Reservation" }, enableHiding: false,
      cell: ({ row: { original: r } }) => (
        <div className="min-w-0">
          <p className="tabular font-medium">{r.code}</p>
          <Link to={`/realestate/units/${r.unit.id}`} className="text-small text-brand hover:underline" onClick={(e) => e.stopPropagation()}>{r.unit.code} · {r.unit.name}</Link>
        </div>
      ),
    },
    {
      id: "lead", header: "Lead", meta: { label: "Lead" },
      cell: ({ row: { original: r } }) => (
        <div className="min-w-0">
          <Link to={`/crm/leads/${r.lead.id}`} className="font-medium hover:underline" onClick={(e) => e.stopPropagation()}>{r.lead.name}</Link>
          <p className="text-caption text-fg-muted">{r.lead.code} · {r.lead_owner?.full_name ?? "Unassigned"}</p>
        </div>
      ),
    },
    { id: "status", header: "Status", meta: { label: "Status" }, cell: ({ row }) => <StatusBadge status={row.original.status} /> },
    {
      id: "expires_at", header: "Expires", meta: { sortKey: "expires_at", label: "Expires", className: "hidden md:table-cell" },
      cell: ({ row: { original: r } }) => r.status === "active"
        ? <span className="text-small" title={formatDateTime(r.expires_at)}>{formatRelative(r.expires_at)}</span>
        : <span className="text-small text-fg-muted">{formatDateTime(r.converted_at ?? r.cancelled_at ?? r.expired_at)}</span>,
    },
    { id: "price", header: "List price", meta: { label: "List price", align: "right", className: "hidden lg:table-cell" }, cell: ({ row }) => <MoneyText value={row.original.list_price} /> },
    { id: "deposit", header: "Deposit", meta: { label: "Deposit", align: "right", className: "hidden xl:table-cell" }, cell: ({ row }) => row.original.deposit_amount ? <MoneyText value={row.original.deposit_amount} /> : <span className="text-fg-muted">—</span> },
    {
      id: "actions", header: "", meta: { label: "Actions", align: "right" }, enableHiding: false,
      cell: ({ row: { original: r } }) => r.allowed_actions.length ? (
        <div className="flex justify-end gap-1">
          <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); setActing({ r, mode: "cancel" }); }}>Cancel</Button>
          <Button size="sm" onClick={(e) => { e.stopPropagation(); setActing({ r, mode: "convert" }); }}>Convert</Button>
        </div>
      ) : null,
    },
  ];

  return (
    <>
      <PageHeader title="Reservations" description="Units held for buyers. Active reservations expire automatically (72 hours by default); deposits are informational only." />
      {canAll && (
        <Tabs value={scope} onValueChange={(v) => state.setFilter("scope", v === "all" ? undefined : v)} className="mb-4">
          <TabsList><TabsTrigger value="all">All reservations</TabsTrigger><TabsTrigger value="mine">Mine</TabsTrigger></TabsList>
        </Tabs>
      )}
      <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Filter by status">
        {STATUSES.map((s) => {
          const active = state.filters.status === s;
          return (
            <button key={s} type="button" aria-pressed={active} onClick={() => state.setFilter("status", active ? undefined : s)}
              className={cn("h-8 rounded-full border px-3 text-small capitalize transition-colors", active ? "border-brand bg-brand-subtle text-brand" : "border-border bg-surface text-fg-secondary hover:border-border-strong")}>
              {s}
            </button>
          );
        })}
      </div>
      <DataTable
        ariaLabel="Reservations"
        columns={columns}
        page={list.data}
        isLoading={list.isPending}
        isFetching={list.isFetching}
        error={list.error}
        onRetry={() => void list.refetch()}
        state={state}
        searchPlaceholder="Search reservation, lead or unit"
        getRowId={(r) => r.id}
        empty={<EmptyState icon={<CalendarCheck className="size-5" />} title="No reservations" description="Reserve a unit from a lead's page." />}
        mobileRow={(r) => (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between gap-2"><span className="tabular font-medium">{r.code}</span><StatusBadge status={r.status} /></div>
            <p className="text-small"><Link className="text-brand" to={`/realestate/units/${r.unit.id}`}>{r.unit.code}</Link> · <Link to={`/crm/leads/${r.lead.id}`}>{r.lead.name}</Link></p>
            {r.status === "active" && <p className="text-caption text-fg-muted">Expires {formatRelative(r.expires_at)}</p>}
            {r.allowed_actions.length > 0 && (
              <div className="flex gap-2 pt-1">
                <Button size="sm" variant="ghost" onClick={() => setActing({ r, mode: "cancel" })}>Cancel</Button>
                <Button size="sm" onClick={() => setActing({ r, mode: "convert" })}>Convert</Button>
              </div>
            )}
          </div>
        )}
      />
      {acting?.mode === "convert" && <ConvertDialog r={acting.r} onClose={() => setActing(null)} />}
      {acting?.mode === "cancel" && <CancelReservationDialog reservation={acting.r} onClose={() => setActing(null)} />}
    </>
  );
}

function ConvertDialog({ r, onClose }: { r: Reservation; onClose: () => void }) {
  const { convert } = useReservationMutations();
  return (
    <ConfirmDialog open onOpenChange={(o) => !o && onClose()} loading={convert.isPending} title={`Convert ${r.code} to a sale?`} confirmLabel="Mark as sold"
      description={`Unit ${r.unit.code} becomes sold and ${r.lead.code} is marked won. This can't be undone.`}
      onConfirm={() => convert.mutate(r.id, {
        onSuccess: () => { toast.success(`${r.unit.code} sold`); onClose(); },
        onError: (e) => { toast.error(e instanceof ApiError ? e.message : "Couldn't convert"); onClose(); },
      })} />
  );
}
