import * as React from "react";
import { toast } from "sonner";
import { MoneyText } from "@/components/system/data-display";
import { FormAlert, FormField } from "@/components/system/forms";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/menu";
import { ApiError } from "@/lib/api-client";
import { lineTotal, sumMoney } from "@/lib/decimal";
import { useQuotationMutations, useSuppliers, type PurchaseRequestDetail, type Quotation } from "./api";

const MONEY = /^\d{1,16}(\.\d{1,2})?$/;

export function QuotationDialog({ request, quotation, onClose }: { request: PurchaseRequestDetail; quotation?: Quotation; onClose: () => void }) {
  const suppliers = useSuppliers({ status: "active", page_size: 100, sort: "name" });
  const { save } = useQuotationMutations(request.id);
  const taken = new Set(request.quotations.filter((q) => q.id !== quotation?.id).map((q) => q.supplier.id));
  const [supplierId, setSupplierId] = React.useState(quotation?.supplier.id ?? "");
  const [reference, setReference] = React.useState(quotation?.reference ?? "");
  const [validUntil, setValidUntil] = React.useState(quotation?.valid_until ?? "");
  const [delivery, setDelivery] = React.useState(quotation?.delivery_days?.toString() ?? "");
  const [terms, setTerms] = React.useState(quotation?.payment_terms ?? "30 days net");
  const [notes, setNotes] = React.useState(quotation?.notes ?? "");
  const [prices, setPrices] = React.useState<Record<string, string>>(() =>
    Object.fromEntries(request.items.map((i) => [i.id, quotation?.items.find((qi) => qi.request_item_id === i.id)?.unit_price ?? ""])));
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [formError, setFormError] = React.useState<string | null>(null);

  const lines = request.items.map((i) => ({ item: i, total: MONEY.test(prices[i.id] ?? "") ? lineTotal(i.quantity, prices[i.id] ?? "") : null }));
  const grand = sumMoney(lines.map((l) => l.total));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!supplierId) errs.supplier = "Choose a supplier.";
    for (const i of request.items) if (!MONEY.test((prices[i.id] ?? "").trim())) errs[i.id] = "Enter a price";
    if (delivery && !/^\d{1,4}$/.test(delivery)) errs.delivery = "Whole days only.";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setFormError(null);
    try {
      await save.mutateAsync({
        id: quotation?.id,
        body: {
          supplier_id: supplierId, reference: reference || null, valid_until: validUntil || null, delivery_days: delivery ? Number(delivery) : null,
          payment_terms: terms || null, notes: notes || null, items: request.items.map((i) => ({ request_item_id: i.id, unit_price: (prices[i.id] ?? "").trim() })),
        },
      });
      toast.success(quotation ? "Quotation updated" : "Quotation recorded");
      onClose();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "The quotation couldn't be saved.");
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] max-w-2xl overflow-y-auto">
        <DialogHeader title={quotation ? `Edit quotation · ${quotation.supplier.name}` : "Record a supplier quotation"} description={`${request.code} · ${request.title}`} />
        <form onSubmit={submit} noValidate className="space-y-5">
          <FormAlert message={formError} />
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Supplier" htmlFor="q-supplier" error={errors.supplier} required>
              <Select value={supplierId || undefined} onValueChange={setSupplierId} disabled={Boolean(quotation)} placeholder="Choose a supplier…"
                options={(suppliers.data?.items ?? []).filter((s) => !taken.has(s.id)).map((s) => ({ value: s.id, label: `${s.name} · ${s.category}` }))} />
            </FormField>
            <FormField label="Supplier reference" htmlFor="q-ref"><Input value={reference} onChange={(e) => setReference(e.target.value)} placeholder="e.g. Q-2291" /></FormField>
            <FormField label="Valid until" htmlFor="q-valid"><Input type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} /></FormField>
            <FormField label="Delivery (days)" htmlFor="q-days" error={errors.delivery}><Input inputMode="numeric" value={delivery} onChange={(e) => setDelivery(e.target.value)} /></FormField>
          </div>

          <div className="overflow-hidden rounded-[var(--radius-panel)] border border-border">
            <table className="w-full text-body">
              <thead className="bg-surface-subtle text-left text-caption uppercase tracking-[0.04em] text-fg-muted">
                <tr><th className="h-8 px-3 font-medium">Item</th><th className="w-36 px-3 font-medium">Unit price (SAR)</th><th className="hidden w-32 px-3 text-right font-medium sm:table-cell">Line total</th></tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {lines.map(({ item, total }) => (
                  <tr key={item.id}>
                    <td className="px-3 py-2">
                      <p className="font-medium">{item.description}</p>
                      <p className="tabular text-caption text-fg-muted">{Number(item.quantity).toLocaleString("en-US")} {item.unit} · est. <MoneyText value={item.estimated_unit_price} decimals={2} /></p>
                    </td>
                    <td className="px-3 py-2">
                      <Input aria-label={`Unit price for ${item.description}`} aria-invalid={errors[item.id] ? true : undefined} inputMode="decimal" className="h-8 tabular"
                        value={prices[item.id] ?? ""} onChange={(e) => setPrices((p) => ({ ...p, [item.id]: e.target.value }))} placeholder="0.00" />
                    </td>
                    <td className="hidden px-3 py-2 text-right sm:table-cell"><MoneyText value={total} decimals={2} /></td>
                  </tr>
                ))}
              </tbody>
              <tfoot><tr className="border-t border-border bg-surface-subtle"><td className="px-3 py-2 font-medium" colSpan={2}>Quotation total</td>
                <td className="px-3 py-2 text-right"><MoneyText value={grand} decimals={2} className="font-semibold" /></td></tr></tfoot>
            </table>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Payment terms" htmlFor="q-terms"><Input value={terms} onChange={(e) => setTerms(e.target.value)} /></FormField>
            <FormField label="Notes" htmlFor="q-notes"><Textarea rows={1} className="min-h-9" value={notes} onChange={(e) => setNotes(e.target.value)} /></FormField>
          </div>
          <DialogFooter>
            <Button type="button" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" loading={save.isPending}>{quotation ? "Save quotation" : "Record quotation"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
