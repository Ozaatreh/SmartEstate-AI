import { ArrowRight, Bell, Database, ScrollText, ShieldCheck, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge, Chip, StatusBadge } from "@/components/system/badges";
import { PageHeader, Panel } from "@/components/system/layout-blocks";
import { ErrorState, ListSkeleton } from "@/components/system/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/primitives";
import { useAuth } from "@/features/auth/auth-context";
import { useAuditLogs, useHealth, useNotifications, useUnreadCount } from "@/features/platform/api";
import { formatDateTime, formatRelative } from "@/lib/format";
import { humanize } from "@/lib/status";
import { cn } from "@/lib/utils";

function greeting(now = new Date()): string {
  const h = now.getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

/** Phase 1 home: the signed-in workspace — account, notifications, platform status, recent activity. All live data. */
export default function HomePage() {
  const { user, can } = useAuth();
  const canAudit = can("audit.logs.read");
  const unread = useUnreadCount();
  const notifications = useNotifications({ page_size: 5 });
  const health = useHealth();
  const activity = useAuditLogs({ page_size: 6 }, canAudit);
  if (!user) return null;
  const firstName = user.full_name.split(" ")[0];

  return (
    <>
      <PageHeader
        title={`${greeting()}, ${firstName}`}
        description="Your SmartEstate workspace. Business modules appear here as they're enabled for your role."
        meta={user.roles.map((r) => <Chip key={r.code}>{r.name}</Chip>)}
      />

      <div className="grid gap-4 lg:grid-cols-3">
        {/* Notifications */}
        <Panel
          className="lg:col-span-2"
          title="Notifications"
          description={unread.data ? `${unread.data.unread} unread` : undefined}
          actions={<Button asChild size="sm" variant="ghost"><Link to="/notifications">View all <ArrowRight /></Link></Button>}
        >
          {notifications.isPending ? <ListSkeleton rows={3} /> : notifications.isError ? (
            <ErrorState error={notifications.error} onRetry={() => void notifications.refetch()} />
          ) : !notifications.data.items.length ? (
            <div className="flex items-center gap-3 px-4 py-8 text-body text-fg-muted"><Bell className="size-4" /> You're all caught up.</div>
          ) : (
            <ul className="divide-y divide-border-subtle">
              {notifications.data.items.map((n) => (
                <li key={n.id} className="flex items-start gap-3 px-4 py-3">
                  <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", n.read_at ? "bg-border-strong" : "bg-brand")} />
                  <div className="min-w-0 flex-1">
                    <p className={cn("text-body", !n.read_at && "font-medium")}>{n.title}</p>
                    {n.body && <p className="mt-0.5 text-small text-fg-secondary">{n.body}</p>}
                  </div>
                  <span className="shrink-0 text-caption text-fg-muted">{formatRelative(n.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        {/* Account & platform */}
        <div className="space-y-4">
          <Panel title="Your account">
            <dl className="divide-y divide-border-subtle text-body">
              <Row label="Email" value={<span className="truncate">{user.email}</span>} />
              <Row label="Title" value={user.job_title ?? "—"} />
              <Row label="Permissions" value={user.is_super_admin ? "All (Super Admin)" : `${user.permissions.length} granted`} />
              <Row label="Last sign-in" value={formatDateTime(user.last_login_at)} />
              <Row label="Session ends" value={formatDateTime(user.session_expires_at)} />
            </dl>
          </Panel>

          <Panel title="Platform status" description={health.data ? `v${health.data.version} · ${health.data.environment}` : undefined}>
            {health.isPending ? (
              <div className="space-y-3 p-4"><Skeleton className="h-4 w-3/4" /><Skeleton className="h-4 w-2/3" /></div>
            ) : health.isError ? (
              <ErrorState error={health.error} onRetry={() => void health.refetch()} />
            ) : (
              <ul className="divide-y divide-border-subtle">
                <StatusRow icon={<Database className="size-4" />} label="Database" status={health.data.database === "ok" ? "Operational" : "Unavailable"}
                  tone={health.data.database === "ok" ? "success" : "danger"} />
                <StatusRow icon={<ShieldCheck className="size-4" />} label="Authentication" status="Operational" tone="success" />
                <StatusRow icon={<Sparkles className="size-4" />} label="AI services" status={humanize(health.data.ai.state)}
                  tone={health.data.ai.state === "enabled" ? "success" : health.data.ai.state === "disabled" ? "neutral" : "warning"}
                  detail={health.data.ai.reason} />
              </ul>
            )}
          </Panel>
        </div>

        {/* Recent activity (audit) */}
        {canAudit && (
          <Panel
            className="lg:col-span-3"
            title="Recent activity"
            description="Security and business events across the platform"
            actions={<Button asChild size="sm" variant="ghost"><Link to="/admin/audit"><ScrollText /> Audit log</Link></Button>}
          >
            {activity.isPending ? <ListSkeleton rows={4} /> : activity.isError ? (
              <ErrorState error={activity.error} onRetry={() => void activity.refetch()} />
            ) : !activity.data.items.length ? (
              <p className="px-4 py-8 text-body text-fg-muted">No activity recorded yet.</p>
            ) : (
              <ul className="divide-y divide-border-subtle">
                {activity.data.items.map((a) => (
                  <li key={a.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5">
                    <StatusBadge status={a.action.endsWith("failed") || a.action.endsWith("locked") ? "danger" : a.action.endsWith("succeeded") ? "success" : "info"} label={humanize(a.action.split(".").slice(1).join(" "))} />
                    <span className="text-body text-fg">{a.actor?.full_name ?? "System"}</span>
                    {a.summary && <span className="hidden text-small text-fg-muted md:inline">· {a.summary}</span>}
                    <span className="ml-auto text-caption text-fg-muted">{formatRelative(a.created_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        )}
      </div>
    </>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 px-4 py-2.5">
      <dt className="shrink-0 text-small text-fg-muted">{label}</dt>
      <dd className="min-w-0 truncate text-right">{value}</dd>
    </div>
  );
}

function StatusRow({ icon, label, status, tone, detail }: { icon: React.ReactNode; label: string; status: string; tone: "success" | "danger" | "warning" | "neutral"; detail?: string }) {
  return (
    <li className="px-4 py-2.5">
      <div className="flex items-center gap-2.5">
        <span className="text-fg-muted">{icon}</span>
        <span className="text-body">{label}</span>
        <Badge tone={tone} className="ml-auto">{status}</Badge>
      </div>
      {detail && tone !== "success" && <p className="mt-1 pl-[26px] text-small text-fg-muted">{detail}</p>}
    </li>
  );
}
