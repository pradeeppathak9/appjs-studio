/** Only same-site paths, so `?next=` can't send the user elsewhere. */
export function safeNext(next: string | null): string | null {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/login") ? next : null;
}
