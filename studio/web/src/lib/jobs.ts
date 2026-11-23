import type { Job } from "../api/types";

/** Who started a job: a user's name, or "App: <name> (device …)" for jobs from an app key. */
export function jobOrigin(job: Job): string {
  if (job.created_by) return job.created_by.name;
  if (job.app) {
    const d = job.app.device_id;
    const device = d ? ` (device ${d.slice(0, 12)}${d.length > 12 ? "…" : ""})` : "";
    return `App: ${job.app.name}${device}`;
  }
  return "—";
}
