import type { components } from "./schema";

type S = components["schemas"];
export type Me = S["UserResponse"];
export type SetupState = S["SetupState"];
export type SetupResponse = S["SetupResponse"];
export type App = S["AppResponse"];
export type AdminUser = S["AdminUserResponse"];
export type AdminApp = S["AdminAppResponse"];
export type Summary = S["SummaryResponse"];
export type Subscription = S["SubscriptionResponse"];
export type ScheduledTransaction = S["ScheduledTransactionResponse"];
export type SubscriptionTransaction = S["SubscriptionTransactionResponse"];
export type RazorpaySubscription = S["RazorpaySubscriptionResponse"];
export type RazorpayTransaction = S["RazorpayTransactionResponse"];

/** GET /api/v1/{app}/phonepay/{phone}/status (not described in the OpenAPI schema). */
export type PhoneStatus = {
  state: string;
  subscription_id?: string | null;
  subscription_start_date?: string | null;
  subscription_validity_end_date?: string | null;
  subscription_frequency?: string | null;
  next_payment_date?: string | null;
  last_payment_status?: string | null;
  number_of_successful_payments?: number | null;
  payment_amount?: number | null;
  trail_amount?: number | null;
  trail_status?: string | null;
};
