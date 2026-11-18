import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ListQuery, type Page } from "@/lib/api-client";
import type { DepartmentRef, EmployeeRef } from "@/features/hr/api";

export interface Category { id: string; code: string; name: string; description: string | null }
export interface ProjectRef { id: string; code: string; name: string }

export interface Project extends ProjectRef {
  description: string | null;
  status: string;
  start_date: string | null;
  end_date: string | null;
  department: DepartmentRef;
  manager: EmployeeRef | null;
  allocated_total: string;
  committed_total: string;
  available_total: string;
}

export interface Position {
  allocated: string;
  adjustments: string;
  committed: string;
  actual: string;
  available: string;
  utilisation_pct: string;
}

export interface Budget {
  id: string;
  fiscal_year: number;
  status: string;
  scope: "department" | "project";
  category: Category;
  department: DepartmentRef | null;
  project: ProjectRef | null;
  owner_department: DepartmentRef;
  notes: string | null;
  position: Position;
}

export interface LedgerEntry {
  id: string;
  entry_type: "commitment" | "release" | "actual" | "adjustment";
  amount: string;
  source_type: string;
  source_id: string;
  source_code: string | null;
  description: string | null;
  created_at: string;
}

export interface BudgetDetail extends Budget { ledger: LedgerEntry[] }

export interface BudgetSummary {
  fiscal_year: number;
  budget_count: number;
  allocated: string;
  committed: string;
  actual: string;
  available: string;
  utilisation_pct: string;
  over_threshold_count: number;
  by_department: { department: DepartmentRef; allocated: string; committed: string; available: string }[];
}

const key = ["finance"] as const;

export function useCategories() {
  return useQuery({ queryKey: [...key, "categories"], queryFn: () => api.get<Category[]>("/finance/categories"), staleTime: 300_000 });
}

export function useProjects(status?: string) {
  return useQuery({ queryKey: [...key, "projects", status], queryFn: () => api.get<Project[]>("/finance/projects", { status }), staleTime: 60_000 });
}

export function useProject(id: string | undefined) {
  return useQuery({ queryKey: [...key, "project", id], queryFn: () => api.get<Project>(`/finance/projects/${id}`), enabled: Boolean(id) });
}

export function useBudgets(query: ListQuery & { fiscal_year?: string | number; scope?: string; department_id?: string; project_id?: string; category_id?: string }, enabled = true) {
  return useQuery({
    queryKey: [...key, "budgets", query],
    queryFn: ({ signal }) => api.get<Page<Budget>>("/finance/budgets", { ...query }, signal),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useBudgetSummary(fiscalYear: number) {
  return useQuery({ queryKey: [...key, "summary", fiscalYear], queryFn: () => api.get<BudgetSummary>("/finance/budgets/summary", { fiscal_year: fiscalYear }) });
}

export function useBudget(id: string | undefined) {
  return useQuery({ queryKey: [...key, "budget", id], queryFn: () => api.get<BudgetDetail>(`/finance/budgets/${id}`), enabled: Boolean(id) });
}

export function useSaveBudget(id?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => (id ? api.patch<BudgetDetail>(`/finance/budgets/${id}`, body) : api.post<BudgetDetail>("/finance/budgets", body)),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
  });
}

export function useSaveProject(id?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => (id ? api.patch<Project>(`/finance/projects/${id}`, body) : api.post<Project>("/finance/projects", body)),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
  });
}
