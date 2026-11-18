import { IMAGE_UPLOAD, type MediaItem, type UnitStatus } from "./api";

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

/** Phase 7D: latitude/longitude as typed in the project form. Returns field errors (the API enforces the same rules). */
export function coordinateErrors(lat: string, lng: string, verified: boolean): { latitude?: string; longitude?: string } {
  const e: { latitude?: string; longitude?: string } = {};
  const num = /^-?\d{1,3}(\.\d{1,6})?$/;
  if (lat.trim() && (!num.test(lat.trim()) || Math.abs(Number(lat)) > 90)) e.latitude = "Between -90 and 90, up to 6 decimals.";
  if (lng.trim() && (!num.test(lng.trim()) || Math.abs(Number(lng)) > 180)) e.longitude = "Between -180 and 180, up to 6 decimals.";
  if (!e.latitude && !e.longitude && Boolean(lat.trim()) !== Boolean(lng.trim())) {
    e[lat.trim() ? "longitude" : "latitude"] = "Enter both coordinates, or neither.";
  }
  if (verified && !lat.trim() && !e.latitude) e.latitude = "Add coordinates before marking the location verified.";
  return e;
}

/** Kinds of project media. The kind decides how the website uses a link: only "image" can become the cover image. */
export const MEDIA_KINDS = [
  { value: "image", label: "Image" },
  { value: "brochure", label: "Brochure" },
  { value: "tour", label: "Virtual tour" },
  { value: "video", label: "Video" },
];

export interface MediaRow { key: string; url: string; caption: string; kind: string; local?: MediaItem }

/** Project media as editable rows. Uploaded images (`local`) keep every stored field; only the ones edited change. */
export function mediaRows(media: MediaItem[] = []): MediaRow[] {
  return media.map((m, i) => (m.file
    ? { key: `m${i}`, url: "", caption: m.caption ?? "", kind: "image", local: m }
    : { key: `m${i}`, url: m.url ?? "", caption: m.caption ?? "", kind: MEDIA_KINDS.some((k) => k.value === m.kind) ? m.kind! : "image" }));
}

/** Checks a picked file before it is sent (the API checks its real content again). */
export function imageFileProblem(file: File): string | null {
  if (!IMAGE_UPLOAD.types.includes(file.type)) return "Choose a JPEG, PNG or WebP image.";
  if (file.size > IMAGE_UPLOAD.maxBytes) return "Images can be at most 10 MB.";
  return null;
}

/** A row for an image just uploaded from the device: not approved until its source and licence are recorded. */
export function uploadedRow(key: string, file: string): MediaRow {
  return { key, url: "", caption: "", kind: "image", local: { kind: "image", file, approved: false } };
}

const clean = (v: string | null | undefined) => (v ?? "").trim() || undefined;

/** Rows back to the API payload, preserving each entry's kind and every field of uploaded entries. */
export function mediaPayload(rows: MediaRow[]): MediaItem[] {
  return rows
    .filter((r) => r.local || r.url.trim())
    .map((r) => {
      if (!r.local) return { url: r.url.trim(), caption: r.caption.trim() || null, kind: r.kind };
      const { caption, source, licence, ...rest } = r.local;
      const out: MediaItem = { ...rest };
      if (clean(caption)) out.caption = clean(caption);
      if (clean(source)) out.source = clean(source);
      if (clean(licence)) out.licence = clean(licence);
      return out;
    });
}

const NOT_IMAGE = /\.(pdf|docx?|pptx?|zip|mp4|mov|webm|html?)$/i;

/** True when the row can be the website's cover: an approved uploaded image, or a link marked Image to an image file. */
export function isCoverCandidate(r: MediaRow): boolean {
  if (r.local) return r.local.approved === true && !!clean(r.local.source) && !!clean(r.local.licence);
  if (r.kind !== "image" || !/^https?:\/\/\S+$/.test(r.url.trim())) return false;
  try { return !NOT_IMAGE.test(new URL(r.url.trim()).pathname); } catch { return false; }
}

/** Index of the row the website will use as its cover image (the first candidate), or -1. */
export const coverIndex = (rows: MediaRow[]) => rows.findIndex(isCoverCandidate);

export function mediaError(rows: MediaRow[]): string | undefined {
  const bad = rows.find((r) => !r.local && r.url.trim() && !/^https?:\/\/\S+$/.test(r.url.trim()));
  if (bad) return "Links must start with http:// or https://.";
  const captions = rows.map((r) => (r.local ? r.local.caption ?? "" : r.caption));
  if (captions.some((c) => c.trim().length > 150)) return "Captions are at most 150 characters.";
  if (rows.some((r) => r.local && [r.local.source, r.local.licence].some((v) => (v ?? "").trim().length > 150))) {
    return "Source and licence are at most 150 characters.";
  }
  if (rows.some((r) => r.local?.approved && !(clean(r.local.source) && clean(r.local.licence)))) {
    return "An approved image needs its source and licence.";
  }
  return undefined;
}
