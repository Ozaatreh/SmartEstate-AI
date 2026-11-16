import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { LogoMark } from "@/components/system/brand";
import { ErrorState, PermissionState } from "@/components/system/states";
import { setUnauthenticatedHandler } from "@/lib/api-client";
import { meKey, useMe, type Me } from "./api";

interface AuthValue {
  user: Me | null;
  can: (permission: string) => boolean;
}

const AuthContext = React.createContext<AuthValue>({ user: null, can: () => false });

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient();
  const me = useMe();

  React.useEffect(() => {
    // Any 401 (expired / revoked session) drops the cached user → guards redirect to sign-in.
    setUnauthenticatedHandler(() => qc.setQueryData(meKey, null));
    return () => setUnauthenticatedHandler(null);
  }, [qc]);

  const value = React.useMemo<AuthValue>(() => {
    const user = me.data ?? null;
    const perms = new Set(user?.permissions ?? []);
    return { user, can: (p) => Boolean(user?.is_super_admin || perms.has(p)) };
  }, [me.data]);

  if (me.isPending) return <SplashScreen />;
  if (me.isError) {
    return (
      <div className="grid min-h-dvh place-items-center bg-canvas">
        <ErrorState error={me.error} onRetry={() => void me.refetch()} title="Can't reach SmartEstate" />
      </div>
    );
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  return React.useContext(AuthContext);
}

/** UI gating only — the API is the enforcement point. */
export function useCan(permission: string | undefined): boolean {
  const { can } = useAuth();
  return permission ? can(permission) : true;
}

export function RequireAuth() {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) {
    const next = location.pathname + location.search;
    return <Navigate to={next && next !== "/" ? `/sign-in?next=${encodeURIComponent(next)}` : "/sign-in"} replace />;
  }
  return <Outlet />;
}

export function RequirePermission({ permission, children }: { permission: string; children: React.ReactNode }) {
  const allowed = useCan(permission);
  return allowed ? <>{children}</> : <PermissionState className="min-h-[60vh]" />;
}

function SplashScreen() {
  return (
    <div className="grid min-h-dvh place-items-center bg-canvas" aria-busy="true" aria-label="Loading SmartEstate AI">
      <LogoMark className="size-9 animate-pulse" />
    </div>
  );
}
