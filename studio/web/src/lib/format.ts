export function formatBytes(n: number | null | undefined): string {
  if (n == null) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function formatDate(s: string | null | undefined): string {
  return s ? new Date(s).toLocaleString() : "—";
}

/** "5s ago", "3m ago", "2h ago", "4d ago". */
export function age(s: string | null | undefined, now = Date.now()): string {
  if (!s) return "—";
  const sec = Math.max(0, Math.round((now - new Date(s).getTime()) / 1000));
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  return `${Math.floor(sec / 86400)}d ago`;
}

export function shortId(id: string): string {
  return id.slice(0, 8);
}
