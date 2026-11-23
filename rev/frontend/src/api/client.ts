import { API_BASE } from "../config";

/** An API failure. FastAPI answers {"detail": "..."} or, for validation, {"detail": [{loc, msg}, ...]}. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function toApiError(status: number, body: unknown, statusText = ""): ApiError {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return new ApiError(status, detail);
  if (Array.isArray(detail)) {
    const parts = detail.map((d: { loc?: unknown[]; msg?: string }) => {
      const field = Array.isArray(d.loc) ? d.loc.filter((x) => x !== "body").join(".") : "";
      return field ? `${field}: ${d.msg}` : String(d.msg);
    });
    return new ApiError(status, parts.join("; ") || "Invalid request");
  }
  return new ApiError(status, statusText || `Request failed (${status})`);
}

export function errorMessage(e: unknown): string {
  if (e instanceof Error) return e.message;
  return String(e);
}

// ---- session token ------------------------------------------------------------------------------
// The API issues a JWT at /api/auth/login; the console keeps it in localStorage under "token" (the
// key the old console used, so signed-in users stay signed in across the upgrade).

const TOKEN_KEY = "token";

export function getToken(): string | null {
  try {
    const t = window.localStorage.getItem(TOKEN_KEY);
    return t && t !== "undefined" ? t : null;
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable */
  }
}

// The router registers here so a 401 raised outside React can still send the user to sign in.
let onUnauthorized: () => void = () => {
  setToken(null);
  window.location.assign("/");
};

export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

export type Query = Record<string, string | number | boolean | null | undefined>;

type Options = {
  method?: string;
  body?: unknown;
  query?: Query;
  /** Send this bearer token instead of the session's (e.g. an app's API key for the public API). */
  auth?: string;
};

/** Call the API with the session token. Throws ApiError; a 401 also signs the user out. */
export async function request<T>(path: string, opts: Options = {}): Promise<T> {
  return (await send<T>(path, opts)).data;
}

/**
 * A list request that also reads X-Total-Count. `total` is null when the response has no count (the
 * caller passed with_count=false while paging); callers keep the total they already had.
 */
export async function requestPage<T>(path: string, opts: Options = {}): Promise<{ rows: T[]; total: number | null }> {
  const { data, headers } = await send<T[]>(path, opts);
  const header = headers.get("X-Total-Count");
  const total = header === null ? null : Number(header);
  return { rows: data, total: Number.isFinite(total) ? total : null };
}

async function send<T>(path: string, opts: Options): Promise<{ data: T; headers: Headers }> {
  const qs = opts.query
    ? new URLSearchParams(
        Object.entries(opts.query)
          .filter(([, v]) => v !== null && v !== undefined)
          .map(([k, v]) => [k, String(v)]),
      ).toString()
    : "";
  const headers: Record<string, string> = {};
  const session = opts.auth === undefined ? getToken() : null;
  const token = opts.auth ?? session;
  if (token) headers.Authorization = `Bearer ${token}`;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`${API_BASE}${path}${qs ? `?${qs}` : ""}`, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const err = toApiError(res.status, body, res.statusText);
    // Only a rejected session signs out; a rejected app API key is just an error.
    if (res.status === 401 && session) onUnauthorized();
    throw err;
  }
  if (res.status === 204) return { data: null as T, headers: res.headers };
  return { data: (await res.json()) as T, headers: res.headers };
}
