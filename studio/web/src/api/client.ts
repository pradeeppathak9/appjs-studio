import createClient from "openapi-fetch";
import type { paths } from "./schema";
import type { Job } from "./types";

/** One entry of `error.details`. Most are {field, message}; a 409 conflict carries other keys. */
export type ErrorDetail = { field?: string; message?: string; [key: string]: unknown };

/** The API's uniform error body: {"error": {"code", "message", "field"?, "details"?}}. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly field?: string;
  readonly details: ErrorDetail[];

  constructor(status: number, code: string, message: string, field?: string, details?: ErrorDetail[]) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.field = field;
    this.details = details ?? [];
  }
}

/** Turn any error body (or a non-JSON one) into an ApiError. */
export function toApiError(status: number, body: unknown, statusText = ""): ApiError {
  const err = (body as { error?: Record<string, unknown> } | null)?.error;
  if (err && typeof err === "object" && typeof err.code === "string") {
    return new ApiError(
      status,
      err.code,
      typeof err.message === "string" ? err.message : err.code,
      typeof err.field === "string" ? err.field : undefined,
      Array.isArray(err.details) ? (err.details as ErrorDetail[]) : undefined,
    );
  }
  return new ApiError(status, `http_${status}`, statusText || `request failed (${status})`);
}

/** A short, human message for an error, used in toasts and alerts. */
export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.code === "forbidden") return "Your role can't do this.";
    if (e.code === "too_many_attempts") return `Too many attempts. ${e.message}`;
    return e.message;
  }
  if (e instanceof Error) return e.message;
  return String(e);
}

/** errorMessage plus the per-field details, for places without form fields to put them on. */
export function errorWithDetails(e: unknown): string {
  const base = errorMessage(e);
  if (!(e instanceof ApiError)) return base;
  const parts = e.details.filter((d) => d.message).map((d) => (d.field ? `${d.field}: ${d.message}` : d.message));
  return parts.length ? `${base}: ${parts.join("; ")}` : base;
}

// ---- auth redirects ------------------------------------------------------------------------------
// The router registers its navigate function here, so errors raised outside React can still move
// the user to /login or /change-password.

type Navigate = (to: string) => void;
let navigate: Navigate = (to) => window.location.assign(to);
let onSignedOut: () => void = () => {};

export function setAuthHandlers(handlers: { navigate: Navigate; onSignedOut: () => void }) {
  navigate = handlers.navigate;
  onSignedOut = handlers.onSignedOut;
}

const PUBLIC_PATHS = ["/login", "/setup"];

/** Called for every API error: 401 -> login (keeping the return path), 403 password change -> that page. */
export function handleAuthError(e: ApiError) {
  const here = window.location.pathname + window.location.search;
  if (e.status === 401 && e.code === "unauthenticated") {
    onSignedOut();
    if (!PUBLIC_PATHS.includes(window.location.pathname)) {
      navigate(`/login?next=${encodeURIComponent(here)}`);
    }
  } else if (e.status === 403 && e.code === "password_change_required") {
    if (window.location.pathname !== "/change-password") navigate("/change-password");
  }
}

// ---- typed client --------------------------------------------------------------------------------

export const api = createClient<paths>({ baseUrl: "", credentials: "same-origin" });

/**
 * Await an openapi-fetch call and return its data, or throw ApiError.
 * Usage: `const me = await unwrap(api.GET("/v1/auth/me"))`.
 */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok) {
    const e = toApiError(response.status, error, response.statusText);
    handleAuthError(e);
    throw e;
  }
  return data as T;
}

/**
 * Run a template: multipart/form-data with one file per input slot (named after the slot) plus
 * optional `variables` (JSON), `model`, `webhook_url` and (creators only) `version`.
 * The Content-Type header is left to the browser so it adds the multipart boundary.
 */
export type RunTemplateArgs = {
  appId: string;
  ref: string;
  files: Record<string, File>;
  variables?: Record<string, string>;
  model?: string | null;
  webhookUrl?: string | null;
  version?: number | null;
};

export function buildRunForm(args: RunTemplateArgs): FormData {
  const form = new FormData();
  for (const [slot, file] of Object.entries(args.files)) form.append(slot, file, file.name);
  if (args.variables && Object.keys(args.variables).length) {
    form.append("variables", JSON.stringify(args.variables));
  }
  if (args.model) form.append("model", args.model);
  if (args.webhookUrl) form.append("webhook_url", args.webhookUrl);
  if (args.version != null) form.append("version", String(args.version));
  return form;
}

export async function postForm<T>(url: string, form: FormData): Promise<T> {
  const response = await fetch(url, { method: "POST", body: form, credentials: "same-origin" });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const e = toApiError(response.status, body, response.statusText);
    handleAuthError(e);
    throw e;
  }
  return body as T;
}

export function runTemplate(args: RunTemplateArgs): Promise<Job> {
  return postForm<Job>(
    `/v1/apps/${args.appId}/templates/${encodeURIComponent(args.ref)}/generations`,
    buildRunForm(args),
  );
}
