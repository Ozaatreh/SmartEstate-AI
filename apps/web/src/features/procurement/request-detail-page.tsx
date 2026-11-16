import {
  Award, Ban, Building2, CalendarClock, Check, CheckCircle2, FolderKanban, Pencil, Plus, Send, Timer, Trash2, Truck, UserRound, XCircle,
} from "lucide-react";
import * as React from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Badge, StatusBadge } from "@/components/system/badges";
import { ApprovalTimeline, BudgetImpactCard, DocumentHeader, MetaItem, PriorityBadge } from "@/components/system/business";
import { MoneyText } from "@/components/system/data-display";
import { ConfirmDialog, FormField } from "@/components/system/forms";
import { DescriptionList, Panel } from "@/components/system/layout-blocks";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/system/states";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/input";
import { Skeleton, Tabs, TabsContent, TabsList, TabsTrigger, Tooltip } from "@/components/ui/primitives";
import { useCan } from "@/features/auth/auth-context";
import { DecisionDialog } from "@/features/approvals/decision-dialog";
import { ApiError } from "@/lib/api-client";
import { formatDate, formatDateTime, formatMoney, formatRelative } from "@/lib/format";
import { humanize } from "@/lib/status";
import { cn } from "@/lib/utils";
import { useQuotationMutations, useRequest, useRequestAction, useRequestActivity, type PurchaseRequestDetail, type Quotation } from "./api";
import { QuotationDialog } from "./quotation-dialog";

const ACTION_LABELS: Record<string, string> = {
  "purchase_request.created": "created the request",
  "purchase_request.updated": "edited the draft",
  "purchase_request.submitted": "submitted it for sourcing",
  "purchase_request.quotation_added": "recorded a quotation",
  "purchase_request.quotation_updated": "updated a quotation",
  "purchase_request.quotation_removed": "removed a quotation",
  "purchase_request.quotation_selected": "selected a supplier",
  "purchase_request.sent_for_approval": "sent it for approval",
  "purchase_request.approved": "committed the budget",
  "purchase_request.rejected": "closed it as rejected",
  "purchase_request.cancelled": "cancelled the request",
  "approval.requested": "opened the approval route",
  "approval.step_approved": "approved a step",
  "approval.rejected": "rejected it",
  "approval.completed": "gave final approval",
};

const STAGES = [
  { key: "draft", label: "Draft" },
  { key: "sourcing", label: "Sourcing" },
  { key: "pending_approval", label: "Approval" },
  { key: "approved", label: "Approved" },
] as const;

export default function RequestDetailPage() {
  const { id } = useParams();
  const q = useRequest(id);
  if (q.isPending) return <DetailSkeleton />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} className="min-h-[50vh]" />;
  return <RequestDetail pr={q.data} />;
}

function RequestDetail({ pr }: { pr: PurchaseRequestDetail }) {
  const action = useRequestAction(pr.id);
  const canReadBudgets = useCan("finance.budgets.read");
  const [decision, setDecision] = React.useState<"approve" | "reject" | null>(null);
  const [cancelling, setCancelling] = React.useState(false);
  const [confirmSend, setConfirmSend] = React.useState(false);
  const [quote, setQuote] = React.useState<Quotation | "new" | null>(null);
  const can = (a: string) => pr.allowed_actions.includes(a);
  const [tab, setTab] = React.useState(pr.status === "sourcing" && can("manage_quotations") ? "quotations" : "overview");

  const run = (name: "submit" | "send-for-approval", ok: string) => action.mutate({ action: name }, {
    onSuccess: () => { toast.success(ok); setConfirmSend(false); },
    onError: (e) => { toast.error(e instanceof ApiError ? e.message : "Action failed"); setConfirmSend(false); },
  });
  const selected = pr.quotations.find((x) => x.id === pr.selected_quotation_id);

  return (
    <>
      <DocumentHeader
        back={{ to: "/procurement/requests", label: "Purchase requests" }}
        code={pr.code}
        title={pr.title}
        status={pr.status}
        amount={pr.approved_total ?? pr.estimated_total}
        amountLabel={pr.approved_total ? (pr.status === "approved" ? "Approved amount" : "Selected quotation") : "Estimated total"}
        meta={<>
          <MetaItem icon={<UserRound />}>{pr.requester.full_name}</MetaItem>
          <MetaItem icon={pr.project ? <FolderKanban /> : <Building2 />}>{pr.project ? `${pr.project.code} · ${pr.project.name}` : pr.department.name}</MetaItem>
          {pr.needed_by && <MetaItem icon={<CalendarClock />}>Needed by {formatDate(pr.needed_by)}</MetaItem>}
          <PriorityBadge priority={pr.priority} />
          {pr.over_budget && <Badge tone="danger">Over budget</Badge>}
        </>}
        actions={<>
          {can("edit") && <Button asChild><Link to={`/procurement/requests/${pr.id}/edit`}><Pencil /> Edit</Link></Button>}
          {can("cancel") && <Button variant="ghost" onClick={() => setCancelling(true)}><Ban /> Cancel request</Button>}
          {can("submit") && <Button variant="primary" loading={action.isPending} onClick={() => run("submit", `${pr.code} submitted for sourcing`)}><Send /> Submit</Button>}
          {can("send_for_approval") && <Button variant="primary" onClick={() => setConfirmSend(true)}><Send /> Send for approval</Button>}
          {can("reject") && <Button variant="danger" onClick={() => setDecision("reject")}><XCircle /> Reject</Button>}
          {can("approve") && <Button variant="primary" onClick={() => setDecision("approve")}><CheckCircle2 /> Approve</Button>}
        </>}
      />

      <LifecycleStepper status={pr.status} />

      {pr.approval?.status === "pending" && pr.approval.blocked_reason && !can("approve") && (
        <p className="mb-6 flex items-center gap-2 rounded-[var(--radius-panel)] border border-border bg-surface px-4 py-3 text-body text-fg-secondary">
          <Timer className="size-4 text-warning" />{pr.waiting_on ? `Waiting on ${pr.waiting_on}.` : pr.approval.blocked_reason}
        </p>
      )}
      {pr.status === "cancelled" && pr.cancel_reason && (
        <p className="mb-6 rounded-[var(--radius-panel)] border border-border bg-surface-subtle px-4 py-3 text-body text-fg-secondary">Cancelled: “{pr.cancel_reason}”</p>
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Tabs value={tab} onValueChange={setTab} className="min-w-0">
          <TabsList className="mb-4">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="quotations">Quotations <span className="tabular ml-1 text-fg-muted">{pr.quotations.length}</span></TabsTrigger>
            <TabsTrigger value="activity">Activity</TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-4">
            <Panel title="Justification"><p className="whitespace-pre-line p-4 text-body text-fg-secondary">{pr.justification}</p></Panel>
            <ItemsPanel pr={pr} />
          </TabsContent>

          <TabsContent value="quotations" className="space-y-4">
            <QuotationsPanel pr={pr} onAdd={() => setQuote("new")} onEdit={(x) => setQuote(x)} />
          </TabsContent>

          <TabsContent value="activity"><ActivityPanel id={pr.id} /></TabsContent>
        </Tabs>

        <aside className="space-y-4">
          <Panel title="Budget impact" description={pr.budget_impact.committed_by_this_request ? "Committed on approval" : "Checked live against the budget"}>
            <div className="p-4"><BudgetImpactCard impact={{ ...pr.budget_impact, budgetLink: canReadBudgets && pr.budget_impact.budget_id ? `/finance/budgets/${pr.budget_impact.budget_id}` : null }} compact /></div>
          </Panel>
          <Panel title="Approval" description={pr.approval ? pr.approval.policy_name : "Starts when procurement sends the request"}>
            <div className="p-4">
              {pr.approval ? <ApprovalTimeline steps={pr.approval.steps} /> : (
                <p className="text-small text-fg-muted">Route: {pr.budget_impact.approval_levels.join(" → ") || "—"}</p>
              )}
            </div>
          </Panel>
          <Panel title="Details">
            <DescriptionList items={[
              { label: "Department", value: pr.department.name },
              { label: "Project", value: pr.project ? `${pr.project.code} · ${pr.project.name}` : "—" },
              { label: "Category", value: `${pr.category} · FY${pr.fiscal_year}` },
              { label: "Supplier", value: selected ? selected.supplier.name : "Not selected" },
              { label: "Created", value: formatDateTime(pr.created_at) },
              { label: "Submitted", value: formatDateTime(pr.submitted_at) },
              { label: "Decided", value: formatDateTime(pr.decided_at) },
            ]} />
          </Panel>
        </aside>
      </div>

      {decision && pr.approval && <DecisionDialog approval={pr.approval} decision={decision} onClose={() => setDecision(null)} />}
      {quote && <QuotationDialog request={pr} quotation={quote === "new" ? undefined : quote} onClose={() => setQuote(null)} />}
      {cancelling && <CancelDialog pr={pr} onClose={() => setCancelling(false)} />}
      <ConfirmDialog open={confirmSend} onOpenChange={setConfirmSend} loading={action.isPending} onConfirm={() => run("send-for-approval", `${pr.code} sent for approval`)}
        title={`Send ${pr.code} for approval?`} confirmLabel="Send for approval"
        description={selected ? <>
          {selected.supplier.name} · <MoneyText value={selected.total_amount} decimals={2} className="font-medium text-fg" />. Route: {pr.budget_impact.approval_levels.join(" → ")}.
          {pr.budget_impact.over_budget && <span className="mt-1 block text-danger">This exceeds the available budget.</span>}
          <span className="mt-1 block">Quotations are locked after sending.</span>
        </> : undefined} />
    </>
  );
}

function LifecycleStepper({ status }: { status: string }) {
  const terminal = status === "rejected" || status === "cancelled";
  const idx = STAGES.findIndex((s) => s.key === status);
  return (
    <ol className="mb-6 flex items-center gap-2 overflow-x-auto rounded-[var(--radius-panel)] border border-border bg-surface px-4 py-3 [scrollbar-width:none]" aria-label="Request progress">
      {STAGES.map((s, i) => {
        const done = !terminal && (i < idx || status === "approved");
        const current = !terminal && i === idx && status !== "approved";
        return (
          <li key={s.key} className="flex shrink-0 items-center gap-2">
            {i > 0 && <span aria-hidden className={cn("h-px w-6 sm:w-12", done || current ? "bg-success/50" : "bg-border")} />}
            <span className={cn("grid size-5 place-items-center rounded-full text-[11px] font-semibold",
              done ? "bg-success text-white" : current ? "bg-brand text-white" : "bg-surface-sunken text-fg-muted")}>
              {done ? <Check className="size-3" /> : i + 1}
            </span>
            <span className={cn("text-small", current ? "font-medium text-fg" : done ? "text-fg-secondary" : "text-fg-muted")} aria-current={current ? "step" : undefined}>{s.label}</span>
          </li>
        );
      })}
      {terminal && <li className="ml-auto shrink-0 pl-4"><StatusBadge status={status} /></li>}
    </ol>
  );
}

function ItemsPanel({ pr }: { pr: PurchaseRequestDetail }) {
  return (
    <Panel title="Items" description={`${pr.items.length} line${pr.items.length === 1 ? "" : "s"} · estimates from the requester`}>
      <div className="overflow-x-auto">
        <table className="w-full text-body">
          <thead className="bg-surface-subtle"><tr className="border-b border-border text-left text-caption uppercase tracking-[0.04em] text-fg-muted">
            <th className="h-9 w-10 px-4 font-medium">#</th><th className="px-4 font-medium">Description</th><th className="px-4 text-right font-medium">Qty</th>
            <th className="hidden px-4 text-right font-medium sm:table-cell">Unit price</th><th className="px-4 text-right font-medium">Total</th>
          </tr></thead>
          <tbody className="divide-y divide-border-subtle">
            {pr.items.map((i) => (
              <tr key={i.id} className="h-10">
                <td className="tabular px-4 text-fg-muted">{i.line_no}</td>
                <td className="px-4">{i.description}</td>
                <td className="tabular whitespace-nowrap px-4 text-right">{Number(i.quantity).toLocaleString("en-US", { maximumFractionDigits: 3 })} <span className="text-fg-muted">{i.unit}</span></td>
                <td className="hidden px-4 text-right sm:table-cell"><MoneyText value={i.estimated_unit_price} decimals={2} /></td>
                <td className="px-4 text-right"><MoneyText value={i.line_total} decimals={2} /></td>
              </tr>
            ))}
          </tbody>
          <tfoot><tr className="border-t border-border bg-surface-subtle"><td colSpan={4} className="px-4 py-2.5 font-medium">Estimated total</td>
            <td className="px-4 text-right"><MoneyText value={pr.estimated_total} decimals={2} className="font-semibold" /></td></tr></tfoot>
        </table>
      </div>
    </Panel>
  );
}

function QuotationsPanel({ pr, onAdd, onEdit }: { pr: PurchaseRequestDetail; onAdd: () => void; onEdit: (q: Quotation) => void }) {
  const manage = pr.allowed_actions.includes("manage_quotations");
  const { select, remove } = useQuotationMutations(pr.id);
  const [removing, setRemoving] = React.useState<Quotation | null>(null);
  const quotes = pr.quotations;
  const cmp = pr.comparison;

  if (!quotes.length) {
    return (
      <Panel title="Supplier quotations">
        <EmptyState icon={<Truck className="size-5" />} title={pr.status === "draft" ? "Submit the request to start sourcing" : "No quotations yet"}
          description={manage ? "Record at least one supplier quotation, compare them and select the best offer." : "Procurement records supplier quotations here."}
          action={manage && <Button variant="primary" size="sm" onClick={onAdd}><Plus /> Record quotation</Button>} />
      </Panel>
    );
  }

  return (
    <>
      <Panel title="Comparison" description={cmp.savings_vs_estimate && cmp.savings_vs_estimate !== "0.00"
        ? `Best offer is ${cmp.savings_vs_estimate.startsWith("-") ? "above" : "below"} the estimate by ${formatMoney(cmp.savings_vs_estimate.replace("-", ""), { decimals: 2 })}` : "Unit prices by supplier"}
        actions={manage && <Button size="sm" onClick={onAdd}><Plus /> Add quotation</Button>}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-body">
            <thead className="bg-surface-subtle"><tr className="border-b border-border text-left text-caption uppercase tracking-[0.04em] text-fg-muted">
              <th className="h-9 px-4 font-medium">Item</th>
              <th className="px-4 text-right font-medium">Estimate</th>
              {quotes.map((x) => (
                <th key={x.id} className={cn("px-4 text-right font-medium", x.status === "selected" && "bg-success-subtle/60 text-success")}>
                  <span className="block truncate normal-case tracking-normal text-small text-fg" title={x.supplier.name}>{x.supplier.name}</span>
                </th>
              ))}
            </tr></thead>
            <tbody className="divide-y divide-border-subtle">
              {cmp.rows.map((r) => (
                <tr key={r.request_item_id} className="h-10">
                  <td className="px-4"><span className="block">{r.description}</span><span className="tabular text-caption text-fg-muted">{Number(r.quantity).toLocaleString("en-US")} {r.unit}</span></td>
                  <td className="px-4 text-right text-fg-muted"><MoneyText value={r.estimated_unit_price} decimals={2} /></td>
                  {quotes.map((x) => {
                    const c = r.cells.find((cell) => cell.quotation_id === x.id);
                    return (
                      <td key={x.id} className={cn("px-4 text-right", x.status === "selected" && "bg-success-subtle/40")}>
                        {c ? <span className={cn(c.is_lowest && quotes.length > 1 && "font-semibold text-success")}><MoneyText value={c.unit_price} decimals={2} /></span> : "—"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-border bg-surface-subtle">
                <td className="px-4 py-2.5 font-medium" colSpan={2}>Total</td>
                {quotes.map((x) => (
                  <td key={x.id} className={cn("px-4 text-right", x.status === "selected" && "bg-success-subtle/60")}>
                    <MoneyText value={x.total_amount} decimals={2} className={cn("font-semibold", x.is_lowest && quotes.length > 1 && "text-success")} />
                  </td>
                ))}
              </tr>
            </tfoot>
          </table>
        </div>
      </Panel>

      <ul className="grid gap-3 md:grid-cols-2">
        {quotes.map((x) => (
          <li key={x.id} className={cn("rounded-[var(--radius-panel)] border bg-surface p-4", x.status === "selected" ? "border-success/50 shadow-[inset_0_0_0_1px_var(--success)]" : "border-border")}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate font-medium">{x.supplier.name}</p>
                <p className="tabular text-caption text-fg-muted">{x.supplier.code}{x.reference ? ` · Ref ${x.reference}` : ""}{x.supplier_rating ? ` · ★ ${x.supplier_rating}` : ""}</p>
              </div>
              <div className="flex shrink-0 flex-wrap justify-end gap-1">
                {x.status === "selected" && <Badge tone="success"><Check className="size-3" /> Selected</Badge>}
                {x.is_lowest && quotes.length > 1 && <Badge tone="brand" dot={false}><Award className="size-3" /> Lowest</Badge>}
                {cmp.fastest_quotation_id === x.id && quotes.length > 1 && <Badge tone="info" dot={false}><Truck className="size-3" /> Fastest</Badge>}
              </div>
            </div>
            <MoneyText value={x.total_amount} decimals={2} className="mt-3 block text-h3 font-semibold" />
            {!x.is_lowest && <p className="text-small text-fg-muted">+<MoneyText value={x.difference_from_lowest} decimals={2} /> vs lowest</p>}
            <dl className="mt-3 grid grid-cols-2 gap-2 text-small">
              <div><dt className="text-fg-muted">Delivery</dt><dd>{x.delivery_days !== null ? `${x.delivery_days} days` : "—"}</dd></div>
              <div><dt className="text-fg-muted">Valid until</dt><dd>{formatDate(x.valid_until)}</dd></div>
              <div className="col-span-2"><dt className="text-fg-muted">Payment terms</dt><dd>{x.payment_terms ?? "—"}</dd></div>
            </dl>
            {manage && (
              <div className="mt-4 flex flex-wrap gap-2 border-t border-border-subtle pt-3">
                {x.status !== "selected" && (
                  <Button size="sm" variant="primary" loading={select.isPending && select.variables === x.id}
                    onClick={() => select.mutate(x.id, { onSuccess: () => toast.success(`${x.supplier.name} selected`), onError: (e) => toast.error(e instanceof ApiError ? e.message : "Couldn't select") })}>
                    <Check /> Select
                  </Button>
                )}
                <Button size="sm" onClick={() => onEdit(x)}><Pencil /> Edit</Button>
                <Tooltip content="Remove quotation"><Button size="icon" variant="ghost" aria-label={`Remove quotation from ${x.supplier.name}`} onClick={() => setRemoving(x)}><Trash2 /></Button></Tooltip>
              </div>
            )}
          </li>
        ))}
      </ul>
      <ConfirmDialog open={removing !== null} onOpenChange={(o) => !o && setRemoving(null)} tone="danger" loading={remove.isPending}
        title={`Remove the quotation from ${removing?.supplier.name}?`} confirmLabel="Remove quotation"
        description={removing?.status === "selected" ? "It is currently selected; you'll need to select another quotation." : "You can record it again later."}
        onConfirm={() => removing && remove.mutate(removing.id, { onSuccess: () => { toast.success("Quotation removed"); setRemoving(null); } })} />
    </>
  );
}

function ActivityPanel({ id }: { id: string }) {
  const q = useRequestActivity(id);
  return (
    <Panel title="Activity" description="Every action on this request, from the audit trail">
      {q.isPending ? <ListSkeleton rows={4} /> : q.isError ? <ErrorState error={q.error} onRetry={() => void q.refetch()} /> : (
        <ol className="p-4">
          {q.data.map((a, i) => (
            <li key={a.id} className="relative flex gap-3 pb-4 last:pb-0">
              {i < q.data.length - 1 && <span aria-hidden className="absolute left-[5px] top-4 h-full w-px bg-border" />}
              <span className={cn("relative mt-1.5 size-[11px] shrink-0 rounded-full border-2 border-surface", /rejected|cancelled/.test(a.action) ? "bg-danger" : /approved|completed/.test(a.action) ? "bg-success" : "bg-border-strong")} />
              <div className="min-w-0">
                <p className="text-body"><span className="font-medium">{a.actor?.full_name ?? "System"}</span> <span className="text-fg-secondary">{ACTION_LABELS[a.action] ?? humanize(a.action.split(".")[1] ?? a.action).toLowerCase()}</span></p>
                {a.summary && <p className="text-small text-fg-muted">{a.summary}</p>}
                <p className="text-caption text-fg-muted" title={formatDateTime(a.created_at)}>{formatRelative(a.created_at)}</p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}

function CancelDialog({ pr, onClose }: { pr: PurchaseRequestDetail; onClose: () => void }) {
  const action = useRequestAction(pr.id);
  const [reason, setReason] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (reason.trim().length < 3) return setError("Give a short reason (at least 3 characters).");
    action.mutate({ action: "cancel", body: { reason } }, {
      onSuccess: () => { toast.success(`${pr.code} cancelled`); onClose(); },
      onError: (err) => setError(err instanceof ApiError ? err.message : "Couldn't cancel"),
    });
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader title={`Cancel ${pr.code}?`} description="The request stops here. This can't be undone." />
        <form onSubmit={submit} noValidate className="space-y-4">
          <FormField label="Reason" htmlFor="cancel-reason" error={error ?? undefined} required>
            <Textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus />
          </FormField>
          <DialogFooter>
            <Button type="button" onClick={onClose}>Keep request</Button>
            <Button type="submit" variant="danger" loading={action.isPending}><Ban /> Cancel request</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function DetailSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading request">
      <Skeleton className="mb-2 h-4 w-24" /><Skeleton className="mb-6 h-8 w-96 max-w-full" /><Skeleton className="mb-6 h-12 w-full" />
      <div className="grid gap-6 xl:grid-cols-[1fr_380px]"><div className="rounded-[var(--radius-panel)] border border-border bg-surface"><ListSkeleton rows={5} /></div>
        <div className="rounded-[var(--radius-panel)] border border-border bg-surface"><ListSkeleton rows={3} /></div></div>
    </div>
  );
}
