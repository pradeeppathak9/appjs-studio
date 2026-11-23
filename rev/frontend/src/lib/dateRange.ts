export type DateRange = { start: string; end: string };

/**
 * Local calendar date, not toISOString(): the backend reads these as IST dates, and UTC would roll an
 * IST user back a day before 05:30, dropping today's rows from a one-day window.
 */
export function isoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function daysAgo(n: number, now = new Date()): Date {
  const d = new Date(now);
  d.setDate(d.getDate() - n);
  return d;
}

/**
 * Empty bounds mean no date filter at all: the parameter is omitted from the request, which keeps
 * future-dated rows (scheduled payments) in range, as an end-of-today bound would not.
 */
export const ALL_TIME: DateRange = { start: "", end: "" };

/** Each dated preset includes today, so "Last 7 days" is today and the 6 before it. */
export const PRESETS: { value: string; label: string; days?: number }[] = [
  { value: "today", label: "Today", days: 0 },
  { value: "7d", label: "Last 7 days", days: 6 },
  { value: "30d", label: "Last 30 days", days: 29 },
  { value: "all", label: "All" },
];

export function presetRange(days: number, now = new Date()): DateRange {
  return { start: isoDate(daysAgo(days, now)), end: isoDate(now) };
}

export function rangeForPreset(value: string, now = new Date()): DateRange {
  const p = PRESETS.find((x) => x.value === value);
  return p?.days === undefined ? ALL_TIME : presetRange(p.days, now);
}

/** The preset a range matches, or null for a custom range. */
export function presetOf(range: DateRange, now = new Date()): string | null {
  const p = PRESETS.find((x) => {
    const r = rangeForPreset(x.value, now);
    return r.start === range.start && r.end === range.end;
  });
  return p?.value ?? null;
}

export function isInvalid(range: DateRange): boolean {
  return Boolean(range.start && range.end && range.start > range.end);
}

/** The query parameters for a range: empty bounds are left out. */
export function rangeParams(range: DateRange): { start_date: string | null; end_date: string | null } {
  return { start_date: range.start || null, end_date: range.end || null };
}

export function formatWindow({ start, end }: DateRange): string {
  if (!start && !end) return "All time";
  const fmt = (iso: string) =>
    new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  if (!start) return `up to ${fmt(end)}`;
  if (!end) return `from ${fmt(start)}`;
  return start === end ? fmt(start) : `${fmt(start)} – ${fmt(end)}`;
}
