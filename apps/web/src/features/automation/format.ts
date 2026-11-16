/** Plain helpers for automation views (kept apart from components for fast refresh). */

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  return `${Math.floor(ms / 60_000)} min ${Math.round((ms % 60_000) / 1000)} s`;
}

export function entityLink(entityType: string | null, entityId: string | null): string | null {
  if (!entityId) return null;
  if (entityType === "purchase_request") return `/procurement/requests/${entityId}`;
  if (entityType === "budget") return `/finance/budgets/${entityId}`;
  return null;
}
