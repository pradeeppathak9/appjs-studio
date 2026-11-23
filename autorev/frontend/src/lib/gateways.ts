import type { App } from "../api/types";

export type Gateway = "phonepe" | "razorpay";

export const GATEWAY_LABEL: Record<Gateway, string> = { phonepe: "PhonePe", razorpay: "Razorpay" };
export const GATEWAY_COLOR: Record<Gateway, string> = { phonepe: "violet", razorpay: "blue" };

/** The gateways an app has switched on, with their environment and whether credentials are set. */
export function gatewaysOf(app: App): { gateway: Gateway; env: string; live: boolean; connected: boolean }[] {
  const out = [];
  if (app.phonepe_enabled) {
    out.push({
      gateway: "phonepe" as const,
      env: app.phonepe_environment,
      live: app.phonepe_environment === "PROD",
      connected: !!app.phonepe_client_id,
    });
  }
  if (app.razorpay_enabled) {
    out.push({
      gateway: "razorpay" as const,
      env: app.razorpay_environment,
      live: app.razorpay_environment === "LIVE",
      connected: !!app.razorpay_key_id,
    });
  }
  return out;
}

export type AppTab = { path: string; label: string; group?: Gateway };

/** The app's sidebar: PhonePe and Razorpay sections when enabled, then the shared pages. */
export function appTabsFor(app: App): AppTab[] {
  const tabs: AppTab[] = [];
  if (app.phonepe_enabled) {
    tabs.push(
      { path: "", label: "Summary", group: "phonepe" },
      { path: "subscriptions", label: "Subscriptions", group: "phonepe" },
      { path: "transactions", label: "Transactions", group: "phonepe" },
    );
  }
  if (app.razorpay_enabled) {
    tabs.push(
      { path: "rz-subscriptions", label: "Subscriptions", group: "razorpay" },
      { path: "rz-payments", label: "Payments", group: "razorpay" },
    );
  }
  tabs.push({ path: "integration-guide", label: "Integration guide" }, { path: "settings", label: "Settings" });
  return tabs;
}

/** Where /apps/:id lands: the PhonePe summary, else Razorpay subscriptions, else settings. */
export function appLanding(app: App): string {
  if (app.phonepe_enabled) return "";
  if (app.razorpay_enabled) return "rz-subscriptions";
  return "settings";
}
