/**
 * One mapping from domain statuses to visual tones (UI_UX_DESIGN.md § 6 — StatusBadge).
 * Modules add their statuses here so the same status always looks the same everywhere.
 */
export type Tone = "success" | "warning" | "danger" | "info" | "neutral" | "brand" | "ai";

const STATUS_TONES: Record<string, Tone> = {
  // generic lifecycle
  draft: "neutral",
  active: "success",
  inactive: "neutral",
  archived: "neutral",
  cancelled: "neutral",
  pending: "warning",
  pending_approval: "warning",
  approved: "success",
  rejected: "danger",
  completed: "success",
  failed: "danger",
  running: "info",
  succeeded: "success",
  skipped: "neutral",
  // notifications
  info: "info",
  success: "success",
  warning: "warning",
  danger: "danger",
  // procurement & approvals
  sourcing: "info",
  waiting: "neutral",
  received: "neutral",
  selected: "success",
  not_selected: "neutral",
  closed: "neutral",
  // projects
  planned: "info",
  on_hold: "warning",
  // priorities
  low: "neutral",
  normal: "info",
  high: "warning",
  urgent: "danger",
  // real estate (later phases)
  available: "success",
  reserved: "warning",
  sold: "brand",
  blocked: "neutral",
};

export function toneFor(status: string | null | undefined): Tone {
  return (status && STATUS_TONES[status]) || "neutral";
}

export function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  const text = value.replace(/[._]/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}
