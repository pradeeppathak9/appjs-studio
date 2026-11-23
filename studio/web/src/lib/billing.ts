/** Money is stored in minor units (paise for INR). */
export function formatPrice(minor: number, currency: string): string {
  try {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency,
      minimumFractionDigits: minor % 100 === 0 ? 0 : 2,
      maximumFractionDigits: 2,
    }).format(minor / 100);
  } catch {
    return `${(minor / 100).toFixed(2)} ${currency}`;
  }
}

/** "199" or "199.50" (major units, as typed) -> 19900 / 19950. */
export function toMinor(major: number | string): number {
  const n = typeof major === "number" ? major : Number(String(major).replace(/,/g, ""));
  return Number.isFinite(n) ? Math.round(n * 100) : NaN;
}

export function signed(n: number): string {
  return n > 0 ? `+${n}` : String(n);
}

export const REASONS: Record<string, string> = {
  signup: "Sign-up bonus",
  subscription_grant: "Subscription",
  generation: "Generation",
  refund: "Refund (failed job)",
  admin_adjust: "Adjusted by admin",
};
