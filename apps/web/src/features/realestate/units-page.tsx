import type { ColumnDef } from "@tanstack/react-table";
import { Home, Plus } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { StatusBadge } from "@/components/system/badges";
import { MoneyText } from "@/components/system/data-display";
import { DataTable } from "@/components/system/data-table";
import { PageHeader } from "@/components/system/layout-blocks";
import { EmptyState } from "@/components/system/states";
import { useListState } from "@/components/system/use-list-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/menu";
import { useCan } from "@/features/auth/auth-context";
import { humanize } from "@/lib/status";
import { useProjects, useUnits, type Unit } from "./api";
import { UNIT_TYPES, bedroomsLabel } from "./logic";
import { UnitFormDialog } from "./manage-dialogs";
import { DemoBadge, DemoDataNotice } from "./shared";

const FILTERS = ["project_id", "status", "unit_type", "min_bedrooms", "price_max"] as const;
const ANY = "__any";

export default function UnitsPage() {
  const state = useListState({ filterKeys: FILTERS, defaultSort: "unit_number" });
  const list = useUnits(state.query);
  const projects = useProjects();
  const navigate = useNavigate();
  const [maxPrice, setMaxPrice] = React.useState(state.filters.price_max ?? "");
  const canManage = useCan("realestate.inventory.manage");
  const [adding, setAdding] = React.useState(false);

  const set = (k: (typeof FILTERS)[number]) => (v: string) => state.setFilter(k, v === ANY ? undefined : v);

  const columns: ColumnDef<Unit, unknown>[] = [
    {
      id: "unit_number", header: "Unit", meta: { sortKey: "unit_number", label: "Unit" }, enableHiding: false,
      cell: ({ row: { original: u } }) => (
        <div className="min-w-0">
          <p className="tabular font-medium">{u.building.code}-{u.unit_number}</p>
          <p className="truncate text-caption text-fg-muted">{u.project.name}</p>
        </div>
      ),
    },
    { id: "type", header: "Type", meta: { label: "Type" }, cell: ({ row: { original: u } }) => <span className="capitalize">{u.unit_type} · {bedroomsLabel(u.bedrooms)}</span> },
    { id: "floor", header: "Floor", meta: { sortKey: "floor", label: "Floor", align: "right", className: "hidden md:table-cell" }, cell: ({ row }) => <span className="tabular">{row.original.floor}</span> },
    { id: "area_sqm", header: "Area", meta: { sortKey: "area_sqm", label: "Area", align: "right", className: "hidden lg:table-cell" }, cell: ({ row }) => <span className="tabular">{Number(row.original.area_sqm).toLocaleString("en-US")} m²</span> },
    { id: "view", header: "View", meta: { label: "View", className: "hidden xl:table-cell" }, cell: ({ row }) => <span className="text-fg-secondary">{row.original.view ?? "—"}</span> },
    { id: "status", header: "Status", meta: { label: "Status" }, cell: ({ row }) => <StatusBadge status={row.original.status} /> },
    { id: "list_price", header: "Price", meta: { sortKey: "list_price", label: "Price", align: "right" }, cell: ({ row }) => <MoneyText value={row.original.list_price} /> },
  ];

  const projectOptions = [{ value: ANY, label: "All projects" }, ...(projects.data?.items ?? []).map((p) => ({ value: p.id, label: p.name }))];
  return (
    <>
      <PageHeader title="Units" description="Search the inventory by project, status, size and price." meta={<DemoBadge />}
        actions={canManage && <Button variant="primary" onClick={() => setAdding(true)}><Plus /> Add unit</Button>} />
      <DemoDataNotice />
      <DataTable
        ariaLabel="Units"
        columns={columns}
        page={list.data}
        isLoading={list.isPending}
        isFetching={list.isFetching}
        error={list.error}
        onRetry={() => void list.refetch()}
        state={state}
        searchPlaceholder="Search unit number or view"
        getRowId={(u) => u.id}
        onRowClick={(u) => navigate(`/realestate/units/${u.id}`)}
        filters={<>
          <Select aria-label="Project" className="w-full sm:w-44" value={state.filters.project_id ?? ANY} onValueChange={set("project_id")} options={projectOptions} />
          <Select aria-label="Status" className="w-full sm:w-36" value={state.filters.status ?? ANY} onValueChange={set("status")}
            options={[{ value: ANY, label: "Any status" }, ...["available", "reserved", "sold", "blocked"].map((s) => ({ value: s, label: humanize(s) }))]} />
          <Select aria-label="Type" className="w-full sm:w-36" value={state.filters.unit_type ?? ANY} onValueChange={set("unit_type")}
            options={[{ value: ANY, label: "Any type" }, ...UNIT_TYPES]} />
          <Select aria-label="Bedrooms" className="w-full sm:w-32" value={state.filters.min_bedrooms ?? ANY} onValueChange={set("min_bedrooms")}
            options={[{ value: ANY, label: "Any size" }, ...[1, 2, 3, 4].map((n) => ({ value: String(n), label: `${n}+ BR` }))]} />
          <form className="w-full sm:w-40" onSubmit={(e) => { e.preventDefault(); state.setFilter("price_max", maxPrice.replace(/[^\d.]/g, "") || undefined); }}>
            <Input aria-label="Maximum price (SAR)" inputMode="numeric" placeholder="Max price (SAR)" value={maxPrice}
              onChange={(e) => setMaxPrice(e.target.value)} onBlur={() => state.setFilter("price_max", maxPrice.replace(/[^\d.]/g, "") || undefined)} />
          </form>
        </>}
        empty={<EmptyState icon={<Home className="size-5" />} title="No units" description="Units appear here once buildings are added to a project." />}
        mobileRow={(u) => (
          <div className="space-y-1">
            <div className="flex items-center justify-between gap-2"><span className="tabular font-medium">{u.building.code}-{u.unit_number}</span><MoneyText value={u.list_price} className="font-medium" /></div>
            <p className="text-small capitalize text-fg-secondary">{u.unit_type} · {bedroomsLabel(u.bedrooms)} · {Number(u.area_sqm).toLocaleString("en-US")} m² · floor {u.floor}</p>
            <StatusBadge status={u.status} />
          </div>
        )}
      />
      {adding && <UnitFormDialog projectId={state.filters.project_id} onClose={() => setAdding(false)} />}
    </>
  );
}
