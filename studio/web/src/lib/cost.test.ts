import { describe, expect, it } from "vitest";
import type { PriceList } from "../api/types";
import { formatUsd, runCost, suggestedCredits } from "./cost";

const prices: PriceList = {
  checked: "2026-11-26",
  credit_usd: 0.04,
  models: [
    { provider: "gemini", model: "lite", usd: 0.034, unit: "image", note: null },
    { provider: "gemini", model: "pro", usd: 0.134, unit: "image", note: null },
    { provider: "fal", model: "video", usd: 0.1, unit: "second", note: null },
  ],
};
const base = { media_type: "image" as const, provider: "gemini", allowed_models: [], n: 1, duration_seconds: null };

describe("template run cost", () => {
  it("prices one image and suggests credits", () => {
    expect(runCost(prices, { ...base, model: "lite" })).toEqual({ usd: 0.034, model: "lite", missing: [], suggested: 1 });
  });
  it("multiplies by n", () => {
    expect(runCost(prices, { ...base, model: "lite", n: 3 })?.suggested).toBe(3);
  });
  it("uses the most expensive allowed model and lists unpriced ones", () => {
    const c = runCost(prices, { ...base, model: "lite", allowed_models: ["pro", "mystery"] });
    expect(c).toMatchObject({ model: "pro", usd: 0.134, missing: ["mystery"], suggested: 4 });
  });
  it("matches on provider too", () => {
    expect(runCost(prices, { ...base, provider: "openai", model: "lite" })).toBeNull();
  });
  it("prices video per second only when a duration is set", () => {
    const v = { ...base, media_type: "video" as const, provider: "fal", model: "video" };
    expect(runCost(prices, v)).toBeNull();
    expect(runCost(prices, { ...v, duration_seconds: "5" })?.usd).toBeCloseTo(0.5);
  });
  it("rounds credits up, but not on float noise", () => {
    expect(suggestedCredits(0.08, 0.04)).toBe(2);
    expect(suggestedCredits(0.081, 0.04)).toBe(3);
    expect(suggestedCredits(0, 0.04)).toBe(0);
  });
  it("formats dollars", () => {
    expect(formatUsd(0.067)).toBe("$0.067");
    expect(formatUsd(0.04)).toBe("$0.04");
    expect(formatUsd(0.0038)).toBe("$0.0038");
  });
});
