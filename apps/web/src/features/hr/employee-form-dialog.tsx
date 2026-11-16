import { zodResolver } from "@hookform/resolvers/zod";
import * as React from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { FormAlert, FormField, applyServerErrors } from "@/components/system/forms";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/menu";
import { useDepartments, useEmployeeOptions, useSaveEmployee, type EmployeeDetail } from "./api";

const NONE = "__none";
const schema = z.object({
  full_name: z.string().trim().min(2, "Enter the full name."),
  job_title: z.string().trim().min(2, "Enter the job title."),
  department_id: z.string().min(1, "Choose a department."),
  manager_id: z.string(),
  email: z.union([z.literal(""), z.string().trim().email("Enter a valid email address.")]),
  phone: z.string().trim().max(40),
  location: z.string().trim().max(120),
  hire_date: z.string(),
});
type Values = z.infer<typeof schema>;

export function EmployeeFormDialog({ open, onOpenChange, employee, onSaved }: {
  open: boolean; onOpenChange: (o: boolean) => void; employee?: EmployeeDetail; onSaved?: (e: EmployeeDetail) => void;
}) {
  const departments = useDepartments();
  const people = useEmployeeOptions(open);
  const save = useSaveEmployee(employee?.id);
  const [formError, setFormError] = React.useState<string | null>(null);
  const form = useForm<Values>({ resolver: zodResolver(schema), values: toValues(employee) });
  const { errors, isSubmitting } = form.formState;

  const submit = form.handleSubmit(async (v) => {
    setFormError(null);
    try {
      const saved = await save.mutateAsync({
        full_name: v.full_name, job_title: v.job_title, department_id: v.department_id, manager_id: v.manager_id === NONE ? null : v.manager_id || null,
        email: v.email || null, phone: v.phone || null, location: v.location || null, hire_date: v.hire_date || null,
      });
      toast.success(employee ? "Employee updated" : `${saved.full_name} added`, { description: saved.employee_no });
      onSaved?.(saved);
      onOpenChange(false);
    } catch (err) {
      setFormError(applyServerErrors(err, form.setError, ["full_name", "job_title", "department_id", "manager_id", "email"]));
    }
  });

  const managerOptions = [{ value: NONE, label: "No manager" },
    ...(people.data?.items ?? []).filter((p) => p.id !== employee?.id).map((p) => ({ value: p.id, label: `${p.full_name} · ${p.job_title}` }))];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader title={employee ? `Edit ${employee.full_name}` : "Add employee"} description="Profile, department and reporting line." />
        <form onSubmit={submit} noValidate className="space-y-4">
          <FormAlert message={formError} />
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Full name" htmlFor="emp-name" error={errors.full_name?.message} required><Input {...form.register("full_name")} /></FormField>
            <FormField label="Job title" htmlFor="emp-title" error={errors.job_title?.message} required><Input {...form.register("job_title")} /></FormField>
            <FormField label="Department" htmlFor="emp-dept" error={errors.department_id?.message} required>
              <Controller control={form.control} name="department_id" render={({ field }) => (
                <Select value={field.value || undefined} onValueChange={field.onChange} placeholder="Choose…"
                  options={(departments.data ?? []).map((d) => ({ value: d.id, label: d.name }))} />
              )} />
            </FormField>
            <FormField label="Reports to" htmlFor="emp-manager" error={errors.manager_id?.message}>
              <Controller control={form.control} name="manager_id" render={({ field }) => (
                <Select value={field.value || NONE} onValueChange={field.onChange} options={managerOptions} />
              )} />
            </FormField>
            <FormField label="Work email" htmlFor="emp-email" error={errors.email?.message}><Input type="email" {...form.register("email")} /></FormField>
            <FormField label="Phone" htmlFor="emp-phone"><Input type="tel" {...form.register("phone")} /></FormField>
            <FormField label="Location" htmlFor="emp-location"><Input placeholder="e.g. Riyadh HQ" {...form.register("location")} /></FormField>
            <FormField label="Hire date" htmlFor="emp-hire"><Input type="date" {...form.register("hire_date")} /></FormField>
          </div>
          <DialogFooter>
            <Button type="button" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" variant="primary" loading={isSubmitting}>{employee ? "Save changes" : "Add employee"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function toValues(e?: EmployeeDetail): Values {
  return {
    full_name: e?.full_name ?? "", job_title: e?.job_title ?? "", department_id: e?.department.id ?? "", manager_id: e?.manager?.id ?? NONE,
    email: e?.email ?? "", phone: e?.phone ?? "", location: e?.location ?? "", hire_date: e?.hire_date ?? "",
  };
}
