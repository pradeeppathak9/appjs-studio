import { describe, expect, it } from "vitest";
import type { TemplateVersion } from "../api/types";
import { diffVersions } from "./diff";

const v1 = {
  version: 1, title: "T", description: "", media_type: "image", provider: "fake", model: "m", allowed_models: [],
  prompt: "p", negative_prompt: null, params: { aspect_ratio: "auto", n: 1 }, inputs: [], variables: [],
  reference_uploads: [], cover_upload: null, note: null, created_by: { id: "u", name: "U" }, created_at: "",
} as TemplateVersion;

describe("diffVersions", () => {
  it("lists only the fields that changed, including the cover", () => {
    const v2 = { ...v1, version: 2, prompt: "q", cover_upload: "abc" };
    expect(diffVersions(v1, v2).map((c) => c.field)).toEqual(["prompt", "cover_upload"]);
  });
});
