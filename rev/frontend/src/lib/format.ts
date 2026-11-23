// Amounts are in paise; dates arrive either as epoch milliseconds (payment dates) or ISO timestamps
// (created_at). Everything is shown in Indian formatting.

/** ₹1,234 — whole rupees, for stat cards. */
export function rupees(paise: number | null | undefined): string {
  return `₹${((paise || 0) / 100).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

/** ₹1,234.50 — full precision, for tables and tooltips. */
export function rupeesExact(paise: number | null | undefined): string {
  return `₹${((paise || 0) / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function num(n: number | null | undefined): string {
  return (n || 0).toLocaleString("en-IN");
}

/** 05 Nov 2026, from epoch ms or an ISO string. */
export function fmtDate(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "" || v === 0) return "—";
  return new Date(v).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

/** 05 Nov 2026, 09:30 pm */
export function fmtDateTime(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  return new Date(v).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** ACTIVATION_IN_PROGRESS -> "Activation in progress" */
export function humanize(state: string): string {
  return state.charAt(0) + state.slice(1).toLowerCase().replace(/_/g, " ");
}
