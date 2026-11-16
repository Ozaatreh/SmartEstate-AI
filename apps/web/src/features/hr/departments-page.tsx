import { zodResolver } from "@hookform/resolvers/zod";
import { Building2, Pencil, Plus, Users } from "lucide-react";
import * as React from "react";
import { Controller, useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { z } from "zod";
import { StatusBadge } from "@/components/system/badges";
import { FormAlert, FormField, applyServerErrors } from "@/components/system/forms";
import { PageHeader } from "@/components/system/layout-blocks";
import { EmptyState, ErrorState } from "@/components/system/states";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/menu";
import { Avatar, Skeleton } from "@/components/ui/primitives";
import { useCan } from "@/features/auth/auth-context";
import { useDepartments, useEmployeeOptions, useSaveDepartment, type Department } from "./api";
import { initialsOf } from "@/lib/utils";

export default function DepartmentsPage() {
  const canManage = useCan("hr.departments.manage");
  const q = useDepartments(canManage);
  const [editing, setEditing] = React.useState<Department | "new" | null>(null);
  const total = (q.data ?? []).reduce((n, d) => n + (d.is_active ? d.headcount : 0), 0);

  return (
    <>
      <PageHeader title="Departments" description={q.data ? `${q.data.filter((d) => d.is_active).length} departments · ${total} active employees` : "Organisation structure."}
        actions={canManage && <Button variant="primary" onClick={() => setEditing("new")}><Plus /> New department</Button>} />
      {q.isPending ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-36 rounded-[var(--radius-panel)]" />)}</div>
      ) : q.isError ? <ErrorState error={q.error} onRetry={() => void q.refetch()} /> : !q.data.length ? (
        <div className="rounded-[var(--radius-panel)] border border-border bg-surface"><EmptyState icon={<Building2 className="size-5" />} title="No departments yet" description="Create the first department to start building the organisation." /></div>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {q.data.map((d) => (
            <li key={d.id} className="group flex flex-col rounded-[var(--radius-panel)] border border-border bg-surface p-4 transition-colors hover:border-border-strong">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="tabular text-caption font-medium text-fg-muted">{d.code}</p>
                  <h2 className="truncate text-lead font-semibold">{d.name}</h2>
                </div>
                <div className="flex items-center gap-1">
                  {!d.is_active && <StatusBadge status="inactive" />}
                  {canManage && <Button size="icon" variant="ghost" aria-label={`Edit ${d.name}`} onClick={() => setEditing(d)}><Pencil /></Button>}
                </div>
              </div>
              {d.description && <p className="mt-1 line-clamp-2 text-small text-fg-secondary">{d.description}</p>}
              <div className="mt-auto flex items-end justify-between gap-3 pt-4">
                {d.manager ? (
                  <Link to={`/hr/employees/${d.manager.id}`} className="flex min-w-0 items-center gap-2">
                    <Avatar initials={initialsOf(d.manager.full_name)} className="size-7 [&_span]:text-[10px]" />
                    <span className="min-w-0"><span className="block truncate text-small font-medium hover:text-brand">{d.manager.full_name}</span><span className="block text-caption text-fg-muted">Manager</span></span>
                  </Link>
                ) : <span className="text-small text-warning">No manager assigned</span>}
                <Link to={`/hr/employees?department_id=${d.id}`} className="inline-flex shrink-0 items-center gap-1.5 text-small font-medium text-fg-secondary hover:text-brand">
                  <Users className="size-3.5" /><span className="tabular">{d.headcount}</span>
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
      {canManage && editing && <DepartmentDialog department={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />}
    </>
  );
}

const NONE = "__none";
const schema = z.object({
  code: z.string().trim().min(2, "At least 2 characters.").max(20).regex(/^[A-Za-z0-9-]+$/, "Letters, digits and dashes only."),
  name: z.string().trim().min(2, "Enter a name."),
  description: z.string().max(2000),
  manager_employee_id: z.string(),
});
type Values = z.infer<typeof schema>;

function DepartmentDialog({ department, onClose }: { department?: Department; onClose: () => void }) {
  const save = useSaveDepartment(department?.id);
  const people = useEmployeeOptions();
  const [formError, setFormError] = React.useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { code: department?.code ?? "", name: department?.name ?? "", description: department?.description ?? "", manager_employee_id: department?.manager?.id ?? NONE },
  });
  const { errors, isSubmitting } = form.formState;
  const submit = form.handleSubmit(async (v) => {
    setFormError(null);
    try {
      const body = { name: v.name, description: v.description || null, manager_employee_id: v.manager_employee_id === NONE ? null : v.manager_employee_id };
      await save.mutateAsync(department ? body : { ...body, code: v.code });
      toast.success(department ? "Department updated" : "Department created");
      onClose();
    } catch (err) {
      setFormError(applyServerErrors(err, form.setError, ["code", "name", "manager_employee_id"]));
    }
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader title={department ? `Edit ${department.name}` : "New department"} description="The manager approves purchase requests at department level." />
        <form onSubmit={submit} noValidate className="space-y-4">
          <FormAlert message={formError} />
          <div className="grid gap-4 sm:grid-cols-[120px_1fr]">
            <FormField label="Code" htmlFor="dep-code" error={errors.code?.message} required><Input disabled={Boolean(department)} className="uppercase" {...form.register("code")} /></FormField>
            <FormField label="Name" htmlFor="dep-name" error={errors.name?.message} required><Input {...form.register("name")} /></FormField>
          </div>
          <FormField label="Manager" htmlFor="dep-manager" error={errors.manager_employee_id?.message}>
            <Controller control={form.control} name="manager_employee_id" render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}
                options={[{ value: NONE, label: "No manager" }, ...(people.data?.items ?? []).map((p) => ({ value: p.id, label: `${p.full_name} · ${p.job_title}` }))]} />
            )} />
          </FormField>
          <FormField label="Description" htmlFor="dep-desc"><Textarea rows={3} {...form.register("description")} /></FormField>
          <DialogFooter>
            <Button type="button" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" loading={isSubmitting}>{department ? "Save changes" : "Create department"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
