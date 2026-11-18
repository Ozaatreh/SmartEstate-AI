import { zodResolver } from "@hookform/resolvers/zod";
import * as React from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { FormAlert, FormField, applyServerErrors } from "@/components/system/forms";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/menu";
import { useDepartments, useEmployeeOptions } from "@/features/hr/api";
import { useCategories, useProjects, useSaveBudget, useSaveProject, type BudgetDetail } from "./api";

const money = z.string().trim().regex(/^\d{1,16}(\.\d{1,2})?$/, "Enter an amount like 250000 or 250000.50.");

const budgetSchema = z.object({
  scope: z.enum(["department", "project"]),
  owner_id: z.string().min(1, "Choose who owns this budget."),
  category_id: z.string().min(1, "Choose a category."),
  fiscal_year: z.coerce.number().int().min(2000).max(2100),
  allocated_amount: money,
  notes: z.string().max(2000),
});
type BudgetValues = z.input<typeof budgetSchema>;

export function BudgetFormDialog({ open, onOpenChange, fiscalYear, budget }: {
  open: boolean; onOpenChange: (o: boolean) => void; fiscalYear: number; budget?: BudgetDetail;
}) {
  const departments = useDepartments();
  const projects = useProjects();
  const categories = useCategories();
  const save = useSaveBudget(budget?.id);
  const [formError, setFormError] = React.useState<string | null>(null);
  const form = useForm<BudgetValues>({
    resolver: zodResolver(budgetSchema),
    values: budget
      ? { scope: budget.scope, owner_id: budget.department?.id ?? budget.project?.id ?? "", category_id: budget.category.id, fiscal_year: budget.fiscal_year,
          allocated_amount: budget.position.allocated, notes: budget.notes ?? "" }
      : { scope: "department", owner_id: "", category_id: "", fiscal_year: fiscalYear, allocated_amount: "", notes: "" },
  });
  const scope = useWatch({ control: form.control, name: "scope" });
  const { errors, isSubmitting } = form.formState;

  const submit = form.handleSubmit(async (raw) => {
    const v = budgetSchema.parse(raw);
    setFormError(null);
    try {
      if (budget) {
        await save.mutateAsync({ allocated_amount: v.allocated_amount, notes: v.notes || null });
        toast.success("Budget updated");
      } else {
        await save.mutateAsync({
          fiscal_year: v.fiscal_year, category_id: v.category_id, allocated_amount: v.allocated_amount, notes: v.notes || null,
          department_id: v.scope === "department" ? v.owner_id : null, project_id: v.scope === "project" ? v.owner_id : null,
        });
        toast.success("Budget created");
      }
      onOpenChange(false);
    } catch (err) {
      setFormError(applyServerErrors(err, form.setError, ["allocated_amount", "category_id", "fiscal_year"]));
    }
  });

  const owners = scope === "department"
    ? (departments.data ?? []).map((d) => ({ value: d.id, label: d.name }))
    : (projects.data ?? []).map((p) => ({ value: p.id, label: `${p.code} · ${p.name}` }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader title={budget ? "Change allocation" : "New budget"}
          description={budget ? "The allocation can't go below what is already committed and spent." : "A yearly allocation for one category, owned by a department or a project."} />
        <form onSubmit={submit} noValidate className="space-y-4">
          <FormAlert message={formError} />
          {!budget && (
            <>
              <div className="grid grid-cols-2 gap-2 rounded-[var(--radius-control)] bg-surface-sunken p-1" role="radiogroup" aria-label="Budget owner">
                {(["department", "project"] as const).map((s) => (
                  <button key={s} type="button" role="radio" aria-checked={scope === s} onClick={() => { form.setValue("scope", s); form.setValue("owner_id", ""); }}
                    className={`h-8 rounded-[4px] text-small font-medium transition-colors ${scope === s ? "bg-surface text-fg shadow-[0_0_0_1px_var(--border)]" : "text-fg-secondary hover:text-fg"}`}>
                    {s === "department" ? "Department" : "Operational project"}
                  </button>
                ))}
              </div>
              <FormField label={scope === "department" ? "Department" : "Project"} htmlFor="b-owner" error={errors.owner_id?.message} required>
                <Controller control={form.control} name="owner_id" render={({ field }) => <Select value={field.value || undefined} onValueChange={field.onChange} options={owners} placeholder="Choose…" />} />
              </FormField>
              <div className="grid gap-4 sm:grid-cols-[1fr_120px]">
                <FormField label="Category" htmlFor="b-cat" error={errors.category_id?.message} required>
                  <Controller control={form.control} name="category_id" render={({ field }) => (
                    <Select value={field.value || undefined} onValueChange={field.onChange} placeholder="Choose…" options={(categories.data ?? []).map((c) => ({ value: c.id, label: c.name }))} />
                  )} />
                </FormField>
                <FormField label="Fiscal year" htmlFor="b-year" error={errors.fiscal_year?.message} required><Input inputMode="numeric" {...form.register("fiscal_year")} /></FormField>
              </div>
            </>
          )}
          <FormField label="Allocated amount (SAR)" htmlFor="b-amount" error={errors.allocated_amount?.message} required>
            <Input inputMode="decimal" className="tabular" placeholder="0.00" {...form.register("allocated_amount")} />
          </FormField>
          <FormField label="Notes" htmlFor="b-notes"><Textarea rows={2} {...form.register("notes")} /></FormField>
          <DialogFooter>
            <Button type="button" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" variant="primary" loading={isSubmitting}>{budget ? "Save allocation" : "Create budget"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

const NONE = "__none";
const projectSchema = z.object({
  name: z.string().trim().min(2, "Enter a name."),
  department_id: z.string().min(1, "Choose the owning department."),
  manager_employee_id: z.string(),
  status: z.enum(["planned", "active", "on_hold", "completed", "cancelled"]),
  start_date: z.string(),
  end_date: z.string(),
  description: z.string().max(2000),
}).refine((v) => !v.start_date || !v.end_date || v.end_date >= v.start_date, { path: ["end_date"], message: "End date must be on or after the start date." });
type ProjectValues = z.infer<typeof projectSchema>;

export function ProjectFormDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const departments = useDepartments();
  const people = useEmployeeOptions(open);
  const save = useSaveProject();
  const [formError, setFormError] = React.useState<string | null>(null);
  const form = useForm<ProjectValues>({
    resolver: zodResolver(projectSchema),
    defaultValues: { name: "", department_id: "", manager_employee_id: NONE, status: "active", start_date: "", end_date: "", description: "" },
  });
  const { errors, isSubmitting } = form.formState;
  const submit = form.handleSubmit(async (v) => {
    setFormError(null);
    try {
      const p = await save.mutateAsync({ ...v, manager_employee_id: v.manager_employee_id === NONE ? null : v.manager_employee_id,
        start_date: v.start_date || null, end_date: v.end_date || null, description: v.description || null });
      toast.success("Project created", { description: (p as { code: string }).code });
      form.reset();
      onOpenChange(false);
    } catch (err) {
      setFormError(applyServerErrors(err, form.setError, ["name", "department_id", "end_date"]));
    }
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader title="New operational project" description="Projects can hold their own budgets; purchase requests can be charged to them." />
        <form onSubmit={submit} noValidate className="space-y-4">
          <FormAlert message={formError} />
          <FormField label="Project name" htmlFor="p-name" error={errors.name?.message} required><Input {...form.register("name")} /></FormField>
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Owning department" htmlFor="p-dept" error={errors.department_id?.message} required>
              <Controller control={form.control} name="department_id" render={({ field }) => (
                <Select value={field.value || undefined} onValueChange={field.onChange} placeholder="Choose…" options={(departments.data ?? []).map((d) => ({ value: d.id, label: d.name }))} />
              )} />
            </FormField>
            <FormField label="Project manager" htmlFor="p-mgr">
              <Controller control={form.control} name="manager_employee_id" render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange} options={[{ value: NONE, label: "Not assigned" }, ...(people.data?.items ?? []).map((p) => ({ value: p.id, label: p.full_name }))]} />
              )} />
            </FormField>
            <FormField label="Start date" htmlFor="p-start"><Input type="date" {...form.register("start_date")} /></FormField>
            <FormField label="End date" htmlFor="p-end" error={errors.end_date?.message}><Input type="date" {...form.register("end_date")} /></FormField>
          </div>
          <FormField label="Description" htmlFor="p-desc"><Textarea rows={2} {...form.register("description")} /></FormField>
          <DialogFooter>
            <Button type="button" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" variant="primary" loading={isSubmitting}>Create project</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
