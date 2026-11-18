/**
 * The only HTTP entry point. Same-origin requests (Vite proxies /api), cookie session,
 * CSRF header on every request, and one error type for the whole app.
 */

export interface ApiErrorBody {
  code: string;
  message: string;
  request_id?: string | null;
  details?: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly details: unknown;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.requestId = body.request_id ?? null;
    this.details = body.details;
  }

  /** Field-level errors from a 422 response, keyed by field path. */
  get fieldErrors(): Record<string, string> {
    const fields = (this.details as { fields?: { field: string | null; message: string }[] } | undefined)?.fields;
    return Object.fromEntries((fields ?? []).filter((f) => f.field).map((f) => [f.field as string, f.message]));
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

const BASE = "/api/v1";
let onUnauthenticated: (() => void) | null = null;

/** Registered by the auth provider so a 401 anywhere returns the user to sign-in. */
export function setUnauthenticatedHandler(handler: (() => void) | null): void {
  onUnauthenticated = handler;
}

function buildUrl(path: string, query?: Query): string {
  const url = new URL(BASE + path, window.location.origin);
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  }
  return url.pathname + url.search;
}

async function request<T>(method: string, path: string, opts: { query?: Query; body?: unknown; signal?: AbortSignal } = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(buildUrl(path, opts.query), {
      method,
      credentials: "same-origin",
      signal: opts.signal,
      headers: {
        Accept: "application/json",
        "X-Requested-With": "XMLHttpRequest",
        ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(0, { code: "network_error", message: "Can't reach the server. Check your connection and try again." });
  }

  if (response.status === 204) return undefined as T;
  const text = await response.text();
  const data = text ? safeJson(text) : undefined;

  if (!response.ok) {
    const body = (data as { error?: ApiErrorBody } | undefined)?.error ?? {
      code: "http_error",
      message: response.status >= 500 ? "Something went wrong on our side. Try again in a moment." : "The request failed.",
      request_id: response.headers.get("x-request-id"),
    };
    const error = new ApiError(response.status, body);
    if (response.status === 401 && !path.startsWith("/auth/login")) onUnauthenticated?.();
    throw error;
  }
  return data as T;
}

/** POST that returns a file (PDF, PNG…). Errors come back as the usual JSON envelope and throw ApiError. */
export async function apiDownload(path: string, body: unknown): Promise<{ blob: Blob; filename: string }> {
  let response: Response;
  try {
    response = await fetch(buildUrl(path), {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, { code: "network_error", message: "Can't reach the server. Check your connection and try again." });
  }
  if (!response.ok) {
    const data = safeJson(await response.text()) as { error?: ApiErrorBody } | undefined;
    if (response.status === 401) onUnauthenticated?.();
    throw new ApiError(response.status, data?.error ?? { code: "http_error", message: "The file couldn't be generated.", request_id: response.headers.get("x-request-id") });
  }
  const match = /filename="([^"]+)"/.exec(response.headers.get("content-disposition") ?? "");
  return { blob: await response.blob(), filename: match?.[1] ?? "download" };
}

/** PUT a file as the raw request body (no multipart); the original name travels in X-Filename. */
export async function apiUpload<T>(path: string, file: File): Promise<T> {
  let response: Response;
  try {
    response = await fetch(buildUrl(path), {
      method: "PUT",
      credentials: "same-origin",
      headers: { "Content-Type": "application/octet-stream", "X-Requested-With": "XMLHttpRequest", "X-Filename": encodeURIComponent(file.name) },
      body: file,
    });
  } catch {
    throw new ApiError(0, { code: "network_error", message: "Can't reach the server. Check your connection and try again." });
  }
  const data = safeJson(await response.text());
  if (!response.ok) {
    if (response.status === 401) onUnauthenticated?.();
    throw new ApiError(response.status, (data as { error?: ApiErrorBody } | undefined)?.error ?? { code: "http_error", message: "The upload failed.", request_id: response.headers.get("x-request-id") });
  }
  return data as T;
}

/** Hands a blob to the browser as a download. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

export const api = {
  get: <T>(path: string, query?: Query, signal?: AbortSignal) => request<T>("GET", path, { query, signal }),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, { body }),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, { body }),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, { body }),
  delete: <T>(path: string) => request<T>("DELETE", path),
};

/** Shared list contract (backend app/common/listing.py). */
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface ListQuery {
  q?: string;
  sort?: string;
  page?: number;
  page_size?: number;
}

/** One server-sent event from a streaming endpoint (`event:` name + JSON `data:`). */
export interface StreamEvent { type: string; [key: string]: unknown }

/** Parses a server-sent-events body. Exported for tests. */
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

/**
 * POSTs JSON and reads a `text/event-stream` answer, calling `onEvent` for each event as it arrives.
 * A non-2xx answer is thrown as `ApiError` (same contract as `api.*`), before any event.
 */
export async function apiStream(path: string, body: unknown, onEvent: (e: StreamEvent) => void, signal?: AbortSignal): Promise<void> {
  let response: Response;
  try {
    response = await fetch(buildUrl(path), {
      method: "POST",
      credentials: "same-origin",
      signal,
      headers: { Accept: "text/event-stream", "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(body),
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(0, { code: "network_error", message: "Can't reach the server. Check your connection and try again." });
  }
  if (!response.ok || !response.body) {
    const data = safeJson(await response.text()) as { error?: ApiErrorBody } | undefined;
    const error = new ApiError(response.status, data?.error ?? { code: "http_error", message: "The request failed." });
    if (response.status === 401) onUnauthenticated?.();
    throw error;
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
