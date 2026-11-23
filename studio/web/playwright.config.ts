import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against a running stack with the fake provider enabled.
 *
 *   E2E_BASE_URL       where the console is served (default: the Vite dev server, http://localhost:5173;
 *                      http://localhost:8080 for the compose stack)
 *   E2E_SETUP_TOKEN    used when the database is empty (default: dev-setup-token)
 *   E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD
 *                      the admin created by setup, or an existing admin to sign in with when the
 *                      database is not empty (defaults: admin@example.com / admin-password-123)
 *
 * The specs create uniquely named users and templates, so they can run again on the same database.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
