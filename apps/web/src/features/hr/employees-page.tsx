import type { ColumnDef } from "@tanstack/react-table";
import { Plus, Users } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { StatusBadge } from "@/components/system/badges";
import { DataTable } from "@/components/system/data-table";
import { PageHeader } from "@/components/system/layout-blocks";
import { EmptyState } from "@/components/system/states";
import { useListState } from "@/components/system/use-list-state";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/menu";
import { Avatar } from "@/components/ui/primitives";
import { useCan } from "@/features/auth/auth-context";
import { formatNumber } from "@/lib/format";
import { initialsOf } from "@/lib/utils";
import { useDepartments, useEmployees, type Employee } from "./api";
import { EmployeeFormDialog } from "./employee-form-dialog";

const FILTERS = ["department_id", "status"] as const;

export default function EmployeesPage() {
  const state = useListState({ filterKeys: FILTERS, defaultSort: "full_name" });
  const list = useEmployees(state.query);
  const departments = useDepartments();
  const canManage = useCan("hr.employees.manage");
  const navigate = useNavigate();
  const [adding, setAdding] = React.useState(false);

  const columns: ColumnDef<Employee, unknown>[] = [
    {
      id: "full_name", header: "Name", meta: { sortKey: "full_name", label: "Name" }, enableHiding: false,
      cell: ({ row: { original: e } }) => (
        <div className="flex items-center gap-3">
          <Avatar initials={initialsOf(e.full_name)} />
          <div className="min-w-0">
            <p className="truncate font-medium">{e.full_name}</p>
            <p className="truncate text-small text-fg-muted">{e.email ?? e.employee_no}</p>
          </div>
        </div>
      ),
    },
    { id: "job_title", header: "Title", meta: { sortKey: "job_title", label: "Title" }, cell: ({ row }) => row.original.job_title },
    { id: "department", header: "Department", meta: { sortKey: "department", label: "Department" }, cell: ({ row }) => row.original.department.name },
    {
      id: "manager", header: "Reports to", meta: { label: "Reports to", className: "hidden lg:table-cell" },
      cell: ({ row }) => row.original.manager ? row.original.manager.full_name : <span className="text-fg-muted">—</span>,
    },
    {
      id: "reports", header: "Team", meta: { label: "Team", align: "right", className: "hidden xl:table-cell" },
      cell: ({ row }) => row.original.direct_reports_count ? <span className="tabular">{row.original.direct_reports_count} direct</span> : <span className="text-fg-muted">—</span>,
    },
    {
      id: "status", header: "Status", meta: { label: "Status", className: "w-28" },
      cell: ({ row }) => <StatusBadge status={row.original.is_active ? "active" : "inactive"} />,
    },
  ];

  return (
    <>
      <PageHeader
        title="Employees"
        description={list.data ? `${formatNumber(list.data.total)} people across ${departments.data?.length ?? "—"} departments.` : "The company directory."}
        actions={canManage && <Button variant="primary" onClick={() => setAdding(true)}><Plus /> Add employee</Button>}
      />
      <DataTable
        ariaLabel="Employees"
        columns={columns}
        page={list.data}
        isLoading={list.isPending}
        isFetching={list.isFetching}
        error={list.error}
        onRetry={() => void list.refetch()}
        state={state}
        searchPlaceholder="Search name, title, email"
        getRowId={(e) => e.id}
        onRowClick={(e) => navigate(`/hr/employees/${e.id}`)}
        filters={<>
          <Select aria-label="Department" className="h-8 w-48" value={state.filters.department_id ?? "all"}
            onValueChange={(v) => state.setFilter("department_id", v === "all" ? undefined : v)}
            options={[{ value: "all", label: "All departments" }, ...(departments.data ?? []).map((d) => ({ value: d.id, label: d.name }))]} />
          <Select aria-label="Status" className="h-8 w-32" value={state.filters.status ?? "active"}
            onValueChange={(v) => state.setFilter("status", v === "active" ? undefined : v)}
            options={[{ value: "active", label: "Active" }, { value: "inactive", label: "Inactive" }, { value: "all", label: "All" }]} />
        </>}
        empty={<EmptyState icon={<Users className="size-5" />} title="No employees yet"
          description="Add people to build the directory and reporting lines." action={canManage && <Button variant="primary" size="sm" onClick={() => setAdding(true)}><Plus /> Add employee</Button>} />}
        mobileRow={(e) => (
          <div className="flex items-center gap-3">
            <Avatar initials={initialsOf(e.full_name)} />
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">{e.full_name}</p>
              <p className="truncate text-small text-fg-muted">{e.job_title} · {e.department.name}</p>
            </div>
            {!e.is_active && <StatusBadge status="inactive" />}
          </div>
        )}
      />
      {canManage && <EmployeeFormDialog open={adding} onOpenChange={setAdding} onSaved={(e) => navigate(`/hr/employees/${e.id}`)} />}
    </>
  );
}
