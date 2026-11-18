import { BarChart3, Table2 } from "lucide-react";
import * as React from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";
import { EmptyState, ErrorState } from "./states";

export interface ChartSeries {
  key: string;
  label: string;
  /** Slot 1–5 → --chart-N (fixed order). */
  slot?: 1 | 2 | 3 | 4 | 5;
}

/**
 * Chart frame with title, period/unit subtitle, accessible table toggle and loading/empty/error
 * states. Data must come from the API (UX-12) — there is no sample-data fallback.
 */
export function ChartCard<T extends Record<string, string | number>>({
  title, subtitle, data, xKey, series, type = "bar", formatValue = (v) => String(v), isLoading, error, onRetry,
  height = 240, className, emptyDescription,
}: {
  title: string; subtitle?: string; data: T[] | undefined; xKey: keyof T & string; series: ChartSeries[];
  type?: "bar" | "line"; formatValue?: (v: number) => string; isLoading?: boolean; error?: unknown; onRetry?: () => void;
  height?: number; className?: string; emptyDescription?: string;
}) {
  const [asTable, setAsTable] = React.useState(false);
  const color = (s: ChartSeries, i: number) => `var(--chart-${s.slot ?? ((i % 5) + 1)})`;

  return (
    <section className={cn("rounded-[var(--radius-panel)] border border-border bg-surface", className)}>
      <div className="flex items-start justify-between gap-3 px-4 pb-2 pt-3">
        <div>
          <h2 className="text-body font-semibold text-fg">{title}</h2>
          {subtitle && <p className="text-small text-fg-muted">{subtitle}</p>}
        </div>
        {data && data.length > 0 && (
          <Button size="icon" variant="ghost" aria-label={asTable ? "Show chart" : "Show as table"} aria-pressed={asTable} onClick={() => setAsTable((v) => !v)}>
            {asTable ? <BarChart3 /> : <Table2 />}
          </Button>
        )}
      </div>

      {series.length > 1 && !asTable && data && data.length > 0 && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 px-4 pb-1 text-small text-fg-secondary">
          {series.map((s, i) => (
            <li key={s.key} className="flex items-center gap-1.5"><span className="size-2 rounded-[2px]" style={{ background: color(s, i) }} />{s.label}</li>
          ))}
        </ul>
      )}

      <div className="px-2 pb-3" style={{ minHeight: height }}>
        {isLoading ? (
          <div className="flex items-end gap-3 px-4 pt-6" style={{ height }} aria-busy="true" aria-label="Loading chart">
            {[40, 65, 50, 80, 55, 70].map((h, i) => <Skeleton key={i} className="flex-1" style={{ height: `${h}%` }} />)}
          </div>
        ) : error ? (
          <ErrorState error={error} onRetry={onRetry} className="py-8" />
        ) : !data || data.length === 0 ? (
          <EmptyState title="No data for this period" description={emptyDescription ?? "Values appear here once records exist."} className="py-8" />
        ) : asTable ? (
          <div className="overflow-x-auto px-2">
            <table className="w-full text-body">
              <thead><tr className="border-b border-border text-left text-caption uppercase tracking-[0.04em] text-fg-muted">
                <th className="py-2 pr-4 font-medium">{xKey}</th>
                {series.map((s) => <th key={s.key} className="py-2 pr-4 text-right font-medium">{s.label}</th>)}
              </tr></thead>
              <tbody className="divide-y divide-border-subtle">
                {data.map((row, i) => (
                  <tr key={i}>
                    <td className="py-2 pr-4">{String(row[xKey])}</td>
                    {series.map((s) => <td key={s.key} className="tabular py-2 pr-4 text-right">{formatValue(Number(row[s.key]))}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={height}>
            {type === "bar" ? (
              <BarChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 4 }} barCategoryGap="28%">
                <CartesianGrid vertical={false} stroke="var(--border-subtle)" />
                <XAxis dataKey={(d: T) => d[xKey]} tickLine={false} axisLine={{ stroke: "var(--border)" }} tick={{ fill: "var(--text-muted)", fontSize: 12 }} />
                <YAxis tickLine={false} axisLine={false} width={56} tick={{ fill: "var(--text-muted)", fontSize: 12 }} tickFormatter={(v: number) => formatValue(v)} />
                <Tooltip content={<ChartTooltip formatValue={formatValue} />} cursor={{ fill: "var(--surface-sunken)" }} />
                {series.map((s, i) => <Bar key={s.key} dataKey={s.key} name={s.label} fill={color(s, i)} radius={[3, 3, 0, 0]} maxBarSize={36} />)}
              </BarChart>
            ) : (
              <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
                <CartesianGrid vertical={false} stroke="var(--border-subtle)" />
                <XAxis dataKey={(d: T) => d[xKey]} tickLine={false} axisLine={{ stroke: "var(--border)" }} tick={{ fill: "var(--text-muted)", fontSize: 12 }} />
                <YAxis tickLine={false} axisLine={false} width={56} tick={{ fill: "var(--text-muted)", fontSize: 12 }} tickFormatter={(v: number) => formatValue(v)} />
                <Tooltip content={<ChartTooltip formatValue={formatValue} />} cursor={{ stroke: "var(--border-strong)" }} />
                {series.map((s, i) => <Line key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={color(s, i)} strokeWidth={2} dot={false} activeDot={{ r: 4 }} />)}
              </LineChart>
            )}
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}

interface TooltipPayload { name?: string; value?: number; color?: string }

function ChartTooltip({ active, payload, label, formatValue }: { active?: boolean; payload?: TooltipPayload[]; label?: string; formatValue: (v: number) => string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-[var(--radius-control)] border border-border bg-surface px-3 py-2 text-small shadow-[var(--shadow-overlay)]">
      <p className="mb-1 font-medium text-fg">{label}</p>
      {payload.map((p) => (
        <p key={p.name} className="flex items-center gap-2 text-fg-secondary">
          <span className="size-2 rounded-[2px]" style={{ background: p.color }} />
          {p.name}: <span className="tabular font-medium text-fg">{formatValue(Number(p.value))}</span>
        </p>
      ))}
    </div>
  );
}
