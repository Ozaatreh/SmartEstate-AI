import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ListQuery, type Page } from "@/lib/api-client";
import type { ApprovalDetail, PersonRef } from "@/features/approvals/api";
import type { Category, Position, ProjectRef } from "@/features/finance/api";
import type { DepartmentRef } from "@/features/hr/api";

export interface SupplierRef { id: string; code: string; name: string }
export interface Supplier extends SupplierRef {
  category: string;
  contact_name: string | null;
  email: string | null;
  phone: string | null;
  vat_number: string | null;
  city: string | null;
  rating: string | null;
  status: string;
  notes: string | null;
  quotation_count: number;
  selected_count: number;
}

export interface RequestItem {
  id: string;
  line_no: number;
  description: string;
  quantity: string;
  unit: string;
  estimated_unit_price: string;
  line_total: string;
}

export interface Quotation {
  id: string;
  supplier: SupplierRef;
  supplier_rating: string | null;
  reference: string | null;
  valid_until: string | null;
  delivery_days: number | null;
  payment_terms: string | null;
  notes: string | null;
  total_amount: string;
  status: "received" | "selected" | "not_selected";
  items: { request_item_id: string; unit_price: string; line_total: string }[];
  is_lowest: boolean;
  difference_from_lowest: string;
  created_at: string;
}

export interface Comparison {
  rows: {
    request_item_id: string;
    line_no: number;
    description: string;
    quantity: string;
    unit: string;
    estimated_unit_price: string;
    cells: { quotation_id: string; unit_price: string; line_total: string; is_lowest: boolean }[];
  }[];
  lowest_quotation_id: string | null;
  fastest_quotation_id: string | null;
  savings_vs_estimate: string | null;
}

export interface BudgetImpact {
  found: boolean;
  budget_id: string | null;
  scope_label: string;
  category: string;
  fiscal_year: number;
  position: Position | null;
  amount: string;
  available_after: string | null;
  over_budget: boolean;
  committed_by_this_request: boolean;
  approval_levels: string[];
}

export interface PurchaseRequest {
  id: string;
  code: string;
  title: string;
  status: string;
  priority: string;
  requester: PersonRef;
  department: DepartmentRef;
  project: ProjectRef | null;
  category: string;
  estimated_total: string;
  approved_total: string | null;
  over_budget: boolean;
  quotation_count: number;
  needed_by: string | null;
  created_at: string;
  submitted_at: string | null;
  decided_at: string | null;
  waiting_on: string | null;
}

export interface PurchaseRequestDetail extends PurchaseRequest {
  justification: string;
  fiscal_year: number;
  category_detail: Category;
  items: RequestItem[];
  quotations: Quotation[];
  comparison: Comparison;
  selected_quotation_id: string | null;
  budget_impact: BudgetImpact;
  approval: ApprovalDetail | null;
  allowed_actions: string[];
  cancel_reason: string | null;
  sent_for_approval_at: string | null;
}

export interface RequestStats {
  draft: number;
  sourcing: number;
  pending_approval: number;
  approved: number;
  rejected: number;
  cancelled: number;
  approved_value: string;
  in_approval_value: string;
}

export interface RequestInput {
  title: string;
  justification: string;
  department_id: string;
  project_id: string | null;
  category_id: string;
  fiscal_year: number;
  needed_by: string | null;
  priority: string;
  items: { description: string; quantity: string; unit: string; estimated_unit_price: string }[];
}

export interface QuotationInput {
  supplier_id: string;
  reference: string | null;
  valid_until: string | null;
  delivery_days: number | null;
  payment_terms: string | null;
  notes: string | null;
  items: { request_item_id: string; unit_price: string }[];
}

const key = ["procurement"] as const;

export function useSuppliers(query: ListQuery & { status?: string; category?: string }, enabled = true) {
  return useQuery({
    queryKey: [...key, "suppliers", query],
    queryFn: ({ signal }) => api.get<Page<Supplier>>("/procurement/suppliers", { ...query }, signal),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useSupplierCategories(enabled = true) {
  return useQuery({ queryKey: [...key, "supplier-categories"], queryFn: () => api.get<string[]>("/procurement/suppliers/categories"), enabled });
}

export function useSaveSupplier(id?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => (id ? api.patch<Supplier>(`/procurement/suppliers/${id}`, body) : api.post<Supplier>("/procurement/suppliers", body)),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
  });
}

export function useRequests(query: ListQuery & { scope?: string; status?: string; department_id?: string }) {
  return useQuery({
    queryKey: [...key, "requests", query],
    queryFn: ({ signal }) => api.get<Page<PurchaseRequest>>("/procurement/requests", { ...query }, signal),
    placeholderData: keepPreviousData,
  });
}

export function useRequestStats(scope: string) {
  return useQuery({ queryKey: [...key, "stats", scope], queryFn: () => api.get<RequestStats>("/procurement/requests/stats", { scope }) });
}

export function useRequest(id: string | undefined) {
  return useQuery({ queryKey: [...key, "request", id], queryFn: () => api.get<PurchaseRequestDetail>(`/procurement/requests/${id}`), enabled: Boolean(id) });
}

export function useRequestActivity(id: string | undefined) {
  return useQuery({
    queryKey: [...key, "request", id, "activity"],
    queryFn: () => api.get<import("@/features/platform/api").AuditLog[]>(`/procurement/requests/${id}/activity`),
    enabled: Boolean(id),
  });
}

export function useBudgetPreview(body: { department_id: string; project_id: string | null; category_id: string; fiscal_year: number; amount: string } | null) {
  return useQuery({
    queryKey: [...key, "preview", body],
    queryFn: () => api.post<BudgetImpact>("/procurement/requests/budget-preview", body),
    enabled: body !== null,
    placeholderData: keepPreviousData,
    staleTime: 10_000,
  });
}

/** Every request mutation refreshes procurement, approvals and finance views (one posting affects all three). */
function useInvalidateAll() {
  const qc = useQueryClient();
  return () => Promise.all([
    qc.invalidateQueries({ queryKey: key }),
    qc.invalidateQueries({ queryKey: ["approvals"] }),
    qc.invalidateQueries({ queryKey: ["finance"] }),
    qc.invalidateQueries({ queryKey: ["notifications"] }),
  ]);
}

export function useSaveRequest(id?: string) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (body: RequestInput) => (id ? api.patch<PurchaseRequestDetail>(`/procurement/requests/${id}`, body) : api.post<PurchaseRequestDetail>("/procurement/requests", body)),
    onSuccess: invalidate,
  });
}

export function useRequestAction(id: string) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: ({ action, body }: { action: "submit" | "send-for-approval" | "cancel"; body?: unknown }) =>
      api.post<PurchaseRequestDetail>(`/procurement/requests/${id}/${action}`, body ?? {}),
    onSuccess: invalidate,
  });
}

export function useQuotationMutations(requestId: string) {
  const invalidate = useInvalidateAll();
  const base = `/procurement/requests/${requestId}/quotations`;
  return {
    save: useMutation({
      mutationFn: ({ id, body }: { id?: string; body: QuotationInput }) => (id ? api.put<PurchaseRequestDetail>(`${base}/${id}`, body) : api.post<PurchaseRequestDetail>(base, body)),
      onSuccess: invalidate,
    }),
    remove: useMutation({ mutationFn: (id: string) => api.delete<void>(`${base}/${id}`), onSuccess: invalidate }),
    select: useMutation({ mutationFn: (id: string) => api.post<PurchaseRequestDetail>(`${base}/${id}/select`), onSuccess: invalidate }),
  };
}
