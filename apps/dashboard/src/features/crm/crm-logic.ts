/** Pure CRM display helpers (tested in crm.test.tsx). */
import type { Stage } from "./api";

export const STAGES: { key: Stage; label: string }[] = [
  { key: "new", label: "New" },
  { key: "contacted", label: "Contacted" },
  { key: "qualified", label: "Qualified" },
  { key: "viewing", label: "Viewing" },
  { key: "negotiation", label: "Negotiation" },
  { key: "won", label: "Won" },
  { key: "lost", label: "Lost" },
];

export const OPEN_STAGES: Stage[] = ["new", "contacted", "qualified", "viewing", "negotiation"];

export const TIMELINES = [
  { value: "immediate", label: "Ready to buy now" },
  { value: "within_3_months", label: "Within 3 months" },
  { value: "within_6_months", label: "Within 6 months" },
  { value: "over_6_months", label: "More than 6 months" },
];

export const SOURCES = [
  { value: "walk_in", label: "Walk-in" },
  { value: "phone", label: "Phone" },
  { value: "website", label: "Website" },
  { value: "referral", label: "Referral" },
  { value: "campaign", label: "Campaign" },
  { value: "social", label: "Social" },
];

export const ACTIVITY_TYPES = [
  { value: "call", label: "Call" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "email", label: "Email" },
  { value: "viewing", label: "Viewing" },
  { value: "note", label: "Note" },
];

export function stageLabel(stage: string): string {
  return STAGES.find((s) => s.key === stage)?.label ?? stage;
}

export function timelineLabel(value: string | null | undefined): string {
  return TIMELINES.find((t) => t.value === value)?.label ?? "—";
}

/** Closing a lead needs a reason; the API enforces the same rule. */
export function stageNeedsReason(stage: Stage): boolean {
  return stage === "won" || stage === "lost";
}

/** Index of the stage on the pipeline (lost sits outside the forward path). */
export function stageProgress(stage: Stage): number {
  return stage === "lost" ? -1 : STAGES.findIndex((s) => s.key === stage);
}

export function budgetLabel(min: string | null, max: string | null, format: (v: string) => string): string {
  if (min && max) return `${format(min)} – ${format(max)}`;
  if (max) return `Up to ${format(max)}`;
  if (min) return `From ${format(min)}`;
  return "—";
}

/** "2026-11-18T09:00:00Z" → value for <input type="datetime-local"> in the viewer's time zone. */
export function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function fromLocalInput(value: string): string | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

export function hoursUntil(iso: string, now: Date = new Date()): number {
  return Math.round((new Date(iso).getTime() - now.getTime()) / 3_600_000);
}
