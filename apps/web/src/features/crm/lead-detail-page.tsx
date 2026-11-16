import {
  AlarmClock, ArrowRightLeft, Building, CalendarCheck, CalendarClock, Check, ChevronDown, Mail, Phone, UserRound,
} from "lucide-react";
import * as React from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Badge, StatusBadge } from "@/components/system/badges";
import { MetaItem } from "@/components/system/business";
import { MoneyText } from "@/components/system/data-display";
import { ConfirmDialog } from "@/components/system/forms";
import { DescriptionList, Panel } from "@/components/system/layout-blocks";
import { ErrorState, ListSkeleton } from "@/components/system/states";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/menu";
import { Skeleton } from "@/components/ui/primitives";
import { ApiError } from "@/lib/api-client";
import { formatDateTime, formatMoney, formatRelative } from "@/lib/format";
import { humanize } from "@/lib/status";
import { cn } from "@/lib/utils";
import { useLead, useLeadActivities, useReservationMutations, type Activity, type LeadDetail, type ReservationBrief, type Stage } from "./api";
import { STAGES, budgetLabel, stageLabel, stageProgress, timelineLabel } from "./crm-logic";
import { ActivityForm, FollowUpDialog, ReassignDialog, ReserveDialog, StageDialog } from "./lead-dialogs";
import { CancelReservationDialog } from "./reservation-dialogs";
import { ScoreBadge } from "./shared";

export default function LeadDetailPage() {
  const { id } = useParams();
  const q = useLead(id);
  if (q.isPending) return <DetailSkeleton />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} className="min-h-[50vh]" />;
  return <LeadView lead={q.data} />;
}

function LeadView({ lead: l }: { lead: LeadDetail }) {
  const [stageTarget, setStageTarget] = React.useState<Stage | null>(null);
  const [dialog, setDialog] = React.useState<"follow" | "reassign" | "reserve" | null>(null);
  const can = (a: string) => l.allowed_actions.includes(a);
  const active = l.reservations.find((r) => r.status === "active");

  return (
    <>
      <header className="mb-6">
        <Link to="/crm/leads" className="mb-3 inline-flex items-center gap-1 text-small text-fg-muted transition-colors hover:text-fg">← Leads</Link>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="tabular text-small font-medium text-fg-muted">{l.code}</span>
              <StatusBadge status={l.stage} label={stageLabel(l.stage)} />
              <ScoreBadge lead={l} />
              {l.follow_up_overdue && <Badge tone="danger"><AlarmClock className="size-3" /> Follow-up overdue</Badge>}
            </div>
            <h1 className="mt-1 text-h2 font-semibold tracking-[-0.015em]">{l.full_name}</h1>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-small text-fg-secondary">
              <MetaItem icon={<UserRound />}>{l.owner?.full_name ?? "Unassigned"}</MetaItem>
              {l.phone && <MetaItem icon={<Phone />}><a href={`tel:${l.phone}`} className="hover:underline">{l.phone}</a></MetaItem>}
              {l.email && <MetaItem icon={<Mail />}><a href={`mailto:${l.email}`} className="hover:underline">{l.email}</a></MetaItem>}
              {l.project && <MetaItem icon={<Building />}><Link to={`/realestate/projects/${l.project.id}`} className="hover:underline">{l.project.name}</Link></MetaItem>}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {can("reassign") && <Button onClick={() => setDialog("reassign")}><ArrowRightLeft /> Reassign</Button>}
            {can("edit") && l.stage !== "won" && l.stage !== "lost" && <Button onClick={() => setDialog("follow")}><CalendarClock /> Follow-up</Button>}
            {can("reserve") && !active && <Button onClick={() => setDialog("reserve")}><CalendarCheck /> Reserve unit</Button>}
            {l.allowed_stages.length > 0 && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild><Button variant="primary">Move stage <ChevronDown /></Button></DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {l.allowed_stages.map((s) => (
                    <DropdownMenuItem key={s} onSelect={() => setStageTarget(s)} className={s === "lost" ? "text-danger" : undefined}>
                      {l.stage === "lost" ? `Reopen as ${stageLabel(s)}` : stageLabel(s)}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>
        </div>
      </header>

      <Pipeline stage={l.stage} />
      {l.close_reason && (
        <p className="mb-6 rounded-[var(--radius-panel)] border border-border bg-surface-subtle px-4 py-3 text-body text-fg-secondary">
          {stageLabel(l.stage)}: “{l.close_reason}”
        </p>
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0 space-y-4">
          {active && <ActiveReservation reservation={active} leadCode={l.code} canOperate={can("reserve") || can("reassign")} />}
          <Panel title="Activity timeline" description="Calls, messages, viewings, stage changes and system events">
            {can("add_activity") && <ActivityForm lead={l} />}
            <Timeline id={l.id} />
          </Panel>
        </div>

        <aside className="space-y-4">
          <Panel title="Score" description="Deterministic rules — every point is explained">
            {l.score_reasons?.length ? (
              <ul className="divide-y divide-border-subtle">
                {l.score_reasons.map((r) => (
                  <li key={r.reason} className="flex items-center justify-between gap-3 px-4 py-2 text-small">
                    <span className="text-fg-secondary">{r.reason}</span>
                    <span className={cn("tabular font-medium", r.points === 0 && "text-fg-muted")}>+{r.points}</span>
                  </li>
                ))}
                <li className="flex items-center justify-between px-4 py-2.5 text-body font-semibold"><span>Total (max 100)</span><span className="tabular">{l.score}</span></li>
              </ul>
            ) : <p className="p-4 text-small text-fg-muted">The lead is being scored by the Lead Registration workflow.</p>}
          </Panel>
          <Panel title="Follow-up">
            <DescriptionList items={[
              { label: "Next follow-up", value: l.next_follow_up_at
                ? <span className={cn(l.follow_up_overdue && "font-medium text-danger")} title={formatDateTime(l.next_follow_up_at)}>{formatRelative(l.next_follow_up_at)}</span>
                : "—" },
              { label: "Last activity", value: l.last_activity_at ? <span title={formatDateTime(l.last_activity_at)}>{formatRelative(l.last_activity_at)}</span> : "—" },
              { label: "Assigned", value: formatDateTime(l.assigned_at) },
            ]} />
          </Panel>
          <Panel title="Requirements">
            <DescriptionList items={[
              { label: "Budget", value: <span className="tabular">{budgetLabel(l.budget_min, l.budget_max, (v) => formatMoney(v))}</span> },
              { label: "Bedrooms", value: l.bedrooms_wanted ?? "—" },
              { label: "Timeline", value: timelineLabel(l.timeline) },
              { label: "Interested in", value: l.interested_unit
                ? <Link className="text-brand hover:underline" to={`/realestate/units/${l.interested_unit.id}`}>{l.interested_unit.code} · {l.interested_unit.name}</Link> : "—" },
              { label: "Interest", value: l.interest ?? "—" },
            ]} />
          </Panel>
          <Panel title="Details">
            <DescriptionList items={[
              { label: "Source", value: humanize(l.source) },
              { label: "Language", value: l.preferred_language === "ar" ? "Arabic" : "English" },
              { label: "Consent", value: l.consent_given_at ? `Given ${formatDateTime(l.consent_given_at)}` : "Not recorded" },
              { label: "Registered by", value: l.created_by?.full_name ?? "System" },
              { label: "Created", value: formatDateTime(l.created_at) },
            ]} />
          </Panel>
          {l.reservations.length > 0 && (
            <Panel title="Reservations">
              <ul className="divide-y divide-border-subtle">
                {l.reservations.map((r) => (
                  <li key={r.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-small">
                    <span className="min-w-0"><span className="tabular font-medium">{r.code}</span> · <Link className="text-brand hover:underline" to={`/realestate/units/${r.unit.id}`}>{r.unit.code}</Link></span>
                    <StatusBadge status={r.status} />
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </aside>
      </div>

      {stageTarget && <StageDialog lead={l} target={stageTarget} onClose={() => setStageTarget(null)} />}
      {dialog === "follow" && <FollowUpDialog lead={l} onClose={() => setDialog(null)} />}
      {dialog === "reassign" && <ReassignDialog lead={l} onClose={() => setDialog(null)} />}
      {dialog === "reserve" && <ReserveDialog lead={l} onClose={() => setDialog(null)} />}
    </>
  );
}

function Pipeline({ stage }: { stage: Stage }) {
  const idx = stageProgress(stage);
  const forward = STAGES.filter((s) => s.key !== "lost");
  return (
    <ol className="mb-6 flex items-center gap-2 overflow-x-auto rounded-[var(--radius-panel)] border border-border bg-surface px-4 py-3 [scrollbar-width:none]" aria-label="Lead pipeline">
      {forward.map((s, i) => {
        const done = idx > i || stage === "won";
        const current = idx === i && stage !== "won";
        return (
          <li key={s.key} className="flex shrink-0 items-center gap-2">
            {i > 0 && <span aria-hidden className={cn("h-px w-4 sm:w-8", done || current ? "bg-success/50" : "bg-border")} />}
            <span className={cn("grid size-5 place-items-center rounded-full text-[11px] font-semibold",
              done ? "bg-success text-white" : current ? "bg-brand text-white" : "bg-surface-sunken text-fg-muted")}>
              {done ? <Check className="size-3" /> : i + 1}
            </span>
            <span className={cn("text-small", current ? "font-medium text-fg" : done ? "text-fg-secondary" : "text-fg-muted")} aria-current={current ? "step" : undefined}>{s.label}</span>
          </li>
        );
      })}
      {stage === "lost" && <li className="ml-auto shrink-0 pl-4"><StatusBadge status="lost" label="Lost" /></li>}
    </ol>
  );
}

function ActiveReservation({ reservation: r, leadCode, canOperate }: { reservation: ReservationBrief; leadCode: string; canOperate: boolean }) {
  const { convert } = useReservationMutations();
  const [mode, setMode] = React.useState<"cancel" | "convert" | null>(null);
  const onError = (e: unknown) => { toast.error(e instanceof ApiError ? e.message : "Action failed"); setMode(null); };
  return (
    <Panel title={`Active reservation ${r.code}`} description={`Unit ${r.unit.code} is held for ${leadCode}`}
      className="border-warning/50"
      actions={canOperate && <>
        <Button size="sm" variant="ghost" onClick={() => setMode("cancel")}>Cancel</Button>
        <Button size="sm" variant="primary" onClick={() => setMode("convert")}>Convert to sale</Button>
      </>}>
      <dl className="grid grid-cols-2 gap-3 p-4 text-small sm:grid-cols-3">
        <div><dt className="text-fg-muted">Unit</dt><dd><Link className="text-brand hover:underline" to={`/realestate/units/${r.unit.id}`}>{r.unit.code} · {r.unit.name}</Link></dd></div>
        <div><dt className="text-fg-muted">Expires</dt><dd title={formatDateTime(r.expires_at)}>{formatRelative(r.expires_at)}</dd></div>
        <div><dt className="text-fg-muted">Deposit (informational)</dt><dd>{r.deposit_amount ? <MoneyText value={r.deposit_amount} decimals={2} /> : "—"}</dd></div>
      </dl>
      <ConfirmDialog open={mode === "convert"} onOpenChange={(o) => !o && setMode(null)} loading={convert.isPending}
        title={`Convert ${r.code} to a sale?`} confirmLabel="Mark as sold"
        description={`Unit ${r.unit.code} becomes sold and ${leadCode} is marked won. This can't be undone.`}
        onConfirm={() => convert.mutate(r.id, { onSuccess: () => { toast.success(`${r.unit.code} sold`); setMode(null); }, onError })} />
      {mode === "cancel" && <CancelReservationDialog reservation={r} onClose={() => setMode(null)} />}
    </Panel>
  );
}

const TYPE_TONE: Record<string, string> = {
  stage_change: "bg-brand", assignment: "bg-info", system: "bg-border-strong", call: "bg-success", whatsapp: "bg-success",
  email: "bg-success", viewing: "bg-warning", note: "bg-fg-muted",
};

function Timeline({ id }: { id: string }) {
  const q = useLeadActivities(id);
  if (q.isPending) return <ListSkeleton rows={4} />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  if (!q.data.length) return <p className="p-4 text-small text-fg-muted">No activity yet.</p>;
  return (
    <ol className="p-4">
      {q.data.map((a: Activity, i: number) => (
        <li key={a.id} className="relative flex gap-3 pb-4 last:pb-0">
          {i < q.data.length - 1 && <span aria-hidden className="absolute left-[5px] top-4 h-full w-px bg-border" />}
          <span className={cn("relative mt-1.5 size-[11px] shrink-0 rounded-full border-2 border-surface", TYPE_TONE[a.type] ?? "bg-border-strong")} />
          <div className="min-w-0">
            <p className="text-body"><span className="font-medium">{a.performed_by?.full_name ?? "System"}</span> <span className="text-caption uppercase tracking-[0.04em] text-fg-muted">{humanize(a.type)}</span></p>
            <p className="whitespace-pre-line break-words text-small text-fg-secondary">{a.body}</p>
            <p className="text-caption text-fg-muted" title={formatDateTime(a.occurred_at)}>{formatRelative(a.occurred_at)}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

function DetailSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading lead">
      <Skeleton className="mb-2 h-4 w-20" /><Skeleton className="mb-6 h-8 w-72 max-w-full" /><Skeleton className="mb-6 h-12 w-full" />
      <div className="grid gap-6 xl:grid-cols-[1fr_380px]"><div className="rounded-[var(--radius-panel)] border border-border bg-surface"><ListSkeleton rows={5} /></div>
        <div className="rounded-[var(--radius-panel)] border border-border bg-surface"><ListSkeleton rows={3} /></div></div>
    </div>
  );
}

