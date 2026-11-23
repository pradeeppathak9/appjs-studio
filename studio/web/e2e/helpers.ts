import { expect, request, type APIRequestContext, type Page } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:5173";
export const ADMIN = {
  email: process.env.E2E_ADMIN_EMAIL ?? "admin@example.com",
  password: process.env.E2E_ADMIN_PASSWORD ?? "admin-password-123",
  name: "Admin",
};
export const SETUP_TOKEN = process.env.E2E_SETUP_TOKEN ?? "dev-setup-token";
export const PHOTO = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures", "photo.png");

/** A suffix that keeps names unique across runs on the same database. */
export const RUN = Date.now().toString(36);

/** An API client with its own cookie jar. Writes need an Origin matching the host (CSRF check). */
export async function apiAs(email: string, password: string): Promise<APIRequestContext> {
  const ctx = await request.newContext({ baseURL: BASE_URL, extraHTTPHeaders: { Origin: BASE_URL } });
  const r = await ctx.post("/v1/auth/login", { data: { email, password } });
  expect(r.status(), await r.text()).toBe(200);
  return ctx;
}

/** Make sure the admin exists: run setup through the UI on an empty database, else sign in. */
export async function signInAdmin(page: Page) {
  const anon = await request.newContext({ baseURL: BASE_URL });
  const { needed } = await (await anon.get("/v1/auth/setup")).json();
  await anon.dispose();
  if (needed) {
    await page.goto("/");
    await expect(page).toHaveURL(/\/setup$/);
    await page.getByLabel("Setup token").fill(SETUP_TOKEN);
    await page.getByLabel("Email").fill(ADMIN.email);
    await page.getByLabel("Name").fill(ADMIN.name);
    await page.getByRole("textbox", { name: "Password", exact: true }).fill(ADMIN.password);
    await page.getByRole("textbox", { name: "Repeat password", exact: true }).fill(ADMIN.password);
    await page.getByRole("button", { name: "Create admin" }).click();
  } else {
    await signIn(page, ADMIN.email, ADMIN.password);
  }
  await expect(page).toHaveURL(/\/$/);
}

export async function signIn(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("textbox", { name: "Password", exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

/** Sign in with a temporary password and set a permanent one on the forced change-password page. */
export async function firstSignIn(page: Page, email: string, temporary: string, password: string) {
  await signIn(page, email, temporary);
  await expect(page).toHaveURL(/\/change-password$/);
  await page.getByRole("textbox", { name: "Current password", exact: true }).fill(temporary);
  await page.getByRole("textbox", { name: "New password", exact: true }).fill(password);
  await page.getByRole("textbox", { name: "Repeat new password", exact: true }).fill(password);
  await page.getByRole("button", { name: "Set password" }).click();
}

/** Create a user through the admin API and set their password; returns the credentials. */
export async function createUser(admin: APIRequestContext, label: string) {
  const email = `${label}-${RUN}@example.com`;
  const r = await admin.post("/v1/admin/users", { data: { email, name: `${label} ${RUN}`, role: "user" } });
  expect(r.status(), await r.text()).toBe(201);
  const { user, temporary_password } = await r.json();
  const password = `${label}-password-${RUN}`;
  const me = await apiAs(email, temporary_password);
  const c = await me.post("/v1/auth/password", { data: { current_password: temporary_password, new_password: password } });
  expect(c.status(), await c.text()).toBe(204);
  await me.dispose();
  return { id: user.id as string, email, password, name: `${label} ${RUN}` };
}

/** Create an app through the admin API; returns its id. */
export async function createApp(admin: APIRequestContext, slug: string, name: string): Promise<string> {
  const r = await admin.post("/v1/admin/apps", { data: { slug, name, description: `${name} (e2e)`, platform: "android" } });
  expect(r.status(), await r.text()).toBe(201);
  return (await r.json()).id;
}

export async function addMember(admin: APIRequestContext, appId: string, userId: string, role: "editor" | "tester") {
  const r = await admin.put(`/v1/admin/apps/${appId}/members/${userId}`, { data: { role } });
  expect(r.status(), await r.text()).toBe(204);
}

/** Create a template with one photo slot and a {{style}} variable; optionally activate it. Returns its id. */
export async function createTemplate(
  api: APIRequestContext,
  appId: string,
  t: { slug: string; title: string },
  active = true,
): Promise<string> {
  const r = await api.post(`/v1/apps/${appId}/manage/templates`, {
    data: {
      slug: t.slug,
      title: t.title,
      description: `${t.title} (e2e)`,
      provider: "fake",
      model: "fake-image-1",
      prompt: "Make this photo look like a {{style}} poster.",
      inputs: [{ name: "photo", label: "Photo", required: true }],
      variables: [{ name: "style", label: "Style", default: "retro", choices: ["retro", "neon"] }],
    },
  });
  expect(r.status(), await r.text()).toBe(201);
  const id = (await r.json()).template.id;
  if (active) {
    const s = await api.post(`/v1/apps/${appId}/manage/templates/${id}/status`, { data: { status: "active" } });
    expect(s.status(), await s.text()).toBe(200);
  }
  return id;
}

/** Pick an option in a Mantine Select. */
export async function choose(page: Page, label: string | RegExp, option: string) {
  await page.getByRole("combobox", { name: label }).click();
  await page.getByRole("option", { name: option, exact: true }).click();
}

/** Open the user menu at the bottom of the navbar and log out. */
export async function logOut(page: Page) {
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Log out" }).click();
}

/** The navbar links of the current app (Templates, Test, Free prompt, Jobs, Android preview, Integration guide; admins: + Users, Settings). */
export function appNav(page: Page) {
  return page.getByRole("navigation", { name: "App sections" }).getByRole("link");
}

/** A template in the editor's list (grid card or table row). */
export function templateItem(page: Page, slug: string) {
  return page.locator(`[data-testid="template-item"][data-slug="${slug}"]`);
}

/** Open a template's ⋯ menu and pick an action. */
export async function templateAction(page: Page, slug: string, action: string | RegExp) {
  await page.getByRole("button", { name: `Actions for ${slug}` }).click();
  await page.getByRole("menuitem", { name: action }).click();
}
