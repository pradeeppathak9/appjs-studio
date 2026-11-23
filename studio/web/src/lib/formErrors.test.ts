import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import { fieldErrors } from "./formErrors";
import { EMPTY_TEMPLATE, isEditorField, resolveField } from "./templateForm";

const e422 = (details: { field: string; message: string }[]) =>
  new ApiError(422, "validation_error", "the template has errors", undefined, details);

describe("422 details -> form fields", () => {
  it("maps known fields and keeps the rest", () => {
    const { errors, rest } = fieldErrors(
      e422([
        { field: "prompt", message: "required" },
        { field: "zzz", message: "odd" },
      ]),
      (p) => p === "prompt",
    );
    expect(errors).toEqual({ prompt: "required" });
    expect(rest).toEqual(["zzz: odd"]);
  });

  it("uses error.field when there are no details", () => {
    const e = new ApiError(422, "validation_error", "this model is not allowed", "model");
    expect(fieldErrors(e, () => true).errors).toEqual({ model: "this model is not allowed" });
  });

  it("maps the editor's server paths onto its form", () => {
    const values = { ...EMPTY_TEMPLATE, variables: [{ name: "x", label: "", default: "", max_length: 10, choices: [] }, { name: "mood", label: "", default: "", max_length: 10, choices: [] }] };
    const { errors } = fieldErrors(
      e422([
        { field: "params.n", message: "at most 4" },
        { field: "variables.mood", message: "declared but not used" },
        { field: "variables.mood.default", message: "must be one of the choices" },
        { field: "inputs.0.name", message: "bad name" },
      ]),
      isEditorField,
      (f) => resolveField(f, values),
    );
    expect(errors).toEqual({
      n: "at most 4",
      "variables.1.name": "declared but not used",
      "variables.1.default": "must be one of the choices",
      "inputs.0.name": "bad name",
    });
  });

  it("ignores errors that aren't ApiErrors", () => {
    expect(fieldErrors(new Error("x"), () => true)).toEqual({ errors: {}, rest: [] });
  });
});
