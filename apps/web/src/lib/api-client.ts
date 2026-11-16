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
