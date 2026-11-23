import { ApiError } from "../api/client";

/**
 * Map a 422's `details[].field` onto form field paths. `resolve` can rename a server path
 * (e.g. `variables.mood` -> `variables.2.name`); it returns null to leave the error unmapped.
 * Returns the mapped errors and the messages that matched no field (to show in an alert).
 */
export function fieldErrors(
  e: unknown,
  known: (path: string) => boolean,
  resolve: (field: string) => string | null = (f) => f,
): { errors: Record<string, string>; rest: string[] } {
  const errors: Record<string, string> = {};
  const rest: string[] = [];
  if (!(e instanceof ApiError)) return { errors, rest };
  const details = e.details.length ? e.details : e.field ? [{ field: e.field, message: e.message }] : [];
  for (const d of details) {
    const msg = d.message ?? e.message;
    const path = d.field ? resolve(d.field) : null;
    if (path && known(path)) errors[path] = errors[path] ? `${errors[path]}; ${msg}` : msg;
    else rest.push(d.field ? `${d.field}: ${msg}` : msg);
  }
  return { errors, rest };
}
