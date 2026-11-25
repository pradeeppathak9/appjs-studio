import { ApiError } from "./api";

export function creditsLabel(n: number): string {
  return n === 1 ? "1 credit" : `${n} credits`;
}

/** 19900 INR → "₹199"; 19950 → "₹199.50". Indian digit grouping, like the Android app. */
export function formatPrice(minor: number, currency = "INR"): string {
  const symbol = { INR: "₹", USD: "$", EUR: "€" }[currency] ?? `${currency} `;
  const value = minor / 100;
  const digits = minor % 100 === 0 ? 0 : 2;
  return symbol + value.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: 2 });
}

export function greeting(now = new Date()): string {
  const h = now.getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

/** "+919876543210" → "+91 98765 43210" */
export function displayPhone(phone: string | null | undefined): string {
  if (!phone) return "";
  const m = /^\+91(\d{5})(\d{5})$/.exec(phone);
  return m ? `+91 ${m[1]} ${m[2]}` : phone;
}

/** The message a person sees for a failed call: same wording as the Android app. */
export function userMessage(e: unknown, signedIn = false): string {
  if (!(e instanceof ApiError)) return "Something went wrong. Try again.";
  if (e.code === "network") return "Can't reach the server. Check your connection and try again.";
  switch (e.code) {
    case "otp_invalid": {
      const left = e.detail("attempts_left");
      return "That code didn't work." + (left !== undefined ? ` ${left} ${left === 1 ? "try" : "tries"} left.` : "");
    }
    case "otp_expired":
      return "This code has expired. Tap Resend code.";
    case "rate_limited": {
      const wait = e.detail("retry_after_s");
      return wait ? `Too many tries. Wait ${wait} s and try again.` : "Too many tries. Try again later.";
    }
    case "insufficient_credits":
      return "You need more credits for this style.";
    case "content_policy":
      return "This photo can't be styled. Try a different one. Your credits were refunded.";
    case "account_blocked":
      return "This account is blocked. Contact support.";
    case "app_disabled":
      return "Restyle AI is under maintenance. Try again later.";
    case "payload_too_large":
      return "That photo is too large. Pick one under 10 MB.";
    case "no_app_key":
      return "This site isn't set up yet (no app key).";
  }
  if (e.code === "provider_unavailable" && e.status === 503) return "This style isn't available right now. Your credits weren't used.";
  if (e.status === 200) return `The image couldn't be made (${e.code}). Your credits were refunded.`;
  if (e.code === "unauthenticated") return signedIn ? "Your session ended. Sign in again." : "Sign in to continue.";
  return e.message ? e.message[0].toUpperCase() + e.message.slice(1) : "Something went wrong. Try again.";
}
