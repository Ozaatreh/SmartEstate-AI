import { Compass } from "lucide-react";
import { isRouteErrorResponse, Link, useRouteError } from "react-router-dom";
import { Wordmark } from "@/components/system/brand";
import { ErrorState } from "@/components/system/states";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
      <div className="mb-4 grid size-10 place-items-center rounded-[var(--radius-panel)] border border-border bg-surface-subtle text-fg-muted"><Compass className="size-5" /></div>
      <p className="tabular text-small font-medium text-brand">404</p>
      <h1 className="mt-1 text-h3 font-semibold">This page doesn't exist</h1>
      <p className="mt-1 max-w-sm text-body text-fg-secondary">The link may be outdated, or the module isn't available yet.</p>
      <Button asChild variant="primary" className="mt-5"><Link to="/">Back to home</Link></Button>
    </div>
  );
}

export function RouteErrorPage() {
  const error = useRouteError();
  if (isRouteErrorResponse(error) && error.status === 404) return <div className="p-8"><NotFoundPage /></div>;
  return (
    <div className="grid min-h-dvh place-items-center bg-canvas px-4">
      <div className="w-full max-w-md text-center">
        <div className="mb-6 flex justify-center"><Wordmark /></div>
        <ErrorState error={error} title="This page failed to load" onRetry={() => window.location.reload()} />
      </div>
    </div>
  );
}
