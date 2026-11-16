import type { ColumnDef } from "@tanstack/react-table";
import { Building2, FolderKanban, Plus, Wallet } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { StatusBadge } from "@/components/system/badges";
import { UtilisationCell } from "@/components/system/business";
import { ChartCard } from "@/components/system/chart-card";
import { KpiCard, MoneyText } from "@/components/system/data-display";
import { DataTable } from "@/components/system/data-table";
import { PageHeader } from "@/components/system/layout-blocks";
import { EmptyState } from "@/components/system/states";
import { useListState } from "@/components/system/use-list-state";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/menu";
import { useCan } from "@/features/auth/auth-context";
import { useDepartments } from "@/features/hr/api";
import { formatMoney, formatPercent } from "@/lib/format";
import { useBudgets, useBudgetSummary, useCategories, type Budget } from "./api";
import { BudgetFormDialog } from "./budget-dialogs";

const FILTERS = ["fiscal_year", "scope", "department_id", "category_id", "project_id"] as const;
const THIS_YEAR = new Date().getFullYear();

export default function BudgetsPage() {
  const state = useListState({ filterKeys: FILTERS, defaultSort: "department" });
  const year = Number(state.filters.fiscal_year ?? THIS_YEAR);
  const list = useBudgets({ ...state.query, fiscal_year: year });
  const summary = useBudgetSummary(year);
  const departments = useDepartments();
  const categories = useCategories();
  const canManage = useCan("finance.budgets.manage");
  const navigate = useNavigate();
  const [creating, setCreating] = React.useState(false);
  const s = summary.data;

  const chartData = (s?.by_department ?? []).map((d) => ({
    department: d.department.code,
    // Chart geometry only (SAR thousands); exact figures are in the table view and the budgets list.
    allocated: Math.round(Number(d.allocated) / 1000),
    committed: Math.round(Number(d.committed) / 1000),
  }));

  const columns: ColumnDef<Budget, unknown>[] = [
    {
      id: "department", header: "Owner", meta: { sortKey: "department", label: "Owner" }, enableHiding: false,
      cell: ({ row: { original: b } }) => (
        <div className="flex items-center gap-2.5">
          <span className="grid size-7 shrink-0 place-items-center rounded-[var(--radius-control)] bg-surface-sunken text-fg-muted">
            {b.scope === "project" ? <FolderKanban className="size-3.5" /> : <Building2 className="size-3.5" />}
          </span>
          <div className="min-w-0">
            <p className="truncate font-medium">{b.project ? b.project.name : b.department?.name}</p>
            <p className="truncate text-caption text-fg-muted">{b.project ? `${b.project.code} · ${b.owner_department.name}` : "Department budget"}</p>
          </div>
        </div>
      ),
    },
    { id: "category", header: "Category", meta: { sortKey: "category", label: "Category" }, cell: ({ row }) => row.original.category.name },
    { id: "allocated", header: "Allocated", meta: { sortKey: "allocated", label: "Allocated", align: "right" }, cell: ({ row }) => <MoneyText value={row.original.position.allocated} /> },
    { id: "committed", header: "Committed", meta: { label: "Committed", align: "right", className: "hidden lg:table-cell" }, cell: ({ row }) => <MoneyText value={row.original.position.committed} /> },
    {
      id: "available", header: "Available", meta: { label: "Available", align: "right" },
      cell: ({ row }) => <MoneyText value={row.original.position.available} className="font-medium" />,
    },
    { id: "utilisation", header: "Used", meta: { label: "Used", className: "w-44 hidden md:table-cell" }, cell: ({ row }) => <UtilisationCell pct={row.original.position.utilisation_pct} /> },
    { id: "status", header: "Status", meta: { label: "Status", className: "hidden xl:table-cell" }, cell: ({ row }) => <StatusBadge status={row.original.status} /> },
  ];

  return (
    <>
      <PageHeader
        title="Budgets"
        description={`Allocations, commitments and what is still available for FY${year}. Commitments come from approved purchase requests.`}
        actions={<>
          <Select aria-label="Fiscal year" className="h-9 w-28" value={String(year)} onValueChange={(v) => state.setFilter("fiscal_year", v === String(THIS_YEAR) ? undefined : v)}
            options={[THIS_YEAR - 1, THIS_YEAR, THIS_YEAR + 1].map((y) => ({ value: String(y), label: `FY${y}` }))} />
          {canManage && <Button variant="primary" onClick={() => setCreating(true)}><Plus /> New budget</Button>}
        </>}
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="Allocated" loading={summary.isPending} value={s ? formatMoney(s.allocated) : ""} hint={s ? `${s.budget_count} budgets` : undefined} />
        <KpiCard label="Committed" loading={summary.isPending} value={s ? formatMoney(s.committed) : ""} hint="from approved requests" />
        <KpiCard label="Available" loading={summary.isPending} value={s ? formatMoney(s.available) : ""} />
        <KpiCard label="Utilisation" loading={summary.isPending} value={s ? formatPercent(Number(s.utilisation_pct)) : ""}
          hint={s ? (s.over_threshold_count ? `${s.over_threshold_count} budget${s.over_threshold_count > 1 ? "s" : ""} ≥ 80% used` : "No budget above 80%") : undefined} />
      </div>

      <ChartCard className="mb-6" title="Allocated vs committed by department" subtitle={`SAR thousands · FY${year} · includes project budgets`}
        data={chartData} xKey="department" isLoading={summary.isPending} error={summary.error} onRetry={() => void summary.refetch()}
        series={[{ key: "allocated", label: "Allocated", slot: 1 }, { key: "committed", label: "Committed", slot: 2 }]}
        formatValue={(v) => `${v.toLocaleString("en-US")}k`} emptyDescription={`No budgets exist for FY${year} yet.`} />

      <DataTable
        ariaLabel="Budgets"
        columns={columns}
        page={list.data}
        isLoading={list.isPending}
        isFetching={list.isFetching}
        error={list.error}
        onRetry={() => void list.refetch()}
        state={state}
        searchPlaceholder="Search department, project, category"
        getRowId={(b) => b.id}
        onRowClick={(b) => navigate(`/finance/budgets/${b.id}`)}
        filters={<>
          <Select aria-label="Owner type" className="h-8 w-36" value={state.filters.scope ?? "all"} onValueChange={(v) => state.setFilter("scope", v === "all" ? undefined : v)}
            options={[{ value: "all", label: "All owners" }, { value: "department", label: "Departments" }, { value: "project", label: "Projects" }]} />
          <Select aria-label="Department" className="h-8 w-44" value={state.filters.department_id ?? "all"} onValueChange={(v) => state.setFilter("department_id", v === "all" ? undefined : v)}
            options={[{ value: "all", label: "All departments" }, ...(departments.data ?? []).map((d) => ({ value: d.id, label: d.name }))]} />
          <Select aria-label="Category" className="h-8 w-44" value={state.filters.category_id ?? "all"} onValueChange={(v) => state.setFilter("category_id", v === "all" ? undefined : v)}
            options={[{ value: "all", label: "All categories" }, ...(categories.data ?? []).map((c) => ({ value: c.id, label: c.name }))]} />
        </>}
        empty={<EmptyState icon={<Wallet className="size-5" />} title={`No budgets for FY${year}`} description="Create budgets so purchase requests can be checked against them."
          action={canManage && <Button size="sm" variant="primary" onClick={() => setCreating(true)}><Plus /> New budget</Button>} />}
        mobileRow={(b) => (
          <div className="space-y-2">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0"><p className="truncate font-medium">{b.project ? b.project.name : b.department?.name}</p><p className="text-small text-fg-muted">{b.category.name}</p></div>
              <MoneyText value={b.position.available} className="font-medium" />
            </div>
            <UtilisationCell pct={b.position.utilisation_pct} />
          </div>
        )}
      />
      {canManage && <BudgetFormDialog open={creating} onOpenChange={setCreating} fiscalYear={year} />}
    </>
  );
}
