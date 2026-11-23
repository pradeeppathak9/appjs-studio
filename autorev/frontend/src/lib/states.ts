// One color per subscription / payment state, shared by every table, badge and chart.
const COLORS: Record<string, string> = {
  ACTIVE: "green",
  COMPLETED: "green",
  SUCCESS: "green",
  INITIATED: "blue",
  ACTIVATION_IN_PROGRESS: "blue",
  INTEROP_IN_PROGRESS: "blue",
  AUTHORIZATION_PENDING: "blue",
  PENDING: "blue",
  SCHEDULED: "blue",
  NOTIFIED: "blue",
  IN_PROGRESS: "orange",
  NOTIFICATION_IN_PROGRESS: "orange",
  PAUSED: "yellow",
  HALTED: "orange",
  PAUSE_IN_PROGRESS: "yellow",
  FAILED: "red",
  REVOKED: "gray",
  REVOKE_IN_PROGRESS: "gray",
  CANCELLED: "gray",
  CANCEL_IN_PROGRESS: "gray",
  NOT_FOUND: "gray",
};

export function stateColor(state: string | null | undefined): string {
  return (state && COLORS[state]) || "gray";
}

/** The filter pills on each list, in display order ("" is All). */
export const PHONEPE_SUBSCRIPTION_STATES = [
  "",
  "INITIATED",
  "ACTIVATION_IN_PROGRESS",
  "INTEROP_IN_PROGRESS",
  "ACTIVE",
  "PAUSED",
  "PAUSE_IN_PROGRESS",
  "CANCELLED",
  "CANCEL_IN_PROGRESS",
  "REVOKE_IN_PROGRESS",
  "REVOKED",
  "FAILED",
];
export const PHONEPE_SCHEDULED_STATES = ["", "SCHEDULED", "IN_PROGRESS", "COMPLETED", "FAILED", "CANCELLED", "REVOKED"];
export const RAZORPAY_SUBSCRIPTION_STATES = ["", "INITIATED", "AUTHORIZATION_PENDING", "ACTIVE", "HALTED", "CANCELLED", "FAILED"];
export const RAZORPAY_PAYMENT_STATES = ["", "INITIATED", "NOTIFIED", "SUCCESS", "FAILED", "CANCELLED"];
