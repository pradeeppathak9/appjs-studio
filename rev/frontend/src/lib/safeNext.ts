/** A same-origin path to return to after sign-in, or the default. Rejects "//evil.com" and absolute URLs. */
export function safeNext(next: string | null, fallback = "/dashboard"): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return fallback;
  if (next === "/") return fallback;
  return next;
}
