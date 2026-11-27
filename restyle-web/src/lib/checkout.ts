/** Buying a plan with Razorpay (APPS_API.md, "Buying a plan"): Studio starts the checkout through
 * autorev, Razorpay Checkout collects the mandate and first payment, then the order is polled until
 * Studio has started the subscription. No secrets here: the key id Razorpay Checkout needs is public. */
import { api, ApiError, type Account, type CheckoutBody, type PaymentOrder, type RazorpayCheckout } from "./api";

const RAZORPAY_JS = "https://checkout.razorpay.com/v1/checkout.js";

type RazorpayInstance = { open: () => void; on: (event: string, fn: (r: unknown) => void) => void };
type RazorpayCtor = new (options: Record<string, unknown>) => RazorpayInstance;
declare global {
  interface Window {
    Razorpay?: RazorpayCtor;
  }
}

let loading: Promise<RazorpayCtor> | null = null;

/** Razorpay's Checkout script, loaded once, on first use. */
export function loadRazorpay(): Promise<RazorpayCtor> {
  if (window.Razorpay) return Promise.resolve(window.Razorpay);
  loading ??= new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = RAZORPAY_JS;
    s.async = true;
    s.onload = () => (window.Razorpay ? resolve(window.Razorpay) : reject(new Error("no Razorpay")));
    s.onerror = () => {
      loading = null;
      reject(new Error("Can't load the payment page. Check your connection and try again."));
    };
    document.head.appendChild(s);
  });
  return loading;
}

export type CheckoutOutcome = "authorised" | "dismissed" | "failed";

/** Open Razorpay Checkout for a recurring order. Resolves when the payer finishes or closes it. */
export async function openRazorpay(r: RazorpayCheckout, description: string): Promise<CheckoutOutcome> {
  const Razorpay = await loadRazorpay();
  return new Promise((resolve) => {
    const rzp = new Razorpay({
      key: r.key_id,
      order_id: r.order_id,
      customer_id: r.customer_id,
      recurring: "1",
      amount: r.amount,
      currency: r.currency,
      // The business the payment goes to (as on the Razorpay account); the app is in the description.
      name: "APPJS Technologies",
      description,
      prefill: { name: r.name, email: r.email, contact: r.phone, method: r.method },
      theme: { color: "#4F46E5" },
      handler: () => resolve("authorised"),
      modal: { ondismiss: () => resolve("dismissed"), confirm_close: true },
    });
    rzp.on("payment.failed", () => resolve("failed"));
    rzp.open();
  });
}

/** Poll an order until it leaves `pending`, for up to `timeoutMs`; returns the last state seen. */
export async function waitForOrder(id: string, timeoutMs = 60_000, everyMs = 2_500): Promise<PaymentOrder> {
  const until = Date.now() + timeoutMs;
  let order = await api.order(id);
  while (order.status === "pending" && Date.now() < until) {
    await new Promise((r) => setTimeout(r, everyMs));
    order = await api.order(id);
  }
  return order;
}

/** What the gateway needs that the account doesn't have: an email (phone sign-in), a mobile (Google). */
export function missingDetails(me: Account | undefined): { email: boolean; phone: boolean } {
  return { email: !me?.email, phone: !me?.phone };
}

const SAVED = "restyle.payer";

/** The email / mobile typed for an earlier checkout on this browser, to fill the form in again. */
export function savedPayer(): { email: string; phone: string } {
  try {
    return { email: "", phone: "", ...JSON.parse(localStorage.getItem(SAVED) ?? "{}") };
  } catch {
    return { email: "", phone: "" };
  }
}

export function savePayer(v: { email: string; phone: string }) {
  try {
    localStorage.setItem(SAVED, JSON.stringify(v));
  } catch {
    /* private mode */
  }
}

export const validEmail = (v: string) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v.trim());
export const validMobile = (v: string) => /^[6-9]\d{9}$/.test(v.replace(/\D/g, "").replace(/^91(?=\d{10}$)/, ""));

export type CheckoutResult =
  | { kind: "active"; order: PaymentOrder }
  | { kind: "pending"; order: PaymentOrder }
  | { kind: "failed"; message: string }
  | { kind: "cancelled" };

/** The whole purchase: start it, open Razorpay, then follow the order. */
export async function buy(body: CheckoutBody, planName: string): Promise<CheckoutResult> {
  const order = await api.checkout(body);
  if (!order.razorpay) throw new ApiError(0, "no_checkout", "The payment couldn't be started. Try again.");
  const outcome = await openRazorpay(order.razorpay, `Restyle AI · ${planName} plan`);
  // Even a dismissed or failed checkout is checked once: the mandate may have gone through anyway.
  const latest = await waitForOrder(order.id, outcome === "authorised" ? 60_000 : 0);
  if (latest.status === "active") return { kind: "active", order: latest };
  if (latest.status === "failed") return { kind: "failed", message: latest.error ?? "The payment didn't go through." };
  if (outcome === "authorised") return { kind: "pending", order: latest };
  return outcome === "failed"
    ? { kind: "failed", message: "The payment didn't go through. Nothing was charged." }
    : { kind: "cancelled" };
}
