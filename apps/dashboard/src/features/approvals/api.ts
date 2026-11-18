import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ListQuery, type Page } from "@/lib/api-client";

export interface PersonRef { id: string; full_name: string }

export interface ApprovalStep {
  step_order: number;
  level: "department" | "finance" | "executive" | "marketing";
  label: string;
  status: "waiting" | "pending" | "approved" | "rejected" | "skipped";
  assignee: PersonRef | null;
  pool_label: string | null;
  escalation_reason: string | null;
  activated_at: string | null;
  decided_at: string | null;
  decision: { decision: string; comment: string | null; decided_by: PersonRef; created_at: string } | null;
}

export interface Approval {
  id: string;
  entity_type: string;
  entity_label: string;
  entity_id: string;
  entity_code: string;
  title: string;
  amount: string;
  status: "pending" | "approved" | "rejected" | "cancelled";
  flags: { over_budget?: boolean };
  requester: PersonRef;
  current_step: number | null;
  current_step_label: string | null;
  waiting_on: string | null;
  link: string;
  created_at: string;
  completed_at: string | null;
  can_decide: boolean;
}

export interface ApprovalDetail extends Approval {
  policy_name: string;
  steps: ApprovalStep[];
  allowed_actions: string[];
  blocked_reason: string | null;
}

const key = ["approvals"] as const;

export function useApprovals(query: ListQuery & { box: string; status?: string }) {
  return useQuery({
    queryKey: [...key, "list", query],
    queryFn: ({ signal }) => api.get<Page<Approval>>("/approvals", { ...query }, signal),
    placeholderData: keepPreviousData,
  });
}

export function usePendingApprovals() {
  return useQuery({ queryKey: [...key, "pending-count"], queryFn: () => api.get<{ pending: number }>("/approvals/pending-count"), refetchInterval: 60_000 });
}

export function useDecide() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, decision, comment }: { id: string; decision: "approve" | "reject"; comment: string }) =>
      api.post<ApprovalDetail>(`/approvals/${id}/${decision}`, { comment: comment.trim() || null }),
    onSuccess: () => Promise.all([
      qc.invalidateQueries({ queryKey: key }),
      qc.invalidateQueries({ queryKey: ["procurement"] }),
      qc.invalidateQueries({ queryKey: ["finance"] }),
      qc.invalidateQueries({ queryKey: ["notifications"] }),
      qc.invalidateQueries({ queryKey: ["marketing"] }),
    ]),
  });
}

export function useApproval(id: string | null | undefined) {
  return useQuery({ queryKey: [...key, "detail", id], queryFn: () => api.get<ApprovalDetail>(`/approvals/${id}`), enabled: Boolean(id) });
}

/** Documents with a money amount (purchase requests). Marketing content is reviewed without one. */
export function isMonetary(a: Pick<Approval, "entity_type" | "amount">): boolean {
  return a.entity_type === "purchase_request" || Number(a.amount) !== 0;
}
