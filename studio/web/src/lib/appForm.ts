import type { AppOut } from "../api/types";

export type AppFormValues = {
  slug: string;
  name: string;
  description: string;
  platform: string;
  status: "active" | "disabled";
  daily_job_limit: number | string;
  device_hourly_limit: number | string;
  // end-user sign-in
  auth_google_enabled: boolean;
  auth_phone_enabled: boolean;
  /** one OAuth Web client id per line */
  google_client_ids: string;
  phone_provider: "msg91" | "firebase";
  msg91_template_id: string;
  msg91_otp_var: string;
  /** write-only: blank keeps the saved key, text replaces it */
  msg91_auth_key: string;
  firebase_project_id: string;
  signup_credits: number | string;
  require_login: boolean;
  // payments: the gateway, and the autorev app that runs it (gateway keys and mode live in autorev)
  payment_provider: "none" | "razorpay" | "phonepe";
  autorev_app_id: string;
  /** write-only: blank keeps the saved value, text replaces it */
  autorev_api_key: string;
  /** write-only: blank keeps the saved value, text replaces it */
  autorev_webhook_secret: string;
};

export const PLATFORMS = ["android", "ios", "web", "other"];

export const EMPTY_APP: AppFormValues = {
  slug: "",
  name: "",
  description: "",
  platform: "android",
  status: "active",
  daily_job_limit: "",
  device_hourly_limit: "",
  auth_google_enabled: false,
  auth_phone_enabled: false,
  google_client_ids: "",
  phone_provider: "msg91",
  msg91_template_id: "",
  msg91_otp_var: "",
  msg91_auth_key: "",
  firebase_project_id: "",
  signup_credits: 0,
  require_login: false,
  payment_provider: "none",
  autorev_app_id: "",
  autorev_api_key: "",
  autorev_webhook_secret: "",
};

export function appValues(a: AppOut): AppFormValues {
  return {
    slug: a.slug,
    name: a.name,
    description: a.description,
    platform: a.platform,
    status: a.status,
    daily_job_limit: a.daily_job_limit ?? "",
    device_hourly_limit: a.device_hourly_limit ?? "",
    auth_google_enabled: a.auth_google_enabled,
    auth_phone_enabled: a.auth_phone_enabled,
    google_client_ids: (a.google_client_ids ?? []).join("\n"),
    phone_provider: a.phone_provider,
    msg91_template_id: a.msg91_template_id ?? "",
    msg91_otp_var: a.msg91_otp_var ?? "",
    msg91_auth_key: "",
    firebase_project_id: a.firebase_project_id ?? "",
    signup_credits: a.signup_credits,
    require_login: a.require_login,
    payment_provider: a.payment_provider,
    autorev_app_id: a.autorev_app_id ?? "",
    autorev_api_key: "",
    autorev_webhook_secret: "",
  };
}

/** Blank limit = no limit (null). */
export function appBody(v: AppFormValues) {
  const limit = (x: number | string) => (x === "" || x === null ? null : Number(x));
  return {
    name: v.name,
    description: v.description,
    platform: v.platform,
    status: v.status,
    daily_job_limit: limit(v.daily_job_limit),
    device_hourly_limit: limit(v.device_hourly_limit),
    ...signInBody(v),
    ...paymentBody(v),
  };
}

/** The general settings only (name, platform, status, limits): what the app page's Settings saves. */
export function generalBody(v: AppFormValues) {
  const limit = (x: number | string) => (x === "" || x === null ? null : Number(x));
  return {
    name: v.name,
    description: v.description,
    platform: v.platform,
    status: v.status,
    daily_job_limit: limit(v.daily_job_limit),
    device_hourly_limit: limit(v.device_hourly_limit),
  };
}

export function signInBody(v: AppFormValues) {
  const key = v.msg91_auth_key.trim();
  return {
    auth_google_enabled: v.auth_google_enabled,
    auth_phone_enabled: v.auth_phone_enabled,
    google_client_ids: v.google_client_ids
      .split(/[\s,]+/)
      .map((x) => x.trim())
      .filter(Boolean),
    phone_provider: v.phone_provider,
    msg91_template_id: v.msg91_template_id.trim() || null,
    msg91_otp_var: v.msg91_otp_var.trim() || null,
    firebase_project_id: v.firebase_project_id.trim() || null,
    // write-only: sent only when typed, so saving never clears the saved key
    ...(key ? { msg91_auth_key: key } : {}),
    signup_credits: Number(v.signup_credits) || 0,
    require_login: v.require_login,
  };
}

export function paymentBody(v: AppFormValues) {
  const key = v.autorev_api_key.trim();
  const secret = v.autorev_webhook_secret.trim();
  return {
    payment_provider: v.payment_provider,
    autorev_app_id: v.autorev_app_id.trim() || null,
    // write-only: sent only when typed, so saving never clears what is saved
    ...(key ? { autorev_api_key: key } : {}),
    ...(secret ? { autorev_webhook_secret: secret } : {}),
  };
}

/** Where autorev should send this Studio's payment events (paste into autorev → Settings → Webhooks). */
export function autorevWebhookUrl(origin: string): string {
  return `${origin.replace(/\/$/, "")}/api/v1/webhooks/autorev`;
}

/** Example calls for the app developers; the key and device id are placeholders they substitute. */
export function appCurl(origin: string, key: string, slug?: string): string {
  const h = `-H "X-App-Key: ${key}" -H "X-Device-Id: <install id>"`;
  const t = slug ?? "<template slug>";
  return [
    "# the app's template catalog (in display order)",
    `curl ${h} \\\n  ${origin}/v1/app/templates`,
    "",
    "# run a template: one file per input slot, variables as JSON",
    `curl ${h} \\\n  -F photo=@me.jpg -F 'variables={"mood":"rainy"}' \\\n  ${origin}/v1/app/templates/${t}/generations`,
    "",
    "# poll the job until status is succeeded or failed; assets[].url are downloadable with the same headers",
    `curl ${h} \\\n  ${origin}/v1/app/generations/<job id>`,
  ].join("\n");
}
