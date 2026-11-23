/** AppJs Studio's API for this app (`/v1/app/*`, contract: studio/docs/APPS_API.md). Every call
 * carries the app key and this browser's device id; once signed in, also the session token. */
import { appKey } from "./config";
import { session } from "./session";

export class ApiError extends Error {
  status: number;
  code: string;
  details: Record<string, unknown>[];

  constructor(status: number, code: string, message: string, details: Record<string, unknown>[] = []) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }

  detail(name: string): number | undefined {
    const v = this.details.find((d) => name in d)?.[name];
    return typeof v === "number" ? v : undefined;
  }
}

// ---- shapes (only the fields this app reads) ------------------------------------------------------

export type AppConfig = {
  app: { slug: string; name: string };
  sign_in: { google: boolean; phone: boolean; google_client_id: string | null; phone_provider: string | null };
  require_login: boolean;
};
export type Template = {
  id: string;
  slug: string;
  title: string;
  description: string;
  media_type: "image" | "video";
  inputs: { name: string; label: string; required: boolean }[];
  cover_url: string | null;
  credit_cost: number;
  version: number;
};
export type Account = {
  id: string;
  name: string | null;
  email: string | null;
  phone: string | null;
  photo_url: string | null;
  sign_in: "phone" | "google";
  credits: number;
  subscription: { plan: { id: string; name: string }; status: string; current_period_end: string } | null;
};
export type SignedIn = { token: string; user: Account; is_new: boolean };
export type Plan = {
  id: string;
  slug: string;
  name: string;
  description: string;
  price_minor: number;
  currency: string;
  billing_period: "month" | "year";
  credits_per_month: number;
  badge: string | null;
};
export type Job = {
  id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  media_type: string;
  template: { slug: string; title: string } | null;
  inputs: { url: string; slot: string }[];
  assets: { url: string; mime_type: string; width: number | null; height: number | null }[];
  error: { code: string; message: string } | null;
  created_at: string;
  credits?: number | null;
};

// ---- transport --------------------------------------------------------------------------------------

function headers(extra?: HeadersInit): Headers {
  const h = new Headers(extra);
  h.set("X-App-Key", appKey());
  h.set("X-Device-Id", session.deviceId());
  h.set("Accept", "application/json");
  const token = session.token();
  if (token) h.set("Authorization", `Bearer ${token}`);
  return h;
}

export async function request(path: string, init: RequestInit = {}): Promise<Response> {
  if (!appKey()) throw new ApiError(0, "no_app_key", "This build has no app key.");
  let res: Response;
  try {
    res = await fetch(path, { ...init, headers: headers(init.headers) });
  } catch {
    throw new ApiError(0, "network", "Can't reach the server.");
  }
  if (!res.ok) {
    let body: { error?: { code?: string; message?: string; details?: Record<string, unknown>[] } } = {};
    try {
      body = await res.json();
    } catch {
      /* not JSON */
    }
    const err = new ApiError(res.status, body.error?.code ?? "http_" + res.status, body.error?.message ?? res.statusText, body.error?.details);
    // A session the server no longer accepts (signed out elsewhere, blocked, deleted): forget it.
    if (res.status === 401 && session.token()) session.clear();
    throw err;
  }
  return res;
}

async function getJson<T>(path: string): Promise<T> {
  return (await request(path)).json();
}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await request(path, {
    method: "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return res.status === 204 ? (undefined as T) : res.json();
}

// ---- endpoints ----------------------------------------------------------------------------------------

export const api = {
  config: () => getJson<AppConfig>("/v1/app"),
  sendOtp: (phone: string) =>
    postJson<{ challenge_id: string; phone: string; resend_after_s: number }>("/v1/app/auth/otp/send", { phone }),
  verifyOtp: (challenge_id: string, code: string) =>
    postJson<SignedIn>("/v1/app/auth/otp/verify", { challenge_id, code }),
  google: (id_token: string) => postJson<SignedIn>("/v1/app/auth/google", { id_token }),
  logout: () => postJson<void>("/v1/app/auth/logout"),
  me: () => getJson<Account>("/v1/app/me"),
  deleteMe: () => request("/v1/app/me", { method: "DELETE" }),
  templates: async () => (await getJson<{ templates: Template[] }>("/v1/app/templates")).templates,
  plans: () => getJson<Plan[]>("/v1/app/plans"),
  jobs: () => getJson<Job[]>("/v1/app/generations?limit=50"),
  job: (id: string) => getJson<Job>(`/v1/app/generations/${id}`),
  run: (slug: string, slot: string, photo: Blob) => {
    const form = new FormData();
    form.append(slot, photo, "photo.jpg");
    return request(`/v1/app/templates/${slug}/generations`, { method: "POST", body: form }).then(
      (r) => r.json() as Promise<Job>,
    );
  },
  /** Images behind the API (covers, results, inputs) need the same headers, so they're fetched. */
  blob: async (url: string) => (await request(url)).blob(),
};
