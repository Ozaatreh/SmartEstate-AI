import type { ColumnDef } from "@tanstack/react-table";
import { Bell, CheckCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { StatusBadge } from "@/components/system/badges";
import { DataTable } from "@/components/system/data-table";
import { PageHeader } from "@/components/system/layout-blocks";
import { EmptyState } from "@/components/system/states";
import { useListState } from "@/components/system/use-list-state";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/menu";
import { useMarkAllRead, useMarkRead, useNotifications, useUnreadCount, type Notification } from "@/features/platform/api";
import { formatDateTime, formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

const FILTERS = ["unread_only"] as const;

export default function NotificationsPage() {
  const state = useListState({ filterKeys: FILTERS, defaultSort: "-created_at" });
  const list = useNotifications(state.query);
  const unread = useUnreadCount();
  const markRead = useMarkRead();
  const markAll = useMarkAllRead();
  const navigate = useNavigate();

  const open = (n: Notification) => {
    if (!n.read_at) markRead.mutate(n.id);
    if (n.link) navigate(n.link);
  };

  const columns: ColumnDef<Notification, unknown>[] = [
    {
      id: "title", header: "Notification", meta: { sortKey: "title", label: "Notification" }, enableHiding: false,
      cell: ({ row: { original: n } }) => (
        <div className="flex items-start gap-3 py-1">
          <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", n.read_at ? "bg-transparent" : "bg-brand")} aria-label={n.read_at ? "Read" : "Unread"} />
          <div className="min-w-0">
            <p className={cn("text-body", !n.read_at && "font-medium")}>{n.title}</p>
            {n.body && <p className="mt-0.5 max-w-xl truncate text-small text-fg-muted">{n.body}</p>}
          </div>
        </div>
      ),
    },
    { id: "level", header: "Type", meta: { label: "Type", className: "w-32" }, cell: ({ row }) => <StatusBadge status={row.original.level} /> },
    {
      id: "created_at", header: "Received", meta: { sortKey: "created_at", label: "Received", align: "right", className: "w-48" },
      cell: ({ row }) => <span className="tabular text-small text-fg-secondary" title={formatDateTime(row.original.created_at)}>{formatRelative(row.original.created_at)}</span>,
    },
  ];

  return (
    <>
      <PageHeader
        title="Notifications"
        description="Approvals, alerts and updates addressed to you."
        actions={
          <Button variant="secondary" disabled={!unread.data?.unread} loading={markAll.isPending}
            onClick={() => markAll.mutate(undefined, { onSuccess: (r) => toast.success(`${r.marked} marked as read`) })}>
            <CheckCheck /> Mark all read
          </Button>
        }
      />
      <DataTable
        ariaLabel="Notifications"
        columns={columns}
        page={list.data}
        isLoading={list.isPending}
        isFetching={list.isFetching}
        error={list.error}
        onRetry={() => void list.refetch()}
        state={state}
        searchPlaceholder="Search notifications"
        getRowId={(n) => n.id}
        onRowClick={open}
        filters={
          <Select aria-label="Read status" className="h-8 w-36" value={state.filters.unread_only ?? "all"}
            onValueChange={(v) => state.setFilter("unread_only", v === "all" ? undefined : v)}
            options={[{ value: "all", label: "All" }, { value: "true", label: "Unread only" }]} />
        }
        empty={<EmptyState icon={<Bell className="size-5" />} title="No notifications yet" description="Approvals, alerts and workflow updates will appear here." />}
        mobileRow={(n) => (
          <div className="flex items-start gap-3">
            <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", n.read_at ? "bg-border-strong" : "bg-brand")} />
            <div className="min-w-0 flex-1">
              <p className={cn("text-body", !n.read_at && "font-medium")}>{n.title}</p>
              {n.body && <p className="mt-0.5 line-clamp-2 text-small text-fg-muted">{n.body}</p>}
              <p className="mt-1 text-caption text-fg-muted">{formatRelative(n.created_at)}</p>
            </div>
          </div>
        )}
      />
    </>
  );
}
