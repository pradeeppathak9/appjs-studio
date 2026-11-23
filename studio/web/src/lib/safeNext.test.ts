import { describe, expect, it } from "vitest";
import { safeNext } from "./safeNext";

describe("safeNext", () => {
  it("only allows same-site paths", () => {
    expect(safeNext("/jobs/1?x=2")).toBe("/jobs/1?x=2");
    expect(safeNext("//evil.example")).toBeNull();
    expect(safeNext("https://evil.example")).toBeNull();
    expect(safeNext("/login?next=/x")).toBeNull();
    expect(safeNext(null)).toBeNull();
  });
});
