import { describe, expect, it } from "vitest";
import { formatPrice, signed, toMinor } from "./billing";

describe("billing helpers", () => {
  it("formats minor units", () => {
    expect(formatPrice(19900, "INR")).toBe("₹199");
    expect(formatPrice(149950, "INR")).toBe("₹1,499.50");
    expect(formatPrice(500, "USD")).toContain("5");
  });
  it("parses typed prices to minor units", () => {
    expect(toMinor("199")).toBe(19900);
    expect(toMinor("1,499.5")).toBe(149950);
    expect(toMinor(0.1 + 0.2)).toBe(30);
    expect(toMinor("abc")).toBeNaN();
  });
  it("signs credit changes", () => {
    expect(signed(5)).toBe("+5");
    expect(signed(-2)).toBe("-2");
  });
});
