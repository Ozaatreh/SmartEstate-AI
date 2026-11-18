import { Archive, Building, CalendarRange, Pencil, Plus, Target } from "lucide-react";
import * as React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { StatusBadge } from "@/components/system/badges";
import { MetaItem } from "@/components/system/business";
import { ConfirmDialog } from "@/components/system/forms";
import { PageHeader, Panel } from "@/components/system/layout-blocks";
import { ErrorState, ListSkeleton } from "@/components/system/states";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api-client";
import { formatRelative } from "@/lib/format";
import { useCampaign, useCampaignMutations, useContentList } from "./api";
import { CampaignDialog } from "./campaign-dialog";
import { CHANNELS, dateRange } from "./logic";
import { ChannelLabel, ContentStatusBadge, LanguageBadge } from "./shared";

export default function CampaignDetailPage() {
  const { id } = useParams();
  const q = useCampaign(id);
  const content = useContentList({ campaign_id: id, page_size: 100, sort: "-updated_at" });
  const { archive } = useCampaignMutations(id);
  const navigate = useNavigate();
  const [dialog, setDialog] = React.useState<"edit" | "archive" | null>(null);
  if (q.isPending) return <ListSkeleton rows={6} />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} className="min-h-[50vh]" />;
  const c = q.data;
  const can = (a: string) => c.allowed_actions.includes(a);

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: "Campaigns", to: "/marketing/campaigns" }, { label: c.code }]}
        title={c.name}
        description={c.description ?? undefined}
        meta={<>
          <StatusBadge status={c.status} />
          <MetaItem icon={<Target />}>{c.objective}</MetaItem>
          <MetaItem icon={<Building />}><Link to={`/realestate/projects/${c.project.id}`} className="hover:underline">{c.project.name}</Link></MetaItem>
          <MetaItem icon={<CalendarRange />}>{dateRange(c)}</MetaItem>
        </>}
        actions={<>
          {can("archive") && <Button onClick={() => setDialog("archive")}><Archive /> Archive</Button>}
          {can("edit") && <Button onClick={() => setDialog("edit")}><Pencil /> Edit</Button>}
          {can("add_content") && <Button variant="primary" onClick={() => navigate(`/marketing/content/new?campaign=${c.id}`)}><Plus /> New content</Button>}
        </>}
      />

      <div className="mb-6 grid gap-3 sm:grid-cols-5">
        {(["draft", "rejected", "pending_approval", "approved", "archived"] as const).map((s) => (
          <div key={s} className="rounded-[var(--radius-panel)] border border-border bg-surface px-4 py-3">
            <p className="text-caption text-fg-muted"><ContentStatusBadge status={s} /></p>
            <p className="mt-1 text-h3 font-semibold tabular">{c.content[s]}</p>
          </div>
        ))}
      </div>

      <Panel title="Content" description={`Channels: ${c.channels.map((ch) => CHANNELS[ch].label).join(", ")}`}>
        {content.isPending ? <ListSkeleton rows={3} /> : content.isError ? <ErrorState error={content.error} onRetry={() => void content.refetch()} />
          : content.data.items.length ? (
            <ul className="divide-y divide-border-subtle">
              {content.data.items.map((it) => (
                <li key={it.id}>
                  <Link to={`/marketing/content/${it.id}`} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 transition-colors hover:bg-surface-subtle">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="tabular text-small text-fg-muted">{it.code}</span>
                        <ChannelLabel channel={it.channel} />
                        <LanguageBadge language={it.language} />
                        <span className="text-caption text-fg-muted">v{it.version}</span>
                      </div>
                      <p className="mt-1 truncate text-body" lang={it.language} dir={it.language === "ar" ? "rtl" : "ltr"}>{it.headline || it.body}</p>
                    </div>
                    <div className="flex items-center gap-3"><span className="text-caption text-fg-muted">{formatRelative(it.updated_at)}</span><ContentStatusBadge status={it.status} /></div>
                  </Link>
                </li>
              ))}
            </ul>
          ) : <p className="p-4 text-small text-fg-muted">No content yet.{can("add_content") ? " Use New content to write the first post." : ""}</p>}
      </Panel>

      {dialog === "edit" && <CampaignDialog campaign={c} onClose={() => setDialog(null)} />}
      <ConfirmDialog open={dialog === "archive"} onOpenChange={(o) => !o && setDialog(null)} loading={archive.isPending}
        title={`Archive ${c.code}?`} confirmLabel="Archive campaign"
        description="The campaign and its content become read-only. Content waiting for review must be decided first."
        onConfirm={() => archive.mutate(c.id, {
          onSuccess: () => { toast.success(`${c.code} archived`); setDialog(null); },
          onError: (e) => { toast.error(e instanceof ApiError ? e.message : "Couldn't archive"); setDialog(null); },
        })} />
    </>
  );
}
