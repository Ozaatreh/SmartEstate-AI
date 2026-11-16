import { Ban, FilePlus2, Save } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { MoneyText } from "@/components/system/data-display";
import { FormAlert, FormField } from "@/components/system/forms";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { ApiError } from "@/lib/api-client";
import { formatMoney } from "@/lib/format";
import { cn } from "@/lib/utils";
import { CANCEL_OPTIONS } from "./orders-logic";
import { useCreateOrder, useOrderMutations, type OrderInput, type PurchaseOrderDetail, type PurchaseRequestDetail } from "./api";

const blank = (v: string) => (v.trim() ? v.trim() : null);

/** Create (from an approved request) or edit a draft order. Only delivery details are editable — lines and prices come from the approved quotation. */
export function OrderFormDialog({ request, order, onClose }: { request?: PurchaseRequestDetail; order?: PurchaseOrderDetail; onClose: () => void }) {
  const navigate = useNavigate();
  const create = useCreateOrder(request?.id ?? order?.request_id ?? "");
  const { update } = useOrderMutations(order?.id ?? "");
  const [date, setDate] = React.useState(order?.expected_delivery_date ?? "");
  const [address, setAddress] = React.useState(order?.delivery_address ?? "");
  const [terms, setTerms] = React.useState(order?.payment_terms ?? "");
  const [notes, setNotes] = React.useState(order?.notes ?? "");
  const [error, setError] = React.useState<string | null>(null);
  const selected = request?.quotations.find((q) => q.id === request.selected_quotation_id);
  const pending = create.isPending || update.isPending;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const body: OrderInput = { expected_delivery_date: blank(date), delivery_address: blank(address), notes: blank(notes) };
    const onError = (err: unknown) => setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    if (order) {
      update.mutate({ ...body, payment_terms: blank(terms) }, { onSuccess: () => { toast.success(`${order.code} updated`); onClose(); }, onError });
    } else {
      create.mutate(body, {
        onSuccess: (po) => { toast.success(`${po.code} drafted`, { description: "Review it, then issue it to the supplier." }); onClose(); navigate(`/procurement/orders/${po.id}`); },
        onError,
      });
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader
          title={order ? `Edit ${order.code}` : `Create a purchase order for ${request?.code}`}
          description={order ? "Delivery details only. Lines and prices are fixed by the approved quotation." : undefined}
        />
        {!order && selected && (
          <div className="mb-4 rounded-[var(--radius-panel)] border border-border bg-surface-subtle px-4 py-3 text-small">
            <p className="font-medium text-fg">{selected.supplier.name} · <MoneyText value={selected.total_amount} decimals={2} /></p>
            <p className="text-fg-secondary">{request?.items.length} line{request?.items.length === 1 ? "" : "s"} copied from the approved quotation. The budget is already committed for this request — the order adds no second commitment.</p>
          </div>
        )}
        <form onSubmit={submit} noValidate className="space-y-4">
          <FormAlert message={error} />
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Expected delivery" htmlFor="po-date"><Input id="po-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></FormField>
            {order && <FormField label="Payment terms" htmlFor="po-terms"><Input id="po-terms" maxLength={120} value={terms} onChange={(e) => setTerms(e.target.value)} /></FormField>}
          </div>
          <FormField label="Delivery address" htmlFor="po-address"><Input id="po-address" maxLength={300} value={address} onChange={(e) => setAddress(e.target.value)} placeholder="Site, gate or warehouse" /></FormField>
          <FormField label="Notes for the supplier" htmlFor="po-notes"><Textarea id="po-notes" rows={3} maxLength={2000} value={notes} onChange={(e) => setNotes(e.target.value)} /></FormField>
          <DialogFooter>
            <Button type="button" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" loading={pending}>{order ? <><Save /> Save changes</> : <><FilePlus2 /> Create draft order</>}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}


export function CancelOrderDialog({ order, onClose }: { order: PurchaseOrderDetail; onClose: () => void }) {
  const { cancel } = useOrderMutations(order.id);
  const [reason, setReason] = React.useState("");
  const [choice, setChoice] = React.useState<"release" | "keep" | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [fieldError, setFieldError] = React.useState<{ reason?: string; choice?: string }>({});

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const errs = {
      reason: reason.trim().length < 3 ? "Give a short reason (at least 3 characters)." : undefined,
      choice: choice === null ? "Choose what happens to the committed budget." : undefined,
    };
    setFieldError(errs);
    if (errs.reason || errs.choice) return;
    cancel.mutate({ reason: reason.trim(), release_budget: choice === "release" }, {
      onSuccess: () => {
        toast.success(`${order.code} cancelled`, { description: choice === "release" ? `Budget released and ${order.request_code} closed.` : "Commitment kept for a replacement order." });
        onClose();
      },
      onError: (err) => setError(err instanceof ApiError ? err.message : "Couldn't cancel the order."),
    });
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader title={`Cancel ${order.code}?`} description={`Committed for ${order.request_code}: ${formatMoney(order.committed_amount ?? order.total_amount, { decimals: 2 })}. Cancelling can't be undone.`} />
        <form onSubmit={submit} noValidate className="space-y-4">
          <FormAlert message={error} />
          <fieldset aria-describedby={fieldError.choice ? "po-choice-error" : undefined}>
            <legend className="mb-2 text-small font-medium text-fg">Committed budget <span className="text-danger">*</span></legend>
            <div className="space-y-2" role="radiogroup">
              {CANCEL_OPTIONS.map((o) => (
                <label key={o.value} className={cn("flex cursor-pointer gap-3 rounded-[var(--radius-panel)] border bg-surface p-3 transition-colors hover:border-border-strong",
                  choice === o.value ? "border-brand shadow-[inset_0_0_0_1px_var(--brand)]" : "border-border")}>
                  <input type="radio" name="po-budget" value={o.value} checked={choice === o.value} onChange={() => { setChoice(o.value); setFieldError((f) => ({ ...f, choice: undefined })); }} className="mt-1 accent-[var(--brand)]" />
                  <span><span className="block text-body font-medium">{o.title}</span><span className="block text-small text-fg-secondary">{o.body}</span></span>
                </label>
              ))}
            </div>
            {fieldError.choice && <p id="po-choice-error" className="mt-1 text-small text-danger">{fieldError.choice}</p>}
          </fieldset>
          <FormField label="Reason" htmlFor="po-cancel-reason" error={fieldError.reason} required>
            <Textarea id="po-cancel-reason" rows={3} maxLength={500} value={reason} onChange={(e) => { setReason(e.target.value); setFieldError((f) => ({ ...f, reason: undefined })); }} />
          </FormField>
          <DialogFooter>
            <Button type="button" onClick={onClose}>Keep order</Button>
            <Button type="submit" variant="danger" loading={cancel.isPending}><Ban /> Cancel order</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
