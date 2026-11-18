/**
 * Public API client for the marketing website.
 *
 * It can only reach `/api/v1/public/*`, sends no staff credentials of its own, and the dev server proxies nothing else.
 * This is a convenience and defence in depth, NOT the security boundary: FastAPI requires authentication for every
 * non-public endpoint and returns only public fields from public ones, whatever any frontend does.
 */

const BASE = "/api/v1/public";

export interface ApiErrorBody { code: string; message: string; request_id?: string | null; details?: unknown }

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.details = body.details;
  }

  private get fields(): { field: string | null; message: string }[] {
    const d = this.details as { fields?: { field: string | null; message: string }[] } | undefined;
    return Array.isArray(d?.fields) ? d.fields : [];
  }

  /** Field errors from a 422, keyed by field name (server-side validation is the source of truth). */
  get fieldErrors(): Record<string, string> {
    return Object.fromEntries(this.fields.filter((f) => f.field).map((f) => [f.field as string, clean(f.message)]));
  }

  /** Whole-form rule errors (e.g. "Provide a phone number or an e-mail address."). */
  get formErrors(): string[] {
    return this.fields.filter((f) => !f.field).map((f) => clean(f.message));
  }
}

function clean(message: string): string {
  return message.replace(/^Value error,\s*/i, "");
}

/** Only public paths are allowed ("/projects", "/inquiries", …), resolved under /api/v1/public. */
export function publicUrl(path: string, query?: Record<string, string | number | null | undefined>): string {
  if (!path.startsWith("/") || path.includes("..") || /^\/\//.test(path)) throw new Error(`Invalid public API path: ${path}`);
  const url = new URL(BASE + path, window.location.origin);
  for (const [k, v] of Object.entries(query ?? {})) if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  return url.pathname + url.search;
}

function safeJson(text: string): unknown {
  try { return JSON.parse(text); } catch { return undefined; }
}

async function request<T>(method: "GET" | "POST", path: string, body?: unknown, query?: Record<string, string | number | null | undefined>): Promise<T> {
  let response: Response;
  try {
    response = await fetch(publicUrl(path, query), {
      method,
      credentials: "same-origin", // only the anonymous visitor cookie of the assistant is ever needed
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest", ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, { code: "network_error", message: "Can't reach SmartEstate right now. Check your connection and try again." });
  }
  const text = await response.text();
  const data = text ? safeJson(text) : undefined;
  if (!response.ok) {
    throw new ApiError(response.status, (data as { error?: ApiErrorBody } | undefined)?.error ?? {
      code: "http_error", message: response.status >= 500 ? "Something went wrong on our side. Please try again." : "The request failed.",
    });
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, query?: Record<string, string | number | null | undefined>) => request<T>("GET", path, undefined, query),
  post: <T>(path: string, body: unknown) => request<T>("POST", path, body),
};

// --- server-sent events (property assistant) -----------------------------------------------------------------
export interface StreamEvent { type: string; [key: string]: unknown }

export function parseSseChunk(buffer: string): { events: StreamEvent[]; rest: string } {
  const events: StreamEvent[] = [];
  const blocks = buffer.split(/\r?\n\r?\n/);
  const rest = blocks.pop() ?? "";
  for (const block of blocks) {
    const data = block.split(/\r?\n/).filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trimStart()).join("\n");
    const parsed = data ? safeJson(data) : undefined;
    if (parsed && typeof parsed === "object" && typeof (parsed as StreamEvent).type === "string") events.push(parsed as StreamEvent);
  }
  return { events, rest };
}

export async function apiStream(path: string, body: unknown, onEvent: (e: StreamEvent) => void, signal?: AbortSignal): Promise<void> {
  let response: Response;
  try {
    response = await fetch(publicUrl(path), {
      method: "POST", credentials: "same-origin", signal,
      headers: { Accept: "text/event-stream", "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(body),
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(0, { code: "network_error", message: "Can't reach SmartEstate right now. Check your connection and try again." });
  }
  if (!response.ok || !response.body) {
    const data = safeJson(await response.text()) as { error?: ApiErrorBody } | undefined;
    throw new ApiError(response.status, data?.error ?? { code: "http_error", message: "The request failed." });
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    const parsed = parseSseChunk(buffer + value);
    buffer = parsed.rest;
    parsed.events.forEach(onEvent);
  }
  parseSseChunk(buffer + "\n\n").events.forEach(onEvent);
}

// --- public types (mirror app/public/catalog.py) -------------------------------------------------------------
export interface PublicProject {
  code: string; name: string; city: string; district: string | null; status: string; handover_date: string | null;
  is_demo_data: boolean; available_units: number; price_from_sar: string | null; cover_image: string | null;
}
export interface PublicPlan { name: string; down_payment_pct: string; installments: number; installment_frequency: string; handover_pct: string; description: string | null }
export interface PublicProjectDetail extends PublicProject {
  description: string | null; amenities: string[]; media: { url: string; caption: string | null; kind: string }[];
  payment_plans: PublicPlan[]; bedroom_options: number[]; location: PublicLocation; models: PublicModel[];
}
export interface PublicIllustrativePoint {
  label: string; latitude: string; longitude: string; notice: string; directions_url: string; maps_url: string;
}
/** Exact address, coordinates and links are present only when the location is verified (never for demo projects). */
export interface PublicLocation {
  district: string | null; city: string; country: string | null; address: string | null;
  latitude: string | null; longitude: string | null; verified: boolean; directions_url: string | null; maps_url: string | null;
  /** A separately stored, labelled reference point for projects whose own location isn't verified (never their address). */
  illustrative?: PublicIllustrativePoint | null;
}
export interface PublicUnit {
  code: string; project: string; project_code: string; type: string; bedrooms: number; bathrooms: number; floor: number;
  area_sqm: string; view: string | null; list_price_sar: string; status: string;
}
export interface PublicPlanBreakdown {
  name: string; down_payment_pct: string; down_payment_sar: string; installments: number; installment_frequency: string;
  installment_amount_sar: string | null; last_installment_amount_sar: string | null; handover_pct: string; handover_payment_sar: string; total_sar: string;
}
export interface PublicUnitDetail extends PublicUnit { project_is_demo_data: boolean; payment_plans: PublicPlanBreakdown[]; models: PublicModel[] }
/** An approved 3D model (Phase 7E). `file_url` is a public API path; no storage details are ever exposed. */
export interface PublicModel {
  id: string; title: string; caption: string | null; representation: "design" | "as_built" | "illustrative"; credit: string;
  format: "glb" | "gltf"; size_bytes: number; file_url: string; unit_code: string | null;
}
