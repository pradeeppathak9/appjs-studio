import { describe, expect, it } from "vitest";
import type { Job } from "../api/types";
import { jobOrigin } from "./jobs";

describe("jobOrigin", () => {
  it("names the user, or the app and device", () => {
    expect(jobOrigin({ created_by: { id: "1", name: "Ann" }, app: null } as Job)).toBe("Ann");
    expect(
      jobOrigin({ created_by: null, app: { id: "a", slug: "s", name: "Android", device_id: "install-1234567890abc" } } as Job),
    ).toBe("App: Android (device install-1234…)");
    expect(jobOrigin({ created_by: null, app: { id: "a", slug: "s", name: "Android", device_id: null } } as Job)).toBe(
      "App: Android",
    );
  });
});
