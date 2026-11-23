import { describe, expect, it } from "vitest";
import { appTabsFor, canEdit, isAdmin } from "./roles";

describe("roles", () => {
  it("maps each app role to its tabs", () => {
    const labels = (r: Parameters<typeof appTabsFor>[0]) => appTabsFor(r).map((t) => t.label);
    expect(labels("tester")).toEqual(["Templates", "Test", "Jobs", "Integration guide"]);
    expect(labels("editor")).toEqual(["Templates", "Test", "Free prompt", "Jobs", "Android preview", "Integration guide"]);
    expect(labels("admin")).toEqual(labels("editor"));
  });

  it("adds Settings only for the global admin", () => {
    const labels = (r: Parameters<typeof appTabsFor>[0], admin: boolean) => appTabsFor(r, admin).map((t) => t.label);
    expect(labels("admin", true)).toEqual([
      "Templates",
      "Test",
      "Free prompt",
      "Jobs",
      "Android preview",
      "Integration guide",
      "Users",
      "Settings",
    ]);
    expect(labels("editor", false)).not.toContain("Settings");
    expect(labels("editor", false)).not.toContain("Users");
    expect(labels("admin", false)).not.toContain("Settings");
  });

  it("lets editors and admins edit, not testers", () => {
    expect(canEdit("admin")).toBe(true);
    expect(canEdit("editor")).toBe(true);
    expect(canEdit("tester")).toBe(false);
    expect(canEdit(undefined)).toBe(false);
  });

  it("knows the global admin", () => {
    expect(isAdmin({ role: "admin" })).toBe(true);
    expect(isAdmin({ role: "user" })).toBe(false);
    expect(isAdmin(undefined)).toBe(false);
  });
});
