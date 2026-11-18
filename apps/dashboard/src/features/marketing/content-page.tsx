import type { ColumnDef } from "@tanstack/react-table";
import { FileText } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { DataTable } from "@/components/system/data-table";
import { PageHeader } from "@/components/system/layout-blocks";
import { EmptyState } from "@/components/system/states";
import { useListState } from "@/components/system/use-list-state";
import { Select } from "@/components/ui/menu";
import { formatDateTime, formatRelative } from "@/lib/format";
import { useContentList, type Content } from "./api";
import { CHANNEL_KEYS, CHANNELS, CONTENT_STATUS_LABEL } from "./logic";
import { ChannelLabel, ContentStatusBadge, LanguageBadge } from "./shared";

const FILTERS = ["status", "channel", "language"] as const;
const ALL = "all";
const STATUS_OPTIONS = [
  { value: ALL, label: "All current" },
  ...(["pending_approval", "draft", "rejected", "approved", "archived"] as const).map((s) => ({ value: s, label: CONTENT_STATUS_LABEL[s] })),
];

export default function ContentPage() {
  const state = useListState({ filterKeys: FILTERS, defaultSort: "-updated_at" });
  const { status, channel, language } = state.filters;
  const list = useContentList({ ...state.query, status: status ?? "current", channel, language });
  const navigate = useNavigate();

  const columns: ColumnDef<Content, unknown>[] = [
    {
      id: "content", header: "Content", meta: { label: "Content" }, enableHiding: false,
      cell: ({ row: { original: c } }) => (
        <div className="min-w-0 max-w-xl">
          <p className="truncate font-medium" lang={c.language} dir={c.language === "ar" ? "rtl" : "ltr"}>{c.headline || c.body}</p>
          <p className="text-small text-fg-muted"><span className="tabular">{c.code}</span> · {c.campaign.name} · v{c.version}</p>
        </div>
      ),
    },
    { id: "channel", header: "Channel", meta: { label: "Channel" }, cell: ({ row }) => <ChannelLabel channel={row.original.channel} /> },
    { id: "language", header: "Language", meta: { label: "Language", className: "hidden md:table-cell" }, cell: ({ row }) => <LanguageBadge language={row.original.language} /> },
    { id: "project", header: "Project", meta: { label: "Project", className: "hidden lg:table-cell" }, cell: ({ row }) => row.original.project.name },
    { id: "author", header: "Author", meta: { label: "Author", className: "hidden xl:table-cell" }, cell: ({ row }) => row.original.created_by?.full_name ?? "—" },
    {
      id: "updated_at", header: "Updated", meta: { sortKey: "updated_at", label: "Updated", align: "right", className: "hidden md:table-cell" },
      cell: ({ row }) => <span className="text-small text-fg-secondary" title={formatDateTime(row.original.updated_at)}>{formatRelative(row.original.updated_at)}</span>,
    },
    { id: "status", header: "Status", meta: { sortKey: "status", label: "Status" }, cell: ({ row }) => <ContentStatusBadge status={row.original.status} /> },
  ];

  return (
    <>
      <PageHeader title="Content" description="Every post, email and page across campaigns, with its review status." />
      <div className="mb-4 grid gap-2 sm:grid-cols-3 lg:max-w-3xl">
        <Select aria-label="Status" value={status ?? ALL} onValueChange={(v) => state.setFilter("status", v === ALL ? undefined : v)} options={STATUS_OPTIONS} />
        <Select aria-label="Channel" value={channel ?? ALL} onValueChange={(v) => state.setFilter("channel", v === ALL ? undefined : v)}
          options={[{ value: ALL, label: "All channels" }, ...CHANNEL_KEYS.map((c) => ({ value: c, label: CHANNELS[c].label }))]} />
        <Select aria-label="Language" value={language ?? ALL} onValueChange={(v) => state.setFilter("language", v === ALL ? undefined : v)}
          options={[{ value: ALL, label: "All languages" }, { value: "en", label: "English" }, { value: "ar", label: "Arabic" }]} />
      </div>
      <DataTable
        ariaLabel="Marketing content"
        columns={columns}
        page={list.data}
        isLoading={list.isPending}
        isFetching={list.isFetching}
        error={list.error}
        onRetry={() => void list.refetch()}
        state={state}
        searchPlaceholder="Search code, headline or text"
        getRowId={(c) => c.id}
        onRowClick={(c) => navigate(`/marketing/content/${c.id}`)}
        empty={<EmptyState icon={<FileText className="size-5" />} title="No content found" description="Open a campaign to write content for its channels."
          filtered={Boolean(status || channel || language || state.query.q)} onClearFilters={state.clear} />}
        mobileRow={(c) => (
          <div className="space-y-1">
            <div className="flex items-center justify-between gap-2"><ChannelLabel channel={c.channel} /><ContentStatusBadge status={c.status} /></div>
            <p className="font-medium" lang={c.language} dir={c.language === "ar" ? "rtl" : "ltr"}>{c.headline || c.body.slice(0, 80)}</p>
            <p className="text-caption text-fg-muted">{c.code} · {c.campaign.name} · {formatRelative(c.updated_at)}</p>
          </div>
        )}
      />
    </>
  );
}
