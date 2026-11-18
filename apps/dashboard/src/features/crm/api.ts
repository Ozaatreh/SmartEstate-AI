import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ListQuery, type Page } from "@/lib/api-client";

export type Stage = "new" | "contacted" | "qualified" | "viewing" | "negotiation" | "won" | "lost";
export interface Ref { id: string; code: string; name: string }
export interface UserRef { id: string; full_name: string }

export interface Lead {
  id: string;
  code: string;
  full_name: string;
  phone: string | null;
  email: string | null;
  source: string;
  interest: string | null;
  budget_min: string | null;
  budget_max: string | null;
  bedrooms_wanted: number | null;
  stage: Stage;
  score: number | null;
  grade: "hot" | "warm" | "cold" | null;
  score_reasons: { points: number; reason: string }[] | null;
  owner: { id: string; full_name: string } | null;
  assigned_at: string | null;
  next_follow_up_at: string | null;
  created_at: string;
  project: Ref | null;
  interested_unit: Ref | null;
  timeline: string | null;
  last_activity_at: string | null;
  follow_up_overdue: boolean;
}

export interface ReservationBrief { id: string; code: string; status: string; unit: Ref; expires_at: string; deposit_amount: string | null }

export interface LeadDetail extends Lead {
  preferred_language: string;
  notes: string | null;
  consent_given_at: string | null;
  stage_changed_at: string | null;
  close_reason: string | null;
  created_by: UserRef | null;
  allowed_actions: string[];
  allowed_stages: Stage[];
  reservations: ReservationBrief[];
}

export interface Activity { id: string; type: string; body: string; performed_by: UserRef | null; occurred_at: string; reservation_id: string | null }

export interface LeadStats {
  new: number; contacted: number; qualified: number; viewing: number; negotiation: number; won: number; lost: number;
  open: number; overdue: number; unassigned: number;
}

export interface Reservation {
  id: string;
  code: string;
  status: "active" | "expired" | "cancelled" | "converted";
  unit: Ref;
  unit_status: string;
  list_price: string;
  lead: Ref;
  lead_owner: UserRef | null;
  reserved_by: UserRef | null;
  reserved_at: string;
  expires_at: string;
  deposit_amount: string | null;
  notes: string | null;
  cancel_reason: string | null;
  cancelled_at: string | null;
  converted_at: string | null;
  expired_at: string | null;
  allowed_actions: string[];
}

export interface LeadInput {
  full_name: string;
  phone: string | null;
  email: string | null;
  source: string;
  interest: string | null;
  budget_min: string | null;
  budget_max: string | null;
  bedrooms_wanted: number | null;
  timeline: string | null;
  project_id: string | null;
  consent: boolean;
}

const key = ["crm"] as const;

export function useLeads(query: ListQuery & { scope?: string; stage?: string; overdue?: string; project_id?: string }) {
  return useQuery({
    queryKey: [...key, "leads", query],
    queryFn: ({ signal }) => api.get<Page<Lead>>("/crm/leads", { ...query }, signal),
    placeholderData: keepPreviousData,
  });
}

export function useLeadStats(scope: string) {
  return useQuery({ queryKey: [...key, "stats", scope], queryFn: () => api.get<LeadStats>("/crm/leads/stats", { scope }) });
}

export function useLead(id: string | undefined) {
  return useQuery({ queryKey: [...key, "lead", id], queryFn: () => api.get<LeadDetail>(`/crm/leads/${id}`), enabled: Boolean(id) });
}

export function useLeadActivities(id: string | undefined) {
  return useQuery({ queryKey: [...key, "lead", id, "activities"], queryFn: () => api.get<Activity[]>(`/crm/leads/${id}/activities`), enabled: Boolean(id) });
}

export function useSalesUsers(enabled: boolean) {
  return useQuery({ queryKey: [...key, "sales-users"], queryFn: () => api.get<UserRef[]>("/crm/sales-users"), enabled, staleTime: 60_000 });
}

export function useReservations(query: ListQuery & { scope?: string; status?: string; lead_id?: string }) {
  return useQuery({
    queryKey: [...key, "reservations", query],
    queryFn: ({ signal }) => api.get<Page<Reservation>>("/crm/reservations", { ...query }, signal),
    placeholderData: keepPreviousData,
  });
}

/** A lead or reservation change also moves units, so CRM, inventory and notifications all refresh. */
function useInvalidate() {
  const qc = useQueryClient();
  return () => Promise.all([
    qc.invalidateQueries({ queryKey: key }),
    qc.invalidateQueries({ queryKey: ["realestate"] }),
    qc.invalidateQueries({ queryKey: ["notifications"] }),
  ]);
}

export function useCreateLead() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (body: LeadInput) => api.post<Lead>("/crm/leads", body), onSuccess: invalidate });
}

export function useLeadMutations(id: string) {
  const invalidate = useInvalidate();
  const base = `/crm/leads/${id}`;
  return {
    update: useMutation({ mutationFn: (body: Record<string, unknown>) => api.patch<LeadDetail>(base, body), onSuccess: invalidate }),
    stage: useMutation({ mutationFn: (body: { stage: Stage; reason?: string | null }) => api.post<LeadDetail>(`${base}/stage`, body), onSuccess: invalidate }),
    activity: useMutation({
      mutationFn: (body: { type: string; body: string; occurred_at?: string | null; next_follow_up_at?: string | null }) =>
        api.post<Activity[]>(`${base}/activities`, body),
      onSuccess: invalidate,
    }),
    assign: useMutation({ mutationFn: (body: { owner_user_id: string; reason?: string | null }) => api.post<LeadDetail>(`${base}/assign`, body), onSuccess: invalidate }),
  };
}

export function useReservationMutations() {
  const invalidate = useInvalidate();
  return {
    create: useMutation({
      mutationFn: (body: { lead_id: string; unit_id: string; hours: number; deposit_amount: string | null; notes: string | null }) =>
        api.post<Reservation>("/crm/reservations", body),
      onSuccess: invalidate,
    }),
    cancel: useMutation({ mutationFn: ({ id, reason }: { id: string; reason: string }) => api.post<Reservation>(`/crm/reservations/${id}/cancel`, { reason }), onSuccess: invalidate }),
    convert: useMutation({ mutationFn: (id: string) => api.post<Reservation>(`/crm/reservations/${id}/convert`), onSuccess: invalidate }),
  };
}

// --- AI lead intelligence (advisory; generated on demand, never stored, changes nothing) -------------
export type AIState = "disabled" | "misconfigured" | "unverified" | "operational" | "degraded";
export interface AIStatus { state: AIState; reason: string; usable: boolean }

export interface LeadSummary {
  lead_id: string;
  lead_code: string;
  ai_generated: true;
  advisory_notice: string;
  overview: string;
  buying_signals: string[];
  concerns: string[];
  next_action: string;
  next_action_reason: string;
  generated_at: string;
  model: string;
  request_id: string;
  interactions_considered: number;
}

export function useAIStatus(enabled = true) {
  return useQuery({ queryKey: ["ai", "status"], queryFn: () => api.get<AIStatus>("/ai/status"), enabled, staleTime: 60_000 });
}

/** No cache invalidation on success: a summary is advisory and changes no CRM data. */
export function useGenerateLeadSummary(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<LeadSummary>(`/crm/leads/${id}/ai-summary`),
    onError: () => void qc.invalidateQueries({ queryKey: ["ai", "status"] }),
  });
}
