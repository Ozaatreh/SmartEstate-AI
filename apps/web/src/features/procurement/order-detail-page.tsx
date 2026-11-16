import { Ban, CalendarClock, FileText, MapPin, Pencil, Send, Truck, UserRound } from "lucide-react";
import * as React from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Badge } from "@/components/system/badges";
import { DocumentHeader, MetaItem } from "@/components/system/business";
import { MoneyText } from "@/components/system/data-display";
import { ConfirmDialog } from "@/components/system/forms";
import { DescriptionList, Panel } from "@/components/system/layout-blocks";
import { ErrorState, ListSkeleton } from "@/components/system/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/primitives";
import { useCan } from "@/features/auth/auth-context";
import { ApiError } from "@/lib/api-client";
import { formatDate, formatDateTime } from "@/lib/format";
import { humanize } from "@/lib/status";
import { useOrder, useOrderMutations, type PurchaseOrderDetail } from "./api";
import { CancelOrderDialog, OrderFormDialog } from "./order-dialogs";
import { budgetNote } from "./orders-logic";

export default function OrderDetailPage() {
  const { id } = useParams();
  const q = useOrder(id);
  if (q.isPending) return <DetailSkeleton />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} className="min-h-[50vh]" />;
  return <OrderDetail order={q.data} />;
}

function OrderDetail({ order: o }: { order: PurchaseOrderDetail }) {
  const { issue } = useOrderMutations(o.id);
  const canReadBudgets = useCan("finance.budgets.read");
  const [editing, setEditing] = React.useState(false);
  const [cancelling, setCancelling] = React.useState(false);
  const [confirmIssue, setConfirmIssue] = React.useState(false);
  const can = (a: string) => o.allowed_actions.includes(a);
  const note = budgetNote(o);

  const doIssue = () => issue.mutate(undefined, {
    onSuccess: () => { toast.success(`${o.code} issued to ${o.supplier.name}`); setConfirmIssue(false); },
    onError: (e) => { toast.error(e instanceof ApiError ? e.message : "Couldn't issue the order"); setConfirmIssue(false); },
  });

  return (
    <>
      <DocumentHeader
        back={{ to: "/procurement/orders", label: "Purchase orders" }}
        code={o.code}
        title={o.supplier.name}
        status={o.status}
        amount={o.total_amount}
        amountLabel="Order total"
        meta={<>
          <MetaItem icon={<FileText />}><Link className="underline-offset-2 hover:underline" to={`/procurement/requests/${o.request_id}`}>{o.request_code} · {o.request_title}</Link></MetaItem>
          {o.expected_delivery_date && <MetaItem icon={<CalendarClock />}>Delivery {formatDate(o.expected_delivery_date)}</MetaItem>}
          {o.delivery_address && <MetaItem icon={<MapPin />}>{o.delivery_address}</MetaItem>}
          {o.replaces && <Badge tone="info" dot={false}>Replaces <Link className="ml-1 underline" to={`/procurement/orders/${o.replaces.id}`}>{o.replaces.code}</Link></Badge>}
        </>}
        actions={<>
          {can("edit") && <Button onClick={() => setEditing(true)}><Pencil /> Edit</Button>}
          {can("cancel") && <Button variant="ghost" onClick={() => setCancelling(true)}><Ban /> Cancel order</Button>}
          {can("issue") && <Button variant="primary" onClick={() => setConfirmIssue(true)}><Send /> Issue to supplier</Button>}
        </>}
      />

      {o.status === "cancelled" && (
        <p className="mb-6 rounded-[var(--radius-panel)] border border-border bg-surface-subtle px-4 py-3 text-body text-fg-secondary">
          Cancelled {o.cancelled_by ? `by ${o.cancelled_by} ` : ""}{formatDateTime(o.cancelled_at)}: “{o.cancel_reason}”
          {o.replaced_by && <> · Replaced by <Link className="font-medium text-fg underline" to={`/procurement/orders/${o.replaced_by.id}`}>{o.replaced_by.code}</Link></>}
        </p>
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-4">
          <Panel title="Order lines" description="Copied from the approved quotation — quantities and agreed prices">
            <div className="overflow-x-auto">
              <table className="w-full text-body">
                <thead className="bg-surface-subtle"><tr className="border-b border-border text-left text-caption uppercase tracking-[0.04em] text-fg-muted">
                  <th className="h-9 w-10 px-4 font-medium">#</th><th className="px-4 font-medium">Description</th><th className="px-4 text-right font-medium">Qty</th>
                  <th className="hidden px-4 text-right font-medium sm:table-cell">Unit price</th><th className="px-4 text-right font-medium">Total</th>
                </tr></thead>
                <tbody className="divide-y divide-border-subtle">
                  {o.lines.map((l) => (
                    <tr key={l.id} className="h-10">
                      <td className="tabular px-4 text-fg-muted">{l.line_no}</td>
                      <td className="px-4">{l.description}</td>
                      <td className="tabular whitespace-nowrap px-4 text-right">{Number(l.quantity).toLocaleString("en-US", { maximumFractionDigits: 3 })} <span className="text-fg-muted">{l.unit}</span></td>
                      <td className="hidden px-4 text-right sm:table-cell"><MoneyText value={l.unit_price} decimals={2} /></td>
                      <td className="px-4 text-right"><MoneyText value={l.line_total} decimals={2} /></td>
                    </tr>
                  ))}
                </tbody>
                <tfoot><tr className="border-t border-border bg-surface-subtle"><td colSpan={4} className="px-4 py-2.5 font-medium">Order total</td>
                  <td className="px-4 text-right"><MoneyText value={o.total_amount} decimals={2} className="font-semibold" /></td></tr></tfoot>
              </table>
            </div>
          </Panel>
          {o.notes && <Panel title="Notes for the supplier"><p className="whitespace-pre-line p-4 text-body text-fg-secondary">{o.notes}</p></Panel>}
        </div>

        <aside className="space-y-4">
          <Panel title="Budget" description="One commitment per approved request">
            <div className="space-y-3 p-4">
              <div className="flex items-baseline justify-between gap-3"><span className="text-small text-fg-secondary">Committed</span><MoneyText value={o.committed_amount} decimals={2} className="font-semibold" /></div>
              {o.released_amount && <div className="flex items-baseline justify-between gap-3"><span className="text-small text-fg-secondary">Released</span><MoneyText value={o.released_amount} decimals={2} className="font-semibold text-success" /></div>}
              <p className="text-small text-fg-muted"><Badge tone={note.tone} dot={false} className="mr-1">{o.status === "cancelled" ? (o.budget_released ? "Released" : "Kept") : "Committed"}</Badge>{note.text}</p>
              {canReadBudgets && <p className="text-small"><Link className="text-brand underline-offset-2 hover:underline" to={`/procurement/requests/${o.request_id}`}>View the request's budget impact →</Link></p>}
            </div>
          </Panel>
          <Panel title="Details">
            <DescriptionList items={[
              { label: "Supplier", value: `${o.supplier.code} · ${o.supplier.name}` },
              { label: "Payment terms", value: o.payment_terms ?? "—" },
              { label: "Request status", value: humanize(o.request_status) },
              { label: "Created", value: <span className="inline-flex items-center gap-1"><UserRound className="size-3.5 text-fg-muted" />{o.created_by ?? "—"} · {formatDateTime(o.created_at)}</span> },
              { label: "Issued", value: o.issued_at ? <span className="inline-flex items-center gap-1"><Truck className="size-3.5 text-fg-muted" />{o.issued_by ?? "—"} · {formatDateTime(o.issued_at)}</span> : "Not issued" },
            ]} />
          </Panel>
        </aside>
      </div>

      {editing && <OrderFormDialog order={o} onClose={() => setEditing(false)} />}
      {cancelling && <CancelOrderDialog order={o} onClose={() => setCancelling(false)} />}
      <ConfirmDialog open={confirmIssue} onOpenChange={setConfirmIssue} loading={issue.isPending} onConfirm={doIssue}
        title={`Issue ${o.code} to ${o.supplier.name}?`} confirmLabel="Issue order"
        description={<>Total <MoneyText value={o.total_amount} decimals={2} className="font-medium text-fg" />. Issuing doesn't touch the budget — it was committed at approval. Delivery details are locked afterwards.</>} />
    </>
  );
}

function DetailSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading purchase order">
      <Skeleton className="mb-2 h-4 w-24" /><Skeleton className="mb-6 h-8 w-80 max-w-full" />
      <div className="grid gap-6 xl:grid-cols-[1fr_360px]"><div className="rounded-[var(--radius-panel)] border border-border bg-surface"><ListSkeleton rows={4} /></div>
        <div className="rounded-[var(--radius-panel)] border border-border bg-surface"><ListSkeleton rows={3} /></div></div>
    </div>
  );
}
