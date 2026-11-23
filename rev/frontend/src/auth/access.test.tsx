import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, test } from "vitest";
import { App } from "../App";
import { renderAt, stubApi } from "../test/render";

const ADMIN = { id: 1, email: "admin@autorev.app", full_name: "Admin", is_admin: true };
const USER = { id: 3, email: "user@example.com", full_name: "User", is_admin: false };
const APP = {
  id: "fee3024f5d6c4696a0ca6e9e341122dc",
  name: "Looksy",
  api_key: "k".repeat(64),
  enabled: true,
  phonepe_enabled: true,
  razorpay_enabled: false,
  phonepe_environment: "PROD",
  razorpay_environment: "TEST",
  phonepe_client_id: "cid",
  razorpay_key_id: null,
};

beforeEach(() => localStorage.clear());

describe("one sign-in page; admin area gated on the session", () => {
  test("/admin while signed out shows the sign-in page", async () => {
    stubApi({ "/api/auth/me": ADMIN });
    renderAt("/admin", <App />);
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  test("/admin as a non-admin goes to the app list", async () => {
    localStorage.setItem("token", "tok");
    stubApi({ "/api/auth/me": USER, "/api/apps": [] });
    renderAt("/admin", <App />);
    expect(await screen.findByText("Your apps")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /Redis/ })).not.toBeInTheDocument();
  });

  test("/admin as an admin renders the admin tabs", async () => {
    localStorage.setItem("token", "tok");
    stubApi({ "/api/auth/me": ADMIN, "/api/apps": [], "/api/admin": [] });
    renderAt("/admin/apps", <App />);
    expect(await screen.findByRole("tab", { name: /Redis/ })).toBeInTheDocument();
  });

  test("the sidebar links to Admin only for admins", async () => {
    localStorage.setItem("token", "tok");
    stubApi({ "/api/auth/me": USER, "/api/apps": [] });
    renderAt("/dashboard", <App />);
    await screen.findByText("Your apps");
    expect(screen.queryByRole("link", { name: "Admin" })).not.toBeInTheDocument();
  });

  test("an app's sidebar has the PhonePe pages, the guide and settings", async () => {
    localStorage.setItem("token", "tok");
    stubApi({ "/api/auth/me": USER, "/api/apps": [APP], [`/api/apps/${APP.id}`]: APP });
    renderAt(`/apps/${APP.id}/settings`, <App />);
    const guide = await screen.findByRole("link", { name: "Integration guide" });
    expect(guide).toHaveAttribute("href", `/apps/${APP.id}/integration-guide`);
    expect(screen.getByRole("link", { name: "Transactions" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Payments" })).not.toBeInTheDocument();
  });
});
