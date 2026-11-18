import { zodResolver } from "@hookform/resolvers/zod";
import type { ColumnDef } from "@tanstack/react-table";
import { Plus, Star, Truck } from "lucide-react";
import * as React from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { StatusBadge } from "@/components/system/badges";
import { DataTable } from "@/components/system/data-table";
import { FormAlert, FormField, applyServerErrors } from "@/components/system/forms";
import { PageHeader } from "@/components/system/layout-blocks";
import { EmptyState } from "@/components/system/states";
import { useListState } from "@/components/system/use-list-state";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/menu";
import { useCan } from "@/features/auth/auth-context";
import { useSaveSupplier, useSupplierCategories, useSuppliers, type Supplier } from "./api";

const FILTERS = ["category", "status"] as const;

export default function SuppliersPage() {
  const state = useListState({ filterKeys: FILTERS, defaultSort: "name" });
  const list = useSuppliers(state.query);
  const categories = useSupplierCategories();
  const canManage = useCan("procurement.suppliers.manage");
  const [editing, setEditing] = React.useState<Supplier | "new" | null>(null);

  const columns: ColumnDef<Supplier, unknown>[] = [
    {
      id: "name", header: "Supplier", meta: { sortKey: "name", label: "Supplier" }, enableHiding: false,
      cell: ({ row: { original: s } }) => <div><p className="font-medium">{s.name}</p><p className="tabular text-caption text-fg-muted">{s.code}{s.city ? ` · ${s.city}` : ""}</p></div>,
    },
    { id: "category", header: "Category", meta: { sortKey: "category", label: "Category" }, cell: ({ row }) => row.original.category },
    {
      id: "contact", header: "Contact", meta: { label: "Contact", className: "hidden lg:table-cell" },
      cell: ({ row: { original: s } }) => <div className="min-w-0"><p className="truncate">{s.contact_name ?? "—"}</p><p className="truncate text-caption text-fg-muted">{s.email ?? s.phone ?? ""}</p></div>,
    },
    { id: "rating", header: "Rating", meta: { sortKey: "rating", label: "Rating" }, cell: ({ row }) => <Rating value={row.original.rating} /> },
    {
      id: "quotes", header: "Quotations", meta: { label: "Quotations", align: "right", className: "hidden md:table-cell" },
      cell: ({ row: { original: s } }) => <span className="tabular text-small text-fg-secondary">{s.quotation_count}{s.selected_count ? ` · ${s.selected_count} won` : ""}</span>,
    },
    { id: "status", header: "Status", meta: { label: "Status" }, cell: ({ row }) => <StatusBadge status={row.original.status} /> },
  ];

  return (
    <>
      <PageHeader title="Suppliers" description="Approved vendors that quote on purchase requests."
        actions={canManage && <Button variant="primary" onClick={() => setEditing("new")}><Plus /> Add supplier</Button>} />
      <DataTable
        ariaLabel="Suppliers"
        columns={columns}
        page={list.data}
        isLoading={list.isPending}
        isFetching={list.isFetching}
        error={list.error}
        onRetry={() => void list.refetch()}
        state={state}
        searchPlaceholder="Search name, code, contact, city"
        getRowId={(s) => s.id}
        onRowClick={canManage ? (s) => setEditing(s) : undefined}
        filters={<>
          <Select aria-label="Category" className="h-8 w-48" value={state.filters.category ?? "all"} onValueChange={(v) => state.setFilter("category", v === "all" ? undefined : v)}
            options={[{ value: "all", label: "All categories" }, ...(categories.data ?? []).map((c) => ({ value: c, label: c }))]} />
          <Select aria-label="Status" className="h-8 w-32" value={state.filters.status ?? "all"} onValueChange={(v) => state.setFilter("status", v === "all" ? undefined : v)}
            options={[{ value: "all", label: "Any status" }, { value: "active", label: "Active" }, { value: "inactive", label: "Inactive" }, { value: "blocked", label: "Blocked" }]} />
        </>}
        empty={<EmptyState icon={<Truck className="size-5" />} title="No suppliers yet" description="Add suppliers so procurement can record their quotations."
          action={canManage && <Button size="sm" variant="primary" onClick={() => setEditing("new")}><Plus /> Add supplier</Button>} />}
        mobileRow={(s) => (
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0"><p className="truncate font-medium">{s.name}</p><p className="text-small text-fg-muted">{s.category}</p></div>
            <div className="flex flex-col items-end gap-1"><Rating value={s.rating} />{s.status !== "active" && <StatusBadge status={s.status} />}</div>
          </div>
        )}
      />
      {canManage && editing && <SupplierDialog supplier={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />}
    </>
  );
}

function Rating({ value }: { value: string | null }) {
  if (!value) return <span className="text-fg-muted">—</span>;
  return <span className="tabular inline-flex items-center gap-1 text-small"><Star className="size-3.5 fill-warning text-warning" aria-hidden />{value}<span className="sr-only"> out of 5</span></span>;
}

const schema = z.object({
  name: z.string().trim().min(2, "Enter the supplier name."),
  category: z.string().trim().min(2, "Enter a category."),
  contact_name: z.string().trim().max(120),
  email: z.union([z.literal(""), z.string().trim().email("Enter a valid email.")]),
  phone: z.string().trim().max(40),
  vat_number: z.string().trim().max(30).regex(/^[0-9A-Za-z-]*$/, "Letters, digits and dashes only."),
  city: z.string().trim().max(80),
  rating: z.union([z.literal(""), z.string().regex(/^[0-5](\.\d)?$/, "0 to 5, one decimal")]),
  status: z.enum(["active", "inactive", "blocked"]),
  notes: z.string().max(2000),
});
type Values = z.infer<typeof schema>;

function SupplierDialog({ supplier, onClose }: { supplier?: Supplier; onClose: () => void }) {
  const save = useSaveSupplier(supplier?.id);
  const [formError, setFormError] = React.useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: supplier?.name ?? "", category: supplier?.category ?? "", contact_name: supplier?.contact_name ?? "", email: supplier?.email ?? "",
      phone: supplier?.phone ?? "", vat_number: supplier?.vat_number ?? "", city: supplier?.city ?? "", rating: supplier?.rating ?? "",
      status: (supplier?.status as Values["status"]) ?? "active", notes: supplier?.notes ?? "",
    },
  });
  const { errors, isSubmitting } = form.formState;
  const submit = form.handleSubmit(async (v) => {
    setFormError(null);
    const body: Record<string, unknown> = Object.fromEntries(Object.entries(v).map(([k, val]) => [k, val === "" ? null : val]));
    if (!supplier) delete body.status;
    try {
      await save.mutateAsync(body);
      toast.success(supplier ? "Supplier updated" : "Supplier added");
      onClose();
    } catch (err) {
      setFormError(applyServerErrors(err, form.setError, ["name", "category", "email", "vat_number", "rating"]));
    }
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-xl">
        <DialogHeader title={supplier ? `Edit ${supplier.name}` : "Add supplier"} description={supplier?.code ?? "Suppliers get a code automatically."} />
        <form onSubmit={submit} noValidate className="space-y-4">
          <FormAlert message={formError} />
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Name" htmlFor="s-name" error={errors.name?.message} required><Input {...form.register("name")} /></FormField>
            <FormField label="Category" htmlFor="s-cat" error={errors.category?.message} required><Input placeholder="e.g. Construction materials" {...form.register("category")} /></FormField>
            <FormField label="Contact person" htmlFor="s-contact"><Input {...form.register("contact_name")} /></FormField>
            <FormField label="Email" htmlFor="s-email" error={errors.email?.message}><Input type="email" {...form.register("email")} /></FormField>
            <FormField label="Phone" htmlFor="s-phone"><Input type="tel" {...form.register("phone")} /></FormField>
            <FormField label="City" htmlFor="s-city"><Input {...form.register("city")} /></FormField>
            <FormField label="VAT number" htmlFor="s-vat" error={errors.vat_number?.message}><Input {...form.register("vat_number")} /></FormField>
            <FormField label="Rating (0–5)" htmlFor="s-rating" error={errors.rating?.message}><Input inputMode="decimal" {...form.register("rating")} /></FormField>
            {supplier && (
              <FormField label="Status" htmlFor="s-status">
                <Controller control={form.control} name="status" render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange} options={[{ value: "active", label: "Active" }, { value: "inactive", label: "Inactive" }, { value: "blocked", label: "Blocked" }]} />
                )} />
              </FormField>
            )}
          </div>
          <FormField label="Notes" htmlFor="s-notes"><Textarea rows={2} {...form.register("notes")} /></FormField>
          <DialogFooter>
            <Button type="button" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" loading={isSubmitting}>{supplier ? "Save changes" : "Add supplier"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
