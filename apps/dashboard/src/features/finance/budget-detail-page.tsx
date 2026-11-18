import { Pencil, ReceiptText } from "lucide-react";
import * as React from "react";
import { Link, useParams } from "react-router-dom";
import { Badge, StatusBadge } from "@/components/system/badges";
import { KpiCard, Meter, MoneyText } from "@/components/system/data-display";
import { PageHeader, Panel } from "@/components/system/layout-blocks";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/system/states";
import { Button } from "@/components/ui/button";
import { useCan } from "@/features/auth/auth-context";
import { formatDateTime, formatMoney, formatPercent } from "@/lib/format";
import { humanize } from "@/lib/status";
import { useBudget } from "./api";
import { BudgetFormDialog } from "./budget-dialogs";

const ENTRY_TONE = { commitment: "brand", release: "success", actual: "info", adjustment: "neutral" } as const;

export default function BudgetDetailPage() {
  const { id } = useParams();
  const q = useBudget(id);
  const canManage = useCan("finance.budgets.manage");
  const [editing, setEditing] = React.useState(false);

  if (q.isPending) return <div className="rounded-[var(--radius-panel)] border border-border bg-surface"><ListSkeleton rows={6} /></div>;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} className="min-h-[50vh]" />;
  const b = q.data;
  const p = b.position;
  const owner = b.project ? `${b.project.code} · ${b.project.name}` : `${b.department?.name} department`;
  const used = Number(p.utilisation_pct);

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: "Budgets", to: "/finance/budgets" }, { label: `FY${b.fiscal_year}` }]}
        title={`${b.category.name} · ${owner}`}
        description={b.notes ?? `FY${b.fiscal_year} ${b.scope === "project" ? "project" : "department"} budget owned by ${b.owner_department.name}.`}
        meta={<StatusBadge status={b.status} />}
        actions={canManage && <Button onClick={() => setEditing(true)}><Pencil /> Change allocation</Button>}
      />
      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="Allocated" value={formatMoney(p.allocated)} hint={p.adjustments !== "0.00" ? `${formatMoney(p.adjustments)} adjustments` : undefined} />
        <KpiCard label="Committed" value={formatMoney(p.committed)} hint="approved purchase requests" />
        <KpiCard label="Actual spend" value={formatMoney(p.actual)} hint="recorded invoices and expenses" />
        <KpiCard label="Available" value={<span className={Number(p.available) < 0 ? "text-danger" : undefined}>{formatMoney(p.available)}</span>} />
      </div>
      <Panel title="Utilisation" className="mb-6">
        <div className="flex items-center gap-4 p-4">
          <Meter value={used} label="Budget utilisation" className="flex-1" />
          <span className={`tabular text-lead font-semibold ${used >= 100 ? "text-danger" : used >= 80 ? "text-warning" : ""}`}>{formatPercent(used)}</span>
        </div>
      </Panel>
      <Panel title="Ledger" description="Append-only record of every commitment, release and actual. Entries are never edited.">
        {b.ledger.length === 0 ? (
          <EmptyState icon={<ReceiptText className="size-5" />} title="No movements yet" description="Approved purchase requests appear here as commitments." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-body">
              <thead className="bg-surface-subtle"><tr className="border-b border-border text-left text-caption uppercase tracking-[0.04em] text-fg-muted">
                <th className="h-9 px-4 font-medium">Date</th><th className="px-4 font-medium">Type</th><th className="px-4 font-medium">Source</th>
                <th className="hidden px-4 font-medium md:table-cell">Description</th><th className="px-4 text-right font-medium">Amount</th>
              </tr></thead>
              <tbody className="divide-y divide-border-subtle">
                {b.ledger.map((e) => (
                  <tr key={e.id} className="h-10">
                    <td className="tabular whitespace-nowrap px-4 text-small text-fg-secondary">{formatDateTime(e.created_at)}</td>
                    <td className="px-4"><Badge tone={ENTRY_TONE[e.entry_type]}>{humanize(e.entry_type)}</Badge></td>
                    <td className="px-4">
                      {e.source_type === "purchase_request" ? <Link className="tabular font-medium text-brand hover:underline" to={`/procurement/requests/${e.source_id}`}>{e.source_code}</Link> : e.source_code}
                    </td>
                    <td className="hidden max-w-md truncate px-4 text-small text-fg-secondary md:table-cell">{e.description}</td>
                    <td className="px-4 text-right"><MoneyText value={e.amount} decimals={2} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      {canManage && <BudgetFormDialog open={editing} onOpenChange={setEditing} fiscalYear={b.fiscal_year} budget={b} />}
    </>
  );
}
