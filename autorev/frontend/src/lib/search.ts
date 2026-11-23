/** A 10-digit number searches by phone; anything else by subscription id. */
export function searchParams(q: string): { phone_number: string | null; subscription_id: string | null } {
  if (!q) return { phone_number: null, subscription_id: null };
  return /^\d{10}$/.test(q) ? { phone_number: q, subscription_id: null } : { phone_number: null, subscription_id: q };
}
