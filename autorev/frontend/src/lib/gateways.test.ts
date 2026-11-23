import { describe, expect, test } from "vitest";
import type { App } from "../api/types";
import { appLanding, appTabsFor, gatewaysOf } from "./gateways";

const base = {
  id: "a1",
  name: "A",
  api_key: "k",
  enabled: true,
  phonepe_enabled: false,
  razorpay_enabled: false,
  phonepe_environment: "UAT",
  razorpay_environment: "TEST",
  phonepe_client_id: null,
  razorpay_key_id: null,
} as unknown as App;

describe("app sidebar", () => {
  test("PhonePe only", () => {
    const app = { ...base, phonepe_enabled: true };
    expect(appTabsFor(app).map((t) => t.path)).toEqual(["", "subscriptions", "transactions", "integration-guide", "settings"]);
    expect(appLanding(app)).toBe("");
  });

  test("Razorpay only lands on its subscriptions", () => {
    const app = { ...base, razorpay_enabled: true };
    expect(appTabsFor(app).map((t) => t.path)).toEqual(["rz-subscriptions", "rz-payments", "integration-guide", "settings"]);
    expect(appLanding(app)).toBe("rz-subscriptions");
  });

  test("no gateway lands on settings", () => {
    expect(appLanding(base)).toBe("settings");
  });
});

describe("gatewaysOf", () => {
  test("live and connected flags", () => {
    const app = { ...base, phonepe_enabled: true, phonepe_environment: "PROD", phonepe_client_id: "x", razorpay_enabled: true };
    expect(gatewaysOf(app)).toEqual([
      { gateway: "phonepe", env: "PROD", live: true, connected: true },
      { gateway: "razorpay", env: "TEST", live: false, connected: false },
    ]);
  });
});
