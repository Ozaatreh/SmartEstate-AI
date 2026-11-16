import { AlertTriangle, Copy, Inbox, Lock, RotateCw, SearchX } from "lucide-react";
import type * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/primitives";
import { ApiError } from "@/lib/api-client";
import { cn } from "@/lib/utils";

function StateFrame({ icon, title, description, children, className, tone = "neutral" }: {
  icon: React.ReactNode; title: string; description?: React.ReactNode; children?: React.ReactNode; className?: string;
  tone?: "neutral" | "danger";
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-12 text-center", className)}>
      <div className={cn(
        "mb-4 grid size-10 place-items-center rounded-[var(--radius-panel)] border",
        tone === "danger" ? "border-danger/20 bg-danger-subtle text-danger" : "border-border bg-surface-subtle text-fg-muted",
      )}>
        {icon}
      </div>
      <h3 className="text-body font-semibold text-fg">{title}</h3>
      {description && <p className="mt-1 max-w-sm text-body text-fg-secondary">{description}</p>}
      {children && <div className="mt-4 flex flex-wrap items-center justify-center gap-2">{children}</div>}
    </div>
  );
}

/** Empty: why it is empty + the next action. Use `filtered` when filters produced no rows. */
export function EmptyState({ title, description, action, filtered, onClearFilters, icon, className }: {
  title?: string; description?: React.ReactNode; action?: React.ReactNode; filtered?: boolean; onClearFilters?: () => void;
  icon?: React.ReactNode; className?: string;
}) {
  if (filtered) {
    return (
      <StateFrame icon={<SearchX className="size-5" />} title={title ?? "No matching results"} className={className}
        description={description ?? "Try a different search or remove some filters."}>
        {onClearFilters && <Button size="sm" onClick={onClearFilters}>Clear filters</Button>}
      </StateFrame>
    );
  }
  return (
    <StateFrame icon={icon ?? <Inbox className="size-5" />} title={title ?? "Nothing here yet"} description={description} className={className}>
      {action}
    </StateFrame>
  );
}

/** Error: message, retry, and the request ID support can look up. */
export function ErrorState({ error, onRetry, title, className }: { error: unknown; onRetry?: () => void; title?: string; className?: string }) {
  const apiError = error instanceof ApiError ? error : null;
  if (apiError?.status === 403) return <PermissionState className={className} />;
  const message = apiError?.message ?? "Something unexpected happened while loading this section.";
  return (
    <StateFrame icon={<AlertTriangle className="size-5" />} tone="danger" title={title ?? "Couldn't load this"} description={message} className={className}>
      {onRetry && <Button size="sm" onClick={onRetry}><RotateCw /> Try again</Button>}
      {apiError?.requestId && (
        <Button size="sm" variant="ghost" onClick={() => {
          void navigator.clipboard?.writeText(apiError.requestId ?? "");
          toast.success("Request ID copied");
        }}>
          <Copy /> <span className="tabular">Ref {apiError.requestId.slice(0, 8)}</span>
        </Button>
      )}
    </StateFrame>
  );
}

export function PermissionState({ className, description }: { className?: string; description?: string }) {
  return (
    <StateFrame icon={<Lock className="size-5" />} title="You don't have access to this" className={className}
      description={description ?? "Ask an administrator to grant your role the required permission."} />
  );
}

/** Skeletons shaped like the final content. */
export function TableSkeleton({ rows = 6, columns = 4 }: { rows?: number; columns?: number }) {
  return (
    <div className="divide-y divide-border-subtle" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, r) => (
        <div key={r} className="flex h-10 items-center gap-6 px-4">
          {Array.from({ length: columns }, (_, c) => (
            <Skeleton key={c} className={cn("h-3", c === 0 ? "w-40" : c === columns - 1 ? "ml-auto w-16" : "w-24")} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function ListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-4 p-4" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-start gap-3">
          <Skeleton className="size-8 rounded-full" />
          <div className="flex-1 space-y-2"><Skeleton className="h-3 w-3/5" /><Skeleton className="h-3 w-2/5" /></div>
        </div>
      ))}
    </div>
  );
}
