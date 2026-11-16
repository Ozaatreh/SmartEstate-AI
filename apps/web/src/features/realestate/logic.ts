import type { UnitStatus } from "./api";

export const DEMO_LABEL = "Illustrative / Fictional Demo Data";

export const UNIT_STATUS_STYLE: Record<UnitStatus, string> = {
  available: "border-success/40 bg-success-subtle text-success hover:border-success",
  reserved: "border-warning/50 bg-warning-subtle text-warning hover:border-warning",
  sold: "border-brand/40 bg-brand-subtle text-brand hover:border-brand",
  blocked: "border-border bg-surface-sunken text-fg-muted hover:border-border-strong",
};

export const UNIT_TYPES = [
  { value: "studio", label: "Studio" },
  { value: "apartment", label: "Apartment" },
  { value: "duplex", label: "Duplex" },
  { value: "penthouse", label: "Penthouse" },
  { value: "townhouse", label: "Townhouse" },
];

export function bedroomsLabel(n: number): string {
  return n === 0 ? "Studio" : `${n} BR`;
}

export const PROJECT_STATUSES = [
  { value: "planning", label: "Planning" },
  { value: "launched", label: "Launched" },
  { value: "under_construction", label: "Under construction" },
  { value: "completed", label: "Completed" },
];

export const FREQUENCIES = [
  { value: "monthly", label: "Monthly" },
  { value: "quarterly", label: "Quarterly" },
  { value: "semi_annual", label: "Semi-annual" },
  { value: "annual", label: "Annual" },
];

/** Same rule the API applies to codes and unit numbers. */
export const CODE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9-]*$/;

/** Commercial details are frozen once a unit is reserved or sold (the API refuses them with 409). */
export const LOCKED_WHEN_COMMITTED = ["unit_type", "bedrooms", "floor", "area_sqm", "list_price"] as const;

export function unitIsCommitted(status: string): boolean {
  return status === "reserved" || status === "sold";
}

/** One amenity per line or comma; trimmed and de-duplicated (mirrors the API). */
export function parseAmenities(text: string): string[] {
  return [...new Set(text.split(/[\n,]/).map((a) => a.trim()).filter(Boolean))];
}

/** Payment-plan shares, checked like the API: 0–100 each, total ≤ 100, and 100 when there are no installments. */
export function planShareError(down: string, handover: string, installments: string): string | null {
  const d = Number(down), h = Number(handover), n = Number(installments);
  if (!/^\d+(\.\d{1,2})?$/.test(down) || d > 100) return "Down payment must be a percentage between 0 and 100.";
  if (!/^\d+(\.\d{1,2})?$/.test(handover) || h > 100) return "Handover share must be a percentage between 0 and 100.";
  if (!Number.isInteger(n) || n < 0 || n > 240) return "Installments must be a whole number from 0 to 240.";
  if (d + h > 100) return "Down payment and handover shares cannot exceed 100%.";
  if (n === 0 && d + h !== 100) return "Without installments, down payment and handover must add up to 100%.";
  return null;
}

/** Positive amount with at most two decimals ("925000", "112.5"). */
export function isPositiveAmount(value: string): boolean {
  return /^\d+(\.\d{1,2})?$/.test(value) && Number(value) > 0;
}

/** Only the fields that changed — so locked fields of a reserved/sold unit are never sent. */
export function changedFields<T extends Record<string, unknown>>(before: Record<string, unknown>, after: T): Partial<T> {
  return Object.fromEntries(Object.entries(after).filter(([k, v]) => String(before[k] ?? "") !== String(v ?? ""))) as Partial<T>;
}
