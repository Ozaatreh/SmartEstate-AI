import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Send, Trash2 } from "lucide-react";
import * as React from "react";
import { Controller, useFieldArray, useForm, useWatch } from "react-hook-form";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { z } from "zod";
import { BudgetImpactCard } from "@/components/system/business";
import { MoneyText } from "@/components/system/data-display";
import { FormAlert, FormField, applyServerErrors } from "@/components/system/forms";
import { PageHeader, Panel } from "@/components/system/layout-blocks";
import { ErrorState, ListSkeleton } from "@/components/system/states";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/menu";
import { Skeleton } from "@/components/ui/primitives";
import { useAuth } from "@/features/auth/auth-context";
import { useCategories, useProjects } from "@/features/finance/api";
import { useDepartments, useEmployees } from "@/features/hr/api";
import { api, ApiError } from "@/lib/api-client";
import { lineTotal, sumMoney } from "@/lib/decimal";
import { useBudgetPreview, useRequest, useSaveRequest, type PurchaseRequestDetail, type RequestInput } from "./api";

const NONE = "__none";
const QTY = /^\d{1,11}(\.\d{1,3})?$/;
const MONEY = /^\d{1,16}(\.\d{1,2})?$/;
const THIS_YEAR = new Date().getFullYear();

const schema = z.object({
  title: z.string().trim().min(3, "Give the request a short title."),
  justification: z.string().trim().min(10, "Explain why this is needed (at least 10 characters)."),
  priority: z.enum(["low", "normal", "high", "urgent"]),
  needed_by: z.string(),
  department_id: z.string().min(1, "Choose the department."),
  project_id: z.string(),
  category_id: z.string().min(1, "Choose a budget category."),
  fiscal_year: z.coerce.number().int().min(2000).max(2100),
  items: z.array(z.object({
    description: z.string().trim().min(2, "Describe the item."),
    quantity: z.string().trim().regex(QTY, "Up to 3 decimals").refine((v) => Number(v) > 0, "Must be more than 0"),
    unit: z.string().trim().min(1, "Unit"),
    estimated_unit_price: z.string().trim().regex(MONEY, "Up to 2 decimals"),
  })).min(1, "Add at least one item."),
});
type Values = z.input<typeof schema>;

const emptyItem = { description: "", quantity: "1", unit: "unit", estimated_unit_price: "" };

export default function RequestFormPage() {
  const { id } = useParams();
  const existing = useRequest(id);
  if (id && existing.isPending) return <div className="space-y-4"><Skeleton className="h-8 w-64" /><div className="rounded-[var(--radius-panel)] border border-border bg-surface"><ListSkeleton rows={6} /></div></div>;
  if (id && existing.isError) return <ErrorState error={existing.error} onRetry={() => void existing.refetch()} />;
  if (existing.data && !existing.data.allowed_actions.includes("edit")) return <ErrorState error={new ApiError(409, { code: "invalid_state", message: "Only draft requests can be edited." })} />;
  return <RequestForm request={existing.data} />;
}

function RequestForm({ request }: { request?: PurchaseRequestDetail }) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const departments = useDepartments();
  const projects = useProjects();
  const categories = useCategories();
  const me = useEmployees({ q: user?.email, page_size: 1 }, !request && Boolean(user?.email));
  const save = useSaveRequest(request?.id);
  const [formError, setFormError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState<"draft" | "submit" | null>(null);

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: request ? {
      title: request.title, justification: request.justification, priority: request.priority as Values["priority"], needed_by: request.needed_by ?? "",
      department_id: request.department.id, project_id: request.project?.id ?? NONE, category_id: request.category_detail.id, fiscal_year: request.fiscal_year,
      items: request.items.map((i) => ({ description: i.description, quantity: i.quantity.replace(/\.?0+$/, ""), unit: i.unit, estimated_unit_price: i.estimated_unit_price })),
    } : { title: "", justification: "", priority: "normal", needed_by: "", department_id: "", project_id: NONE, category_id: "", fiscal_year: THIS_YEAR, items: [emptyItem] },
  });
  const { fields, append, remove } = useFieldArray({ control: form.control, name: "items" });
  const { errors } = form.formState;

  // Default the department to the requester's own (from the directory).
  const myDept = me.data?.items[0]?.department.id;
  React.useEffect(() => {
    if (!request && myDept && !form.getValues("department_id")) form.setValue("department_id", myDept);
  }, [myDept, request, form]);

  const watched = useWatch({ control: form.control });
  const totals = (watched.items ?? []).map((i) => (i && QTY.test(i.quantity ?? "") && MONEY.test(i.estimated_unit_price ?? "") ? lineTotal(i.quantity ?? "", i.estimated_unit_price ?? "") : null));
  const total = sumMoney(totals);
  const previewInput = watched.department_id && watched.category_id && Number(watched.fiscal_year) >= 2000
    ? { department_id: watched.department_id, project_id: watched.project_id && watched.project_id !== NONE ? watched.project_id : null, category_id: watched.category_id,
        fiscal_year: Number(watched.fiscal_year), amount: total }
    : null;
  const debounced = useDebounced(previewInput, 400);
  const preview = useBudgetPreview(debounced);

  const run = (mode: "draft" | "submit") => form.handleSubmit(async (raw) => {
    const v = schema.parse(raw);
    setFormError(null);
    setSubmitting(mode);
    const body: RequestInput = {
      title: v.title, justification: v.justification, priority: v.priority, needed_by: v.needed_by || null, department_id: v.department_id,
      project_id: v.project_id === NONE ? null : v.project_id, category_id: v.category_id, fiscal_year: v.fiscal_year, items: v.items,
    };
    try {
      const saved = await save.mutateAsync(body);
      if (mode === "submit") {
        await api.post(`/procurement/requests/${saved.id}/submit`);
        toast.success(`${saved.code} submitted`, { description: "Procurement will now collect supplier quotations." });
      } else {
        toast.success(request ? "Draft saved" : `${saved.code} saved as draft`);
      }
      navigate(`/procurement/requests/${saved.id}`);
    } catch (err) {
      setFormError(applyServerErrors(err, form.setError, ["title", "justification", "department_id", "project_id", "category_id"]));
      setSubmitting(null);
    }
  });

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: "Purchase requests", to: "/procurement/requests" }, { label: request ? request.code : "New" }]}
        title={request ? `Edit ${request.code}` : "New purchase request"}
        description="Describe what you need and where it is charged. The budget is checked as you type."
      />
      <form noValidate onSubmit={(e) => e.preventDefault()} className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-6">
          <FormAlert message={formError} />
          <Panel title="Request">
            <div className="grid gap-4 p-4 sm:grid-cols-2">
              <FormField label="Title" htmlFor="pr-title" error={errors.title?.message} required className="sm:col-span-2">
                <Input placeholder="e.g. Concrete pump rental — Q4 pours" {...form.register("title")} />
              </FormField>
              <FormField label="Justification" htmlFor="pr-why" error={errors.justification?.message} required className="sm:col-span-2" hint="Approvers read this first.">
                <Textarea rows={3} {...form.register("justification")} />
              </FormField>
              <FormField label="Priority" htmlFor="pr-priority">
                <Controller control={form.control} name="priority" render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange} options={["low", "normal", "high", "urgent"].map((p) => ({ value: p, label: p[0]!.toUpperCase() + p.slice(1) }))} />
                )} />
              </FormField>
              <FormField label="Needed by" htmlFor="pr-needed"><Input type="date" {...form.register("needed_by")} /></FormField>
            </div>
          </Panel>

          <Panel title="Charge to" description="Project requests draw on the project's budget; others on the department's.">
            <div className="grid gap-4 p-4 sm:grid-cols-2">
              <FormField label="Department" htmlFor="pr-dept" error={errors.department_id?.message} required>
                <Controller control={form.control} name="department_id" render={({ field }) => (
                  <Select value={field.value || undefined} onValueChange={field.onChange} placeholder="Choose…" options={(departments.data ?? []).map((d) => ({ value: d.id, label: d.name }))} />
                )} />
              </FormField>
              <FormField label="Operational project" htmlFor="pr-project" error={errors.project_id?.message}>
                <Controller control={form.control} name="project_id" render={({ field }) => (
                  <Select value={field.value || NONE} onValueChange={field.onChange}
                    options={[{ value: NONE, label: "None — department budget" }, ...(projects.data ?? []).filter((p) => ["planned", "active"].includes(p.status)).map((p) => ({ value: p.id, label: `${p.code} · ${p.name}` }))]} />
                )} />
              </FormField>
              <FormField label="Budget category" htmlFor="pr-cat" error={errors.category_id?.message} required>
                <Controller control={form.control} name="category_id" render={({ field }) => (
                  <Select value={field.value || undefined} onValueChange={field.onChange} placeholder="Choose…" options={(categories.data ?? []).map((c) => ({ value: c.id, label: c.name }))} />
                )} />
              </FormField>
              <FormField label="Fiscal year" htmlFor="pr-year" error={errors.fiscal_year?.message} required>
                <Controller control={form.control} name="fiscal_year" render={({ field }) => (
                  <Select value={String(field.value)} onValueChange={(v) => field.onChange(Number(v))} options={[THIS_YEAR, THIS_YEAR + 1].map((y) => ({ value: String(y), label: `FY${y}` }))} />
                )} />
              </FormField>
            </div>
          </Panel>

          <Panel title="Items" description="Estimated prices; procurement replaces them with supplier quotations."
            actions={<Button type="button" size="sm" onClick={() => append(emptyItem)} disabled={fields.length >= 50}><Plus /> Add item</Button>}>
            <div className="divide-y divide-border-subtle">
              <div className="hidden grid-cols-[minmax(0,1fr)_96px_88px_128px_112px_32px] gap-3 bg-surface-subtle px-4 py-2 text-caption font-medium uppercase tracking-[0.04em] text-fg-muted md:grid">
                <span>Description</span><span>Qty</span><span>Unit</span><span>Unit price</span><span className="text-right">Total</span><span />
              </div>
              {fields.map((f, i) => {
                const e = errors.items?.[i];
                return (
                  <div key={f.id} className="grid grid-cols-2 gap-3 px-4 py-3 md:grid-cols-[minmax(0,1fr)_96px_88px_128px_112px_32px] md:items-start">
                    <div className="col-span-2 md:col-span-1">
                      <Input aria-label={`Item ${i + 1} description`} aria-invalid={e?.description ? true : undefined} placeholder={`Item ${i + 1}`} {...form.register(`items.${i}.description`)} />
                      {e?.description && <p className="mt-1 text-caption text-danger">{e.description.message}</p>}
                    </div>
                    <div>
                      <Input aria-label={`Item ${i + 1} quantity`} aria-invalid={e?.quantity ? true : undefined} inputMode="decimal" className="tabular" {...form.register(`items.${i}.quantity`)} />
                      {e?.quantity && <p className="mt-1 text-caption text-danger">{e.quantity.message}</p>}
                    </div>
                    <Input aria-label={`Item ${i + 1} unit`} {...form.register(`items.${i}.unit`)} />
                    <div>
                      <Input aria-label={`Item ${i + 1} unit price`} aria-invalid={e?.estimated_unit_price ? true : undefined} inputMode="decimal" className="tabular" placeholder="0.00"
                        {...form.register(`items.${i}.estimated_unit_price`)} />
                      {e?.estimated_unit_price && <p className="mt-1 text-caption text-danger">{e.estimated_unit_price.message}</p>}
                    </div>
                    <p className="flex h-9 items-center justify-end text-right font-medium"><MoneyText value={totals[i]} decimals={2} /></p>
                    <Button type="button" size="icon" variant="ghost" aria-label={`Remove item ${i + 1}`} disabled={fields.length === 1} onClick={() => remove(i)} className="justify-self-end"><Trash2 /></Button>
                  </div>
                );
              })}
            </div>
            {errors.items?.root && <p className="px-4 pb-3 text-small text-danger">{errors.items.root.message}</p>}
          </Panel>
        </div>

        <aside className="space-y-4 xl:sticky xl:top-[calc(var(--topbar-height)+24px)] xl:self-start">
          <Panel title="Estimated total">
            <div className="p-4">
              <MoneyText value={total} decimals={2} className="text-h2 font-semibold tracking-[-0.02em]" />
              <p className="mt-1 text-small text-fg-muted">{fields.length} item{fields.length === 1 ? "" : "s"}</p>
            </div>
          </Panel>
          <Panel title="Budget check" description="Live, against the selected budget">
            <div className="p-4">
              {!previewInput ? <p className="text-small text-fg-muted">Choose a department and category to see the budget impact.</p>
                : preview.isPending ? <div className="space-y-2"><Skeleton className="h-4 w-2/3" /><Skeleton className="h-2 w-full" /><Skeleton className="h-10 w-full" /></div>
                : preview.isError ? <p className="text-small text-danger">{preview.error instanceof ApiError ? preview.error.message : "Budget check unavailable."}</p>
                : <BudgetImpactCard impact={preview.data} compact />}
            </div>
          </Panel>
          <div className="flex flex-col gap-2">
            <Button type="button" variant="primary" size="lg" onClick={run("submit")} loading={submitting === "submit"} disabled={submitting !== null || (preview.data && !preview.data.found)}>
              <Send /> Submit for sourcing
            </Button>
            <Button type="button" size="lg" onClick={run("draft")} loading={submitting === "draft"} disabled={submitting !== null}>Save as draft</Button>
          </div>
        </aside>
      </form>
    </>
  );
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = React.useState(value);
  const key = JSON.stringify(value);
  React.useEffect(() => {
    const t = window.setTimeout(() => setV(JSON.parse(key) as T), ms);
    return () => window.clearTimeout(t);
  }, [key, ms]);
  return v;
}
