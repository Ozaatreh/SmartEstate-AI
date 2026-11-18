import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ListQuery, type Page } from "@/lib/api-client";

// --- health -------------------------------------------------------------------------------
export interface Health {
  status: "ok" | "degraded";
  version: string;
  environment: string;
  database: "ok" | "unavailable";
  /** AI gateway availability: configuration plus the last real provider outcome (never "operational" from config alone). */
  ai: { state: "disabled" | "misconfigured" | "unverified" | "operational" | "degraded"; reason: string };
}

export function useHealth() {
  return useQuery({ queryKey: ["platform", "health"], queryFn: () => api.get<Health>("/health"), staleTime: 60_000 });
}

// --- notifications ----------------------------------------------------------------------------
export interface Notification {
  id: string;
  type: string;
  level: "info" | "success" | "warning" | "danger";
  title: string;
  body: string | null;
  link: string | null;
  entity_type: string | null;
  entity_id: string | null;
  read_at: string | null;
  created_at: string;
}

const nKey = ["notifications"] as const;

export function useNotifications(query: ListQuery & { unread_only?: string | boolean }) {
  return useQuery({
    queryKey: [...nKey, "list", query],
    queryFn: ({ signal }) => api.get<Page<Notification>>("/notifications", { ...query }, signal),
    placeholderData: keepPreviousData,
  });
}

export function useUnreadCount() {
  return useQuery({
    queryKey: [...nKey, "unread"],
    queryFn: () => api.get<{ unread: number }>("/notifications/unread-count"),
    refetchInterval: 60_000,
  });
}

export function useMarkRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<Notification>(`/notifications/${id}/read`),
    onSuccess: () => qc.invalidateQueries({ queryKey: nKey }),
  });
}

export function useMarkAllRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<{ marked: number }>("/notifications/read-all"),
    onSuccess: () => qc.invalidateQueries({ queryKey: nKey }),
  });
}

// --- audit ------------------------------------------------------------------------------------
export interface AuditLog {
  id: string;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  summary: string | null;
  changes: Record<string, unknown> | null;
  request_id: string | null;
  ip_address: string | null;
  created_at: string;
  actor: { id: string; full_name: string; email: string } | null;
}

export function useAuditLogs(query: ListQuery & { action?: string; entity_type?: string }, enabled = true) {
  return useQuery({
    queryKey: ["audit", "list", query],
    queryFn: ({ signal }) => api.get<Page<AuditLog>>("/audit-logs", { ...query }, signal),
    placeholderData: keepPreviousData,
    enabled,
  });
}
