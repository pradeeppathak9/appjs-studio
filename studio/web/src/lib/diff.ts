import type { TemplateVersion } from "../api/types";

const FIELDS: (keyof TemplateVersion)[] = [
  "title",
  "description",
  "media_type",
  "provider",
  "model",
  "allowed_models",
  "prompt",
  "negative_prompt",
  "params",
  "inputs",
  "variables",
  "reference_uploads",
  "cover_upload",
];

export type FieldChange = { field: string; before: string; after: string };

function show(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  return typeof v === "string" ? v : JSON.stringify(v, null, 1).replace(/\n\s*/g, " ");
}

/** Fields that differ between two template versions (everything differs from "nothing"). */
export function diffVersions(prev: TemplateVersion | undefined, next: TemplateVersion): FieldChange[] {
  const out: FieldChange[] = [];
  for (const f of FIELDS) {
    const a = prev ? show(prev[f]) : "—";
    const b = show(next[f]);
    if (a !== b) out.push({ field: f, before: a, after: b });
  }
  return out;
}
