import type { TemplateCreate, TemplateVersion } from "../api/types";

export type SlotForm = { name: string; label: string; required: boolean };
export type VarForm = { name: string; label: string; default: string; max_length: number; choices: string[] };

/** The editor's form values: the template version with `params` flattened. */
export type EditorValues = {
  slug: string;
  title: string;
  description: string;
  media_type: "image" | "video";
  provider: string;
  model: string;
  allowed_models: string[];
  prompt: string;
  negative_prompt: string;
  aspect_ratio: string;
  n: number;
  seed: number | string;
  duration_seconds: string | null;
  inputs: SlotForm[];
  variables: VarForm[];
  reference_uploads: string[];
  cover_upload: string | null;
  note: string;
  /** credits a signed-in app user pays per run (template pricing, not versioned) */
  credit_cost: number | string;
};

export const EMPTY_TEMPLATE: EditorValues = {
  slug: "",
  title: "",
  description: "",
  media_type: "image",
  provider: "",
  model: "",
  allowed_models: [],
  prompt: "",
  negative_prompt: "",
  aspect_ratio: "auto",
  n: 1,
  seed: "",
  duration_seconds: null,
  inputs: [{ name: "photo", label: "Your photo", required: true }],
  variables: [],
  reference_uploads: [],
  cover_upload: null,
  note: "",
  credit_cost: 1,
};

export function newVariable(name: string): VarForm {
  return { name, label: name, default: "", max_length: 100, choices: [] };
}

export function fromVersion(v: TemplateVersion, slug: string, creditCost: number = 1): EditorValues {
  return {
    slug,
    title: v.title,
    description: v.description,
    media_type: v.media_type === "video" ? "video" : "image",
    provider: v.provider,
    model: v.model,
    allowed_models: v.allowed_models,
    prompt: v.prompt,
    negative_prompt: v.negative_prompt ?? "",
    aspect_ratio: v.params.aspect_ratio ?? "auto",
    n: v.params.n ?? 1,
    seed: v.params.seed ?? "",
    duration_seconds: v.params.duration_seconds != null ? String(v.params.duration_seconds) : null,
    inputs: v.inputs.map((s) => ({ name: s.name, label: s.label ?? "", required: s.required !== false })),
    variables: v.variables.map((x) => ({
      name: x.name,
      label: x.label ?? "",
      default: x.default ?? "",
      max_length: x.max_length ?? 100,
      choices: x.choices ?? [],
    })),
    reference_uploads: v.reference_uploads,
    cover_upload: v.cover_upload ?? null,
    note: "",
    credit_cost: creditCost,
  };
}

export function toBody(v: EditorValues): Omit<TemplateCreate, "slug"> {
  return {
    title: v.title,
    description: v.description,
    media_type: v.media_type,
    provider: v.provider,
    model: v.model,
    allowed_models: v.allowed_models,
    prompt: v.prompt,
    negative_prompt: v.negative_prompt || null,
    params: {
      aspect_ratio: v.aspect_ratio,
      n: v.media_type === "video" ? 1 : v.n,
      seed: v.seed === "" ? null : Number(v.seed),
      duration_seconds: v.media_type === "video" && v.duration_seconds ? Number(v.duration_seconds) : null,
    },
    inputs: v.inputs.map((s) => ({ name: s.name, label: s.label || s.name, required: s.required })),
    variables: v.variables.map((x) => ({
      name: x.name,
      label: x.label || x.name,
      default: x.default,
      max_length: x.max_length,
      choices: x.choices.length ? x.choices : null,
    })),
    reference_uploads: v.reference_uploads,
    cover_upload: v.cover_upload,
    note: v.note || null,
    credit_cost: v.credit_cost === "" ? null : Number(v.credit_cost),
  };
}

/**
 * Map a server error field to the editor's form path:
 * `params.n` -> `n`, `variables.mood` -> `variables.2.name`, `variables.mood.default` -> `variables.2.default`.
 */
export function resolveField(field: string, v: EditorValues): string | null {
  if (field.startsWith("params.")) return field.slice("params.".length);
  const m = /^variables\.([^.]+)(?:\.(\w+))?$/.exec(field);
  if (m && !/^\d+$/.test(m[1])) {
    const i = v.variables.findIndex((x) => x.name === m[1]);
    return i < 0 ? "variables" : `variables.${i}.${m[2] ?? "name"}`;
  }
  return field;
}

export function isEditorField(path: string): boolean {
  return path in EMPTY_TEMPLATE || /^(inputs|variables)\.\d+\.\w+$/.test(path);
}
