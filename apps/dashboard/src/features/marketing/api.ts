import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ListQuery, type Page } from "@/lib/api-client";

export type Channel = "instagram" | "x" | "linkedin" | "email" | "website" | "whatsapp";
export type Language = "en" | "ar";
export type CampaignStatus = "draft" | "active" | "completed" | "archived";
export type ContentStatus = "draft" | "pending_approval" | "approved" | "rejected" | "archived";
export interface Ref { id: string; code: string; name: string }
export interface PersonRef { id: string; full_name: string }
export interface StatusCounts { draft: number; pending_approval: number; approved: number; rejected: number; archived: number }

export interface Campaign {
  id: string; code: string; name: string; objective: string; description: string | null; project: Ref; channels: Channel[];
  start_date: string | null; end_date: string | null; status: CampaignStatus; created_by: PersonRef | null; created_at: string;
  updated_at: string; content: StatusCounts; allowed_actions: string[];
}

export interface CampaignInput {
  name: string; objective: string; description: string | null; project_id?: string; channels: Channel[];
  start_date: string | null; end_date: string | null; status: Exclude<CampaignStatus, "archived">;
}

export interface Content {
  id: string; code: string; campaign: Ref; project: Ref; channel: Channel; language: Language; headline: string | null; body: string;
  call_to_action: string | null; hashtags: string[]; status: ContentStatus; version: number; generated_by_ai: boolean;
  created_by: PersonRef | null; updated_at: string; submitted_at: string | null; decided_at: string | null; rejection_comment: string | null;
}

export interface FactWarning { kind: "price" | "percentage" | "bedrooms"; text: string; message: string }
export interface Version {
  version: number; channel: Channel; language: Language; headline: string | null; body: string; call_to_action: string | null;
  hashtags: string[]; note: string; edited_by: PersonRef | null; created_at: string;
}
export interface ApprovalRound {
  id: string; status: string; version: number | null; requested_by: PersonRef | null; created_at: string; completed_at: string | null;
  steps: { label: string; status: string; decided_by: PersonRef | null; decided_at: string | null; comment: string | null }[];
}
export interface ContentDetail extends Content {
  allowed_actions: string[]; approval_id: string | null; can_decide: boolean; decide_blocked_reason: string | null;
  approvals: ApprovalRound[]; versions: Version[]; fact_warnings: FactWarning[]; channel_limit: number; length: number;
}
export interface ContentInput {
  campaign_id?: string; channel: Channel; language: Language; headline: string | null; body: string; call_to_action: string | null;
  hashtags: string[]; note?: string | null;
}

export interface ProjectFacts {
  project: Ref; city: string; district: string | null; status: string; handover_date: string | null; is_published: boolean;
  is_demo_data: boolean; amenities: string[]; available_units: number; price_from_sar: string | null; description: string | null;
  bedroom_options: { bedrooms: number; available: number; price_from_sar: string; price_to_sar: string }[];
  payment_plans: { name: string; down_payment_pct: string; installments: number; installment_frequency: string; handover_pct: string }[];
}

const key = ["marketing"] as const;

export function useCampaigns(query: ListQuery & { status?: string; project_id?: string }) {
  return useQuery({
    queryKey: [...key, "campaigns", query],
    queryFn: ({ signal }) => api.get<Page<Campaign>>("/marketing/campaigns", { ...query }, signal),
    placeholderData: keepPreviousData,
  });
}

export function useCampaign(id: string | undefined) {
  return useQuery({ queryKey: [...key, "campaign", id], queryFn: () => api.get<Campaign>(`/marketing/campaigns/${id}`), enabled: Boolean(id) });
}

export function useContentList(query: ListQuery & { campaign_id?: string; status?: string; channel?: string; language?: string }) {
  return useQuery({
    queryKey: [...key, "content", query],
    queryFn: ({ signal }) => api.get<Page<Content>>("/marketing/content", { ...query }, signal),
    placeholderData: keepPreviousData,
  });
}

export function useContent(id: string | undefined) {
  return useQuery({ queryKey: [...key, "content-item", id], queryFn: () => api.get<ContentDetail>(`/marketing/content/${id}`), enabled: Boolean(id) });
}

export function useProjectFacts(projectId: string | undefined) {
  return useQuery({
    queryKey: [...key, "facts", projectId],
    queryFn: () => api.get<ProjectFacts>(`/marketing/projects/${projectId}/facts`),
    enabled: Boolean(projectId),
    staleTime: 60_000,
  });
}

export function useMarketingAIStatus() {
  return useQuery({ queryKey: [...key, "ai-status"], queryFn: () => api.get<{ enabled: boolean; reason: string }>("/marketing/ai-status"), staleTime: 60_000 });
}

export function checkFacts(body: { project_id: string; headline: string | null; body: string; call_to_action: string | null }) {
  return api.post<FactWarning[]>("/marketing/facts-check", body);
}

function useInvalidate() {
  const qc = useQueryClient();
  return () => Promise.all([qc.invalidateQueries({ queryKey: key }), qc.invalidateQueries({ queryKey: ["approvals"] })]);
}

export function useCampaignMutations(id?: string) {
  const invalidate = useInvalidate();
  return {
    save: useMutation({
      mutationFn: (body: Partial<CampaignInput>) => id ? api.patch<Campaign>(`/marketing/campaigns/${id}`, body) : api.post<Campaign>("/marketing/campaigns", body),
      onSuccess: invalidate,
    }),
    archive: useMutation({ mutationFn: (cid: string) => api.post<Campaign>(`/marketing/campaigns/${cid}/archive`), onSuccess: invalidate }),
  };
}

export function useContentMutations(id?: string) {
  const invalidate = useInvalidate();
  return {
    save: useMutation({
      mutationFn: (body: Partial<ContentInput>) => id ? api.patch<ContentDetail>(`/marketing/content/${id}`, body) : api.post<ContentDetail>("/marketing/content", body),
      onSuccess: invalidate,
    }),
    submit: useMutation({ mutationFn: (cid: string) => api.post<ContentDetail>(`/marketing/content/${cid}/submit`), onSuccess: invalidate }),
    archive: useMutation({ mutationFn: (cid: string) => api.post<ContentDetail>(`/marketing/content/${cid}/archive`), onSuccess: invalidate }),
  };
}
