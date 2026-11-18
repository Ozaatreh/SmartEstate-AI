/** Business-document building blocks shared by Operations modules (UI_UX_DESIGN.md § 4, Operations). */
import { AlertTriangle, ArrowUpRight, Check, CircleDashed, Clock, CornerDownRight, Flag, X } from "lucide-react";
import type * as React from "react";
import { Link } from "react-router-dom";
import { sumMoney } from "@/lib/decimal";
import { formatDateTime, formatPercent, formatRelative } from "@/lib/format";
import { humanize } from "@/lib/status";
import { cn } from "@/lib/utils";
import { Badge, StatusBadge } from "./badges";
import { Meter, MoneyText } from "./data-display";

// --- Document header ----------------------------------------------------------------------------
export function DocumentHeader({ code, title, status, amount, amountLabel, meta, actions, back }: {
  code: string; title: string; status: string; amount?: string | null; amountLabel?: string; meta?: React.ReactNode;
  actions?: React.ReactNode; back?: { to: string; label: string };
}) {
  return (
    <header className="mb-6">
      {back && <Link to={back.to} className="mb-3 inline-flex items-center gap-1 text-small text-fg-muted transition-colors hover:text-fg">← {back.label}</Link>}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="tabular text-small font-medium text-fg-muted">{code}</span>
            <StatusBadge status={status} />
          </div>
          <h1 className="mt-1 text-h2 font-semibold tracking-[-0.015em] text-fg">{title}</h1>
          {meta && <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-small text-fg-secondary">{meta}</div>}
        </div>
        <div className="flex shrink-0 flex-col gap-3 lg:items-end">
          {amount !== undefined && (
            <div className="lg:text-right">
              <p className="text-caption font-medium uppercase tracking-[0.06em] text-fg-muted">{amountLabel ?? "Amount"}</p>
              <MoneyText value={amount} decimals={2} className="text-h2 font-semibold tracking-[-0.02em]" />
            </div>
          )}
          {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
        </div>
      </div>
    </header>
  );
}

export function MetaItem({ icon, children }: { icon?: React.ReactNode; children: React.ReactNode }) {
  return <span className="inline-flex items-center gap-1.5 [&_svg]:size-3.5 [&_svg]:text-fg-muted">{icon}{children}</span>;
}

export function PriorityBadge({ priority }: { priority: string }) {
  if (priority === "normal") return null;
  return <Badge tone={priority === "urgent" ? "danger" : priority === "high" ? "warning" : "neutral"} dot={false}><Flag className="size-3" />{humanize(priority)}</Badge>;
}

// --- Approval timeline -----------------------------------------------------------------------------
interface TimelineStep {
  step_order: number;
  label: string;
  status: "waiting" | "pending" | "approved" | "rejected" | "skipped";
  assignee: { full_name: string } | null;
  pool_label: string | null;
  escalation_reason: string | null;
  activated_at: string | null;
  decided_at: string | null;
  decision: { decision: string; comment: string | null; decided_by: { full_name: string }; created_at: string } | null;
}

const STEP_ICON: Record<TimelineStep["status"], { icon: React.ReactNode; ring: string }> = {
  approved: { icon: <Check className="size-3.5" />, ring: "bg-success text-on-accent border-success" },
  rejected: { icon: <X className="size-3.5" />, ring: "bg-danger text-on-accent border-danger" },
  pending: { icon: <Clock className="size-3.5" />, ring: "bg-warning-subtle text-warning border-warning" },
  waiting: { icon: <CircleDashed className="size-3.5" />, ring: "bg-surface text-fg-muted border-border-strong" },
  skipped: { icon: <CircleDashed className="size-3.5" />, ring: "bg-surface-sunken text-fg-muted border-border" },
};

export function ApprovalTimeline({ steps, className }: { steps: TimelineStep[]; className?: string }) {
  return (
    <ol className={cn("relative", className)}>
      {steps.map((s, i) => {
        const look = STEP_ICON[s.status];
        const who = s.decision?.decided_by.full_name ?? s.assignee?.full_name ?? s.pool_label ?? "—";
        return (
          <li key={s.step_order} className="relative flex gap-3 pb-5 last:pb-0">
            {i < steps.length - 1 && <span aria-hidden className={cn("absolute left-[13px] top-7 h-[calc(100%-24px)] w-px", s.status === "approved" ? "bg-success/40" : "bg-border")} />}
            <span className={cn("relative z-10 grid size-7 shrink-0 place-items-center rounded-full border", look.ring)}>{look.icon}</span>
            <div className="min-w-0 flex-1 pt-0.5">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <p className="text-body font-medium text-fg">{s.label}</p>
                <StatusBadge status={s.status === "pending" ? "pending" : s.status} label={s.status === "pending" ? "Awaiting decision" : undefined} />
              </div>
              <p className="mt-0.5 text-small text-fg-secondary">
                {s.decision ? `${humanize(s.decision.decision)} by ${who}` : s.status === "skipped" ? "Not required after rejection" : `Assigned to ${who}`}
                {(s.decided_at || s.activated_at) && (
                  <span className="text-fg-muted" title={formatDateTime(s.decided_at ?? s.activated_at)}> · {formatRelative(s.decided_at ?? s.activated_at)}</span>
                )}
              </p>
              {s.escalation_reason && (
                <p className="mt-1.5 flex items-start gap-1.5 text-small text-warning"><CornerDownRight className="mt-0.5 size-3.5 shrink-0" />{s.escalation_reason}</p>
              )}
              {s.decision?.comment && (
                <blockquote className="mt-2 rounded-[var(--radius-control)] border-l-2 border-border-strong bg-surface-subtle px-3 py-2 text-small text-fg-secondary">
                  “{s.decision.comment}”
                </blockquote>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

// --- Budget impact -------------------------------------------------------------------------------------
interface ImpactProps {
  found: boolean;
  scope_label: string;
  category: string;
  fiscal_year: number;
  position: { allocated: string; adjustments: string; committed: string; actual: string; available: string; utilisation_pct: string } | null;
  amount: string;
  available_after: string | null;
  over_budget: boolean;
  committed_by_this_request?: boolean;
  approval_levels: string[];
  budgetLink?: string | null;
}

export function BudgetImpactCard({ impact, compact = false }: { impact: ImpactProps; compact?: boolean }) {
  if (!impact.found || !impact.position) {
    return (
      <div className="flex items-start gap-3 rounded-[var(--radius-panel)] border border-danger/25 bg-danger-subtle p-4 text-body text-danger">
        <AlertTriangle className="mt-0.5 size-4 shrink-0" />
        <div>
          <p className="font-medium">No budget found</p>
          <p className="mt-0.5 text-small">No active {impact.category} budget exists for {impact.scope_label} in FY{impact.fiscal_year}. Finance needs to set one up before this request can be submitted.</p>
        </div>
      </div>
    );
  }
  const p = impact.position;
  const capacity = Number(sumMoney([p.allocated, p.adjustments])); // proportions for the bar only
  const usedPct = Number(p.utilisation_pct);
  const thisPct = capacity > 0 ? (Number(impact.amount) / capacity) * 100 : 0;
  const committed = impact.committed_by_this_request;
  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-small font-medium text-fg">{impact.scope_label}</p>
          <p className="text-caption text-fg-muted">{impact.category} · FY{impact.fiscal_year}</p>
        </div>
        {impact.budgetLink && <Link to={impact.budgetLink} className="inline-flex shrink-0 items-center gap-0.5 text-small font-medium text-brand hover:underline">Budget<ArrowUpRight className="size-3.5" /></Link>}
      </div>
      {/* Stacked bar: already used + this request */}
      <div className="h-2 w-full overflow-hidden rounded-full bg-surface-sunken" role="img"
        aria-label={`${formatPercent(usedPct)} used${committed ? " including this request" : `, this request adds ${formatPercent(thisPct)}`}`}>
        <div className="flex h-full">
          <div className="h-full bg-primary" style={{ width: `${Math.min(100, usedPct)}%` }} />
          {!committed && <div className={cn("h-full", impact.over_budget ? "bg-danger" : "bg-brand")} style={{ width: `${Math.max(0, Math.min(100 - usedPct, thisPct))}%` }} />}
        </div>
      </div>
      <dl className={cn("grid gap-x-4 gap-y-2 text-small", compact ? "grid-cols-2" : "grid-cols-2 sm:grid-cols-4")}>
        <Fig label="Allocated" value={<MoneyText value={sumMoney([p.allocated, p.adjustments])} />} />
        <Fig label={committed ? "Committed (incl. this)" : "Committed"} value={<MoneyText value={sumMoney([p.committed, p.actual])} />} />
        <Fig label="This request" value={<MoneyText value={impact.amount} decimals={2} className={cn(!committed && "text-brand")} />} />
        <Fig label={committed ? "Available now" : "Available after"} value={<MoneyText value={impact.available_after} decimals={2} className={cn("font-semibold", impact.over_budget ? "text-danger" : "text-success")} />} />
      </dl>
      {impact.over_budget && !committed && (
        <p className="flex items-start gap-2 rounded-[var(--radius-control)] bg-danger-subtle px-3 py-2 text-small text-danger">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />Exceeds the available budget. Finance and Executive approval will be required.
        </p>
      )}
      {impact.approval_levels.length > 0 && !committed && (
        <p className="text-small text-fg-muted">Approval route: <span className="text-fg-secondary">{impact.approval_levels.join(" → ")}</span></p>
      )}
    </div>
  );
}

function Fig({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-caption text-fg-muted">{label}</dt>
      <dd className="truncate font-medium text-fg">{value}</dd>
    </div>
  );
}

/** Compact budget utilisation cell for tables. */
export function UtilisationCell({ pct, className }: { pct: string | number; className?: string }) {
  const v = Number(pct);
  return (
    <div className={cn("flex min-w-28 items-center gap-2", className)}>
      <Meter value={v} label="Budget utilisation" className="flex-1" />
      <span className={cn("tabular w-12 text-right text-small", v >= 100 ? "text-danger" : v >= 80 ? "text-warning" : "text-fg-secondary")}>{formatPercent(v)}</span>
    </div>
  );
}
