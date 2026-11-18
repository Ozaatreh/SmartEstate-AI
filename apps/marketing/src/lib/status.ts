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
  issued: "info",
  // projects
  planned: "info",
  on_hold: "warning",
  // priorities
  low: "neutral",
  normal: "info",
  high: "warning",
  urgent: "danger",
  // CRM pipeline & reservations (Phase 5)
  new: "info",
  contacted: "info",
  qualified: "brand",
  viewing: "brand",
  negotiation: "warning",
  won: "success",
  lost: "neutral",
  expired: "neutral",
  converted: "success",
  hot: "danger",
  warm: "warning",
  cold: "info",
  // real estate projects
  launched: "success",
  under_construction: "info",
  planning: "neutral",
  // real estate units
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

/** Public-facing labels (project and unit statuses) in both languages; anything else falls back to `humanize`. */
const LABELS: Record<string, { en: string; ar: string }> = {
  launched: { en: "Launched", ar: "مُطلق" },
  under_construction: { en: "Under construction", ar: "قيد الإنشاء" },
  planning: { en: "Planning", ar: "قيد التخطيط" },
  completed: { en: "Completed", ar: "مكتمل" },
  available: { en: "Available", ar: "متاحة" },
  reserved: { en: "Reserved", ar: "محجوزة" },
  sold: { en: "Sold", ar: "مُباعة" },
  blocked: { en: "Unavailable", ar: "غير متاحة" },
};

export function statusLabel(status: string | null | undefined, lang: "en" | "ar" = "en"): string {
  const l = status ? LABELS[status] : undefined;
  return l ? l[lang] : humanize(status);
}

const UNIT_TYPES: Record<string, { en: string; ar: string }> = {
  studio: { en: "Studio", ar: "استوديو" },
  apartment: { en: "Apartment", ar: "شقة" },
  duplex: { en: "Duplex", ar: "دوبلكس" },
  penthouse: { en: "Penthouse", ar: "بنتهاوس" },
  townhouse: { en: "Townhouse", ar: "تاون هاوس" },
};

export function unitTypeLabel(type: string, lang: "en" | "ar" = "en"): string {
  return UNIT_TYPES[type]?.[lang] ?? humanize(type);
}

const FREQUENCIES: Record<string, { en: string; ar: string }> = {
  monthly: { en: "monthly", ar: "شهرية" },
  quarterly: { en: "quarterly", ar: "ربع سنوية" },
  semi_annual: { en: "semi-annual", ar: "نصف سنوية" },
  annual: { en: "annual", ar: "سنوية" },
  construction_linked: { en: "construction-linked", ar: "مرتبطة بالإنشاء" },
};

export function frequencyLabel(freq: string, lang: "en" | "ar" = "en"): string {
  return FREQUENCIES[freq]?.[lang] ?? humanize(freq).toLowerCase();
}
