import { describe, expect, it } from "vitest";
import { templateCurl } from "./curl";

describe("templateCurl", () => {
  it("builds the app-scoped multipart call with a token placeholder", () => {
    const c = templateCurl({
      origin: "http://h",
      appId: "a1",
      ref: "cartoon",
      slots: [{ name: "photo", fileName: "me.png" }],
      variables: { mood: "it's rainy" },
      model: "m2",
    });
    expect(c).toContain('-H "Authorization: Bearer $CREATIVE_TOKEN"');
    expect(c).toContain("-F photo=@me.png");
    expect(c).toContain(`-F 'variables={"mood":"it'\\''s rainy"}'`);
    expect(c).toContain("-F model=m2");
    expect(c.endsWith("http://h/v1/apps/a1/templates/cartoon/generations")).toBe(true);
  });
});
