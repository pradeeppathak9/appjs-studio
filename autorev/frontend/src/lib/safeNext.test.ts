import { expect, test } from "vitest";
import { safeNext } from "./safeNext";

test("only same-origin paths are followed after sign-in", () => {
  expect(safeNext("/apps/x/settings")).toBe("/apps/x/settings");
  expect(safeNext(null)).toBe("/dashboard");
  expect(safeNext("/")).toBe("/dashboard");
  expect(safeNext("//evil.com")).toBe("/dashboard");
  expect(safeNext("/\\evil.com")).toBe("/dashboard");
  expect(safeNext("https://evil.com")).toBe("/dashboard");
});
