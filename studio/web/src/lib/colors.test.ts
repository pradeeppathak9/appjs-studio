import { describe, expect, it } from "vitest";
import { colorFor, initials } from "./colors";

describe("avatar helpers", () => {
  it("makes initials", () => {
    expect(initials("Pixel Fun")).toBe("PF");
    expect(initials("toon")).toBe("TO");
    expect(initials("dana.editor@example.com")).toBe("DE");
    expect(initials("  ")).toBe("?");
  });

  it("picks a stable color per key", () => {
    expect(colorFor("pixel-fun")).toBe(colorFor("pixel-fun"));
    expect(typeof colorFor("x")).toBe("string");
  });
});
