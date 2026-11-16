import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import type * as React from "react";
import { Link } from "react-router-dom";
import { Skeleton } from "@/components/ui/primitives";
import { formatMoney } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Money from API decimal strings — formatted exactly, tabular figures, negatives in danger tone. */
export function MoneyText({ value, decimals = 0, className }: { value: string | null | undefined; decimals?: 0 | 2; className?: string }) {
  const negative = typeof value === "string" && value.trim().startsWith("-");
  return <span className={cn("tabular whitespace-nowrap", negative && "text-danger", className)}>{formatMoney(value, { decimals })}</span>;
}

export interface KpiDelta {
  /** Signed change in percent vs. comparison period. */
  value: number;
  label?: string;
  /** Whether "up" is good (revenue) or bad (overdue items). */
  goodDirection?: "up" | "down";
}

/** KPI tile: label, value, delta vs. comparison period, optional sparkline and link to the source. */
export function KpiCard({ label, value, delta, hint, to, sparkline, loading, className }: {
  label: string; value: React.ReactNode; delta?: KpiDelta | null; hint?: React.ReactNode; to?: string;
  sparkline?: number[]; loading?: boolean; className?: string;
}) {
  const body = (
    <div className={cn(
      "group flex h-full flex-col rounded-[var(--radius-panel)] border border-border bg-surface p-4 transition-colors duration-150",
      to && "hover:border-border-strong",
      className,
    )}>
      <div className="flex items-start justify-between gap-2">
        <p className="text-small font-medium text-fg-secondary">{label}</p>
        {sparkline && sparkline.length > 1 && <Sparkline values={sparkline} />}
      </div>
      {loading ? (
        <div className="mt-3 space-y-2"><Skeleton className="h-7 w-28" /><Skeleton className="h-3 w-20" /></div>
      ) : (
        <div className="mt-3">
          <p className="tabular text-h2 font-semibold tracking-[-0.02em] text-fg">{value}</p>
          <div className="mt-1 flex items-center gap-2 text-small">
            {delta && <DeltaText delta={delta} />}
            {hint && <span className="text-fg-muted">{hint}</span>}
          </div>
        </div>
      )}
    </div>
  );
  return to ? <Link to={to} className="block rounded-[var(--radius-panel)]">{body}</Link> : body;
}

function DeltaText({ delta }: { delta: KpiDelta }) {
  const { value, goodDirection = "up", label } = delta;
  const flat = Math.abs(value) < 0.05;
  const good = flat ? null : (value > 0) === (goodDirection === "up");
  const Icon = flat ? Minus : value > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <span className={cn("inline-flex items-center gap-0.5 font-medium tabular", good === null ? "text-fg-muted" : good ? "text-success" : "text-danger")}>
      <Icon className="size-3.5" aria-hidden />
      {flat ? "0%" : `${value > 0 ? "+" : ""}${value.toFixed(1)}%`}
      {label && <span className="ml-1 font-normal text-fg-muted">{label}</span>}
    </span>
  );
}

export function Sparkline({ values, className }: { values: number[]; className?: string }) {
  const w = 64, h = 20;
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - ((v - min) / span) * (h - 2) - 1}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className={cn("h-5 w-16 shrink-0", className)} aria-hidden>
      <polyline points={pts} fill="none" stroke="var(--chart-1)" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

/** Horizontal meter (budget utilisation etc.). Tone shifts at thresholds. */
export function Meter({ value, max = 100, label, className }: { value: number; max?: number; label?: string; className?: string }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const tone = pct >= 100 ? "bg-danger" : pct >= 80 ? "bg-warning" : "bg-primary";
  return (
    <div className={cn("w-full", className)}>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-sunken" role="meter" aria-valuemin={0} aria-valuemax={max} aria-valuenow={value} aria-label={label}>
        <div className={cn("h-full rounded-full transition-[width] duration-300 ease-[var(--ease-standard)]", tone)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
