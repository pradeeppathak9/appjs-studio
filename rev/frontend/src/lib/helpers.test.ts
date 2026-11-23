import { describe, expect, test } from "vitest";
import { csvEscape, toCsv } from "./csv";
import { ALL_TIME, formatWindow, isInvalid, isoDate, presetOf, presetRange, rangeForPreset, rangeParams } from "./dateRange";
import { fmtDate, humanize, rupees, rupeesExact } from "./format";
import { searchParams } from "./search";
import { stateColor } from "./states";

const NOW = new Date(2026, 10, 5, 3, 0); // 05 Nov 2026, 03:00 local — before 05:30, where UTC would roll back a day

describe("date ranges", () => {
  test("isoDate uses the local calendar date, not UTC", () => {
    expect(isoDate(NOW)).toBe("2026-11-05");
  });

  test("presets include today", () => {
    expect(presetRange(0, NOW)).toEqual({ start: "2026-11-05", end: "2026-11-05" });
    expect(rangeForPreset("7d", NOW)).toEqual({ start: "2026-10-30", end: "2026-11-05" });
    expect(rangeForPreset("all", NOW)).toEqual(ALL_TIME);
  });

  test("a range maps back to its preset, or null when custom", () => {
    expect(presetOf(presetRange(29, NOW), NOW)).toBe("30d");
    expect(presetOf(ALL_TIME, NOW)).toBe("all");
    expect(presetOf({ start: "2026-01-01", end: "2026-01-31" }, NOW)).toBeNull();
  });

  test("All omits both bounds from the request", () => {
    expect(rangeParams(ALL_TIME)).toEqual({ start_date: null, end_date: null });
    expect(rangeParams({ start: "2026-11-01", end: "" })).toEqual({ start_date: "2026-11-01", end_date: null });
  });

  test("validity and labels", () => {
    expect(isInvalid({ start: "2026-11-06", end: "2026-11-05" })).toBe(true);
    expect(isInvalid({ start: "2026-11-06", end: "" })).toBe(false);
    expect(formatWindow(ALL_TIME)).toBe("All time");
    expect(formatWindow({ start: "2026-11-05", end: "2026-11-05" })).toBe("05 Nov 2026");
  });
});

describe("formatting", () => {
  test("amounts are paise", () => {
    expect(rupees(123456)).toBe("₹1,235");
    expect(rupeesExact(123450)).toBe("₹1,234.50");
    expect(rupeesExact(null)).toBe("₹0.00");
  });

  test("missing dates are a dash", () => {
    expect(fmtDate(null)).toBe("—");
    expect(fmtDate(0)).toBe("—");
  });

  test("states read as words and get a color", () => {
    expect(humanize("ACTIVATION_IN_PROGRESS")).toBe("Activation in progress");
    expect(stateColor("ACTIVE")).toBe("green");
    expect(stateColor("SOMETHING_NEW")).toBe("gray");
  });
});

test("search: 10 digits is a phone, anything else a subscription id", () => {
  expect(searchParams("9876543210")).toEqual({ phone_number: "9876543210", subscription_id: null });
  expect(searchParams("abc123")).toEqual({ phone_number: null, subscription_id: "abc123" });
  expect(searchParams("98765")).toEqual({ phone_number: null, subscription_id: "98765" });
  expect(searchParams("")).toEqual({ phone_number: null, subscription_id: null });
});

test("CSV escapes commas, quotes and newlines", () => {
  expect(csvEscape('a "b", c')).toBe('"a ""b"", c"');
  expect(csvEscape(null)).toBe("");
  expect(toCsv(["x", "y"], [[1, "a,b"]])).toBe('x,y\n1,"a,b"');
});
