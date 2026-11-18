import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";

export interface Me {
  id: string;
  email: string;
  full_name: string;
  job_title: string | null;
  initials: string;
  roles: { code: string; name: string }[];
  permissions: string[];
  is_super_admin: boolean;
  last_login_at: string | null;
  session_expires_at: string | null;
}

export const meKey = ["auth", "me"] as const;

/** Current user, or null when signed out (401 is an expected state, not an error). */
export function useMe() {
  return useQuery({
    queryKey: meKey,
    queryFn: async () => {
      try {
        return await api.get<Me>("/auth/me");
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) return null;
        throw err;
      }
    },
    staleTime: 5 * 60_000,
    retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 2,
  });
}

/**
 * Drops every cached query except the current-user one. (`queryClient.clear()` would also detach
 * the mounted `useMe` observer, so the app would never see the new user.)
 */
function resetUserData(qc: ReturnType<typeof useQueryClient>, me: Me | null) {
  qc.removeQueries({ predicate: (q) => q.queryKey[0] !== meKey[0] });
  qc.setQueryData(meKey, me);
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; password: string }) => api.post<Me>("/auth/login", body),
    onSuccess: (me) => resetUserData(qc, me),
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<void>("/auth/logout"),
    onSettled: () => resetUserData(qc, null),
  });
}
