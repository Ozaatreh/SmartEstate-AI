import type { ColumnDef } from "@tanstack/react-table";
import { Megaphone, Plus } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { StatusBadge } from "@/components/system/badges";
import { DataTable } from "@/components/system/data-table";
import { PageHeader } from "@/components/system/layout-blocks";
import { EmptyState } from "@/components/system/states";
import { useListState } from "@/components/system/use-list-state";
import { Button } from "@/components/ui/button";
import { useCan } from "@/features/auth/auth-context";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useCampaigns, type Campaign } from "./api";
import { CampaignDialog } from "./campaign-dialog";
import { dateRange } from "./logic";
import { ChannelLabel } from "./shared";

const FILTERS = ["status"] as const;
const STATUS_FILTERS = [
  { value: undefined, label: "Current" }, { value: "active", label: "Active" }, { value: "draft", label: "Draft" },
  { value: "completed", label: "Completed" }, { value: "archived", label: "Archived" },
] as const;

export default function CampaignsPage() {
  const canManage = useCan("marketing.campaigns.manage");
  const state = useListState({ filterKeys: FILTERS, defaultSort: "-created_at" });
  const list = useCampaigns({ ...state.query, status: state.filters.status ?? "current" });
  const navigate = useNavigate();
  const [creating, setCreating] = React.useState(false);

  const columns: ColumnDef<Campaign, unknown>[] = [
    {
      id: "name", header: "Campaign", meta: { sortKey: "name", label: "Campaign" }, enableHiding: false,
      cell: ({ row: { original: c } }) => (
        <div className="min-w-0">
          <p className="font-medium">{c.name}</p>
          <p className="truncate text-small text-fg-muted"><span className="tabular">{c.code}</span> · {c.objective}</p>
        </div>
      ),
    },
    { id: "project", header: "Project", meta: { label: "Project", className: "hidden md:table-cell" }, cell: ({ row }) => row.original.project.name },
    {
      id: "channels", header: "Channels", meta: { label: "Channels", className: "hidden lg:table-cell" },
      cell: ({ row }) => <div className="flex flex-wrap gap-x-3 gap-y-1">{row.original.channels.map((ch) => <ChannelLabel key={ch} channel={ch} />)}</div>,
    },
    {
      id: "content", header: "Content", meta: { label: "Content", className: "hidden md:table-cell" },
      cell: ({ row: { original: c } }) => (
        <span className="text-small text-fg-secondary">
          {c.content.approved} approved · {c.content.pending_approval} in review · {c.content.draft + c.content.rejected} drafts
        </span>
      ),
    },
    { id: "start_date", header: "Dates", meta: { sortKey: "start_date", label: "Dates", className: "hidden xl:table-cell" }, cell: ({ row }) => <span className="text-small">{dateRange(row.original)}</span> },
    { id: "status", header: "Status", meta: { label: "Status" }, cell: ({ row }) => <StatusBadge status={row.original.status} /> },
  ];

  return (
    <>
      <PageHeader
        title="Campaigns"
        description="Marketing campaigns per project and channel. Content is written here, reviewed by a marketing manager, and never published automatically."
        actions={canManage && <Button variant="primary" onClick={() => setCreating(true)}><Plus /> New campaign</Button>}
      />
      <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Filter by status">
        {STATUS_FILTERS.map((s) => {
          const active = (state.filters.status ?? undefined) === s.value;
          return (
            <button key={s.label} type="button" aria-pressed={active} onClick={() => state.setFilter("status", s.value)}
              className={cn("h-8 rounded-full border px-3 text-small transition-colors", active ? "border-brand bg-brand-subtle text-brand" : "border-border bg-surface text-fg-secondary hover:border-border-strong")}>
              {s.label}
            </button>
          );
        })}
      </div>
      <DataTable
        ariaLabel="Campaigns"
        columns={columns}
        page={list.data}
        isLoading={list.isPending}
        isFetching={list.isFetching}
        error={list.error}
        onRetry={() => void list.refetch()}
        state={state}
        searchPlaceholder="Search name or code"
        getRowId={(c) => c.id}
        onRowClick={(c) => navigate(`/marketing/campaigns/${c.id}`)}
        empty={<EmptyState icon={<Megaphone className="size-5" />} title="No campaigns yet"
          description={canManage ? "Create a campaign for a project, then write content for its channels." : "Campaigns created by the marketing team appear here."}
          action={canManage ? <Button size="sm" variant="primary" onClick={() => setCreating(true)}><Plus /> New campaign</Button> : undefined} />}
        mobileRow={(c) => (
          <div className="space-y-1">
            <div className="flex items-center justify-between gap-2"><span className="font-medium">{c.name}</span><StatusBadge status={c.status} /></div>
            <p className="text-small text-fg-muted">{c.code} · {c.project.name}</p>
            <p className="text-caption text-fg-muted">{c.content.approved} approved · {c.content.pending_approval} in review · updated {formatRelative(c.updated_at)}</p>
          </div>
        )}
      />
      {creating && <CampaignDialog onClose={() => setCreating(false)} />}
    </>
  );
}
