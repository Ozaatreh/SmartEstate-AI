/**
 * Formatting rules (UI_UX_DESIGN.md § 2.5). Money arrives from the API as decimal strings and is
 * never converted to floating point for arithmetic — only formatted for display.
 */

import { activeLang } from "@/lib/i18n";

const groupInt = (digits: string) => digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");

/** "1250000.5" → "SAR 1,250,000.50" (decimals: 0 | 2). Works on strings to keep exact values. */
export function formatMoney(value: string | number | null | undefined, opts: { decimals?: 0 | 2; currency?: string } = {}): string {
  if (value === null || value === undefined || value === "") return "—";
  const { decimals = 0, currency = "SAR" } = opts;
  const raw = String(value).trim();
  if (!/^-?\d+(\.\d+)?$/.test(raw)) return "—";
  const negative = raw.startsWith("-");
  const [intPart = "0", fracPart = ""] = raw.replace("-", "").split(".");
  let int = intPart.replace(/^0+(?=\d)/, "");
  let frac = "";
  if (decimals === 2) {
    const padded = (fracPart + "000").slice(0, 3);
    let cents = Number(padded.slice(0, 2)) + (Number(padded[2]) >= 5 ? 1 : 0);
    if (cents === 100) {
      cents = 0;
      int = (BigInt(int) + 1n).toString();
    }
    frac = "." + String(cents).padStart(2, "0");
  } else if (Number(fracPart[0] ?? 0) >= 5) {
    int = (BigInt(int) + 1n).toString();
  }
  const amount = `${negative ? "−" : ""}${groupInt(int)}${frac}`;
  // Arabic: "435,000 ر.س" (Western digits, as on Saudi price lists); English: "SAR 435,000".
  return activeLang() === "ar" && currency === "SAR" ? `${amount} ر.س` : `${negative ? "−" : ""}${currency} ${groupInt(int)}${frac}`;
}

export function formatNumber(value: number | null | undefined, maximumFractionDigits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits }).format(value);
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(digits)}%`;
}

const DATE = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });
const DATE_AR = new Intl.DateTimeFormat("ar-SA-u-nu-latn-ca-gregory", { day: "numeric", month: "long", year: "numeric" });
const DATETIME = new Intl.DateTimeFormat("en-GB", {
  day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
});

export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const d = typeof value === "string" ? new Date(value) : value;
  return Number.isNaN(d.getTime()) ? "—" : (activeLang() === "ar" ? DATE_AR : DATE).format(d);
}

export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const d = typeof value === "string" ? new Date(value) : value;
  return Number.isNaN(d.getTime()) ? "—" : DATETIME.format(d);
}

export function formatRelative(value: string | Date | null | undefined, now: Date = new Date()): string {
  if (!value) return "—";
  const d = typeof value === "string" ? new Date(value) : value;
  const s = Math.round((now.getTime() - d.getTime()) / 1000);
  if (Number.isNaN(s)) return "—";
  if (s <= -45) {
    // Future times (follow-ups, reservation expiry): "in 30 min", "in 5 h", "in 2 d", then the date.
    const fm = Math.round(-s / 60);
    if (fm < 60) return `in ${fm} min`;
    const fh = Math.round(fm / 60);
    if (fh < 24) return `in ${fh} h`;
    const fd = Math.round(fh / 24);
    if (fd < 7) return `in ${fd} d`;
    return formatDate(d);
  }
  if (s < 45) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  const days = Math.round(h / 24);
  if (days < 7) return `${days} d ago`;
  return formatDate(d);
}
