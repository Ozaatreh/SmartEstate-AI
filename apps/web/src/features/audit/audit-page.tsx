import type { ColumnDef } from "@tanstack/react-table";
import { Copy, ScrollText } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { StatusBadge } from "@/components/system/badges";
import { DataTable } from "@/components/system/data-table";
import { DescriptionList, PageHeader } from "@/components/system/layout-blocks";
import { EmptyState } from "@/components/system/states";
import { useListState } from "@/components/system/use-list-state";
import { Button } from "@/components/ui/button";
import { Dialog, SheetContent } from "@/components/ui/dialog";
import { Select } from "@/components/ui/menu";
import { Avatar } from "@/components/ui/primitives";
import { useAuditLogs, type AuditLog } from "@/features/platform/api";
import { formatDateTime, formatRelative } from "@/lib/format";
import { humanize } from "@/lib/status";

const FILTERS = ["action"] as const;

const ACTION_OPTIONS = [
  { value: "all", label: "All events" },
  { value: "auth.", label: "Authentication" },
  { value: "auth.login_failed", label: "Failed sign-ins" },
  { value: "auth.account_locked", label: "Account locks" },
];

function actionTone(action: string): string {
  if (/failed|locked|throttled|denied/.test(action)) return "danger";
  if (/succeeded|approved|created/.test(action)) return "success";
  return "info";
}

function initialsOf(name: string): string {
  return name.split(" ").filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase();
}

export default function AuditPage() {
  const state = useListState({ filterKeys: FILTERS, defaultSort: "-created_at" });
  const list = useAuditLogs(state.query);
  const [selected, setSelected] = React.useState<AuditLog | null>(null);

  const columns: ColumnDef<AuditLog, unknown>[] = [
    {
      id: "action", header: "Event", meta: { sortKey: "action", label: "Event" }, enableHiding: false,
      cell: ({ row: { original: a } }) => (
        <div className="flex flex-col gap-0.5">
          <StatusBadge status={actionTone(a.action)} label={humanize(a.action.split(".").slice(1).join(" ")) || a.action} className="self-start" />
          <code className="text-caption text-fg-muted">{a.action}</code>
        </div>
      ),
    },
    {
      id: "actor", header: "Actor", meta: { label: "Actor" },
      cell: ({ row: { original: a } }) => a.actor ? (
        <div className="flex items-center gap-2">
          <Avatar initials={initialsOf(a.actor.full_name)} className="size-6 [&_span]:text-[10px]" />
          <div className="min-w-0"><p className="truncate">{a.actor.full_name}</p><p className="truncate text-caption text-fg-muted">{a.actor.email}</p></div>
        </div>
      ) : <span className="text-fg-muted">System / anonymous</span>,
    },
    { id: "summary", header: "Details", meta: { label: "Details", className: "hidden lg:table-cell" }, cell: ({ row }) => <span className="text-small text-fg-secondary">{row.original.summary ?? "—"}</span> },
    { id: "ip", header: "IP address", meta: { label: "IP address", className: "hidden xl:table-cell" }, cell: ({ row }) => <span className="tabular text-small text-fg-secondary">{row.original.ip_address ?? "—"}</span> },
    {
      id: "created_at", header: "When", meta: { sortKey: "created_at", label: "When", align: "right", className: "w-44" },
      cell: ({ row }) => <span className="tabular text-small text-fg-secondary" title={formatDateTime(row.original.created_at)}>{formatRelative(row.original.created_at)}</span>,
    },
  ];

  return (
    <>
      <PageHeader title="Audit log" description="An append-only record of security and business events. Entries can't be edited or deleted." />
      <DataTable
        ariaLabel="Audit log"
        columns={columns}
        page={list.data}
        isLoading={list.isPending}
        isFetching={list.isFetching}
        error={list.error}
        onRetry={() => void list.refetch()}
        state={state}
        searchPlaceholder="Search events, people or IDs"
        getRowId={(a) => a.id}
        onRowClick={setSelected}
        filters={
          <Select aria-label="Event type" className="h-8 w-44" value={state.filters.action ?? "all"}
            onValueChange={(v) => state.setFilter("action", v === "all" ? undefined : v)} options={ACTION_OPTIONS} />
        }
        empty={<EmptyState icon={<ScrollText className="size-5" />} title="No events recorded yet" description="Sign-ins and business actions are recorded here automatically." />}
        mobileRow={(a) => (
          <div className="space-y-1">
            <div className="flex items-center justify-between gap-2">
              <StatusBadge status={actionTone(a.action)} label={humanize(a.action.split(".").slice(1).join(" ")) || a.action} />
              <span className="text-caption text-fg-muted">{formatRelative(a.created_at)}</span>
            </div>
            <p className="text-body">{a.actor?.full_name ?? "System / anonymous"}</p>
            {a.summary && <p className="text-small text-fg-muted">{a.summary}</p>}
          </div>
        )}
      />

      <Dialog open={selected !== null} onOpenChange={(o) => !o && setSelected(null)}>
        <SheetContent side="right" title="Audit event" className="w-[min(440px,92vw)]">
          {selected && (
            <div className="flex h-full flex-col">
              <div className="border-b border-border px-5 py-4">
                <p className="text-caption font-medium uppercase tracking-[0.06em] text-fg-muted">Audit event</p>
                <h2 className="mt-1 text-lead font-semibold">{humanize(selected.action.split(".").slice(1).join(" "))}</h2>
                <code className="text-small text-fg-muted">{selected.action}</code>
              </div>
              <div className="flex-1 overflow-y-auto">
                <DescriptionList items={[
                  { label: "When", value: formatDateTime(selected.created_at) },
                  { label: "Actor", value: selected.actor ? `${selected.actor.full_name} (${selected.actor.email})` : "System / anonymous" },
                  { label: "Subject", value: selected.entity_type ? `${selected.entity_type} · ${selected.entity_id}` : "—" },
                  { label: "Details", value: selected.summary ?? "—" },
                  { label: "IP address", value: <span className="tabular">{selected.ip_address ?? "—"}</span> },
                  {
                    label: "Request ID", value: selected.request_id ? (
                      <button type="button" className="inline-flex items-center gap-1 text-small text-brand hover:underline"
                        onClick={() => { void navigator.clipboard?.writeText(selected.request_id ?? ""); toast.success("Request ID copied"); }}>
                        <span className="tabular">{selected.request_id.slice(0, 12)}…</span><Copy className="size-3" />
                      </button>
                    ) : "—",
                  },
                ]} />
                {selected.changes && (
                  <div className="px-4 py-3">
                    <p className="mb-2 text-small text-fg-muted">Changes</p>
                    <pre className="overflow-x-auto rounded-[var(--radius-control)] bg-surface-sunken p-3 text-caption">{JSON.stringify(selected.changes, null, 2)}</pre>
                  </div>
                )}
              </div>
              <div className="border-t border-border p-4"><Button className="w-full" onClick={() => setSelected(null)}>Close</Button></div>
            </div>
          )}
        </SheetContent>
      </Dialog>
    </>
  );
}
