// Dev helper: screenshots of the main pages in light and dark. Not part of the build or tests.
//   node scripts/screenshots.mjs <out-dir> [prefix]   (needs the dev stack and E2E_ADMIN_* env)
import { chromium, request } from "@playwright/test";

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:5173";
const EMAIL = process.env.E2E_ADMIN_EMAIL ?? "admin@example.com";
const PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "admin-password-123";
const OUT = process.argv[2] ?? ".";
const PREFIX = process.argv[3] ?? "after";
const only = process.env.ONLY?.split(",");

const api = await request.newContext({ baseURL: BASE, extraHTTPHeaders: { Origin: BASE } });
await api.post("/v1/auth/login", { data: { email: EMAIL, password: PASSWORD } });
const apps = await (await api.get("/v1/apps")).json();
const app = apps.find((a) => a.slug === "pixel-fun") ?? apps[0];
const templates = await (await api.get(`/v1/apps/${app.id}/manage/templates`)).json();
const jobs = (await (await api.get(`/v1/apps/${app.id}/generations?limit=5`)).json()).items;
const tpl = templates.sort((a, b) => a.position - b.position)[0];
const job = jobs.find((j) => j.status === "succeeded" && j.template) ?? jobs[0];

const pages = {
  home: "/",
  templates: `/apps/${app.id}`,
  test: `/apps/${app.id}/test?t=${tpl?.slug ?? ""}${job ? `&job=${job.id}` : ""}`,
  jobs: `/apps/${app.id}/jobs`,
  admin: `/admin/apps/${app.id}`,
  users: "/admin/users",
  editor: `/apps/${app.id}/templates/${tpl?.id}`,
};

const browser = await chromium.launch();
async function shot(name, path, scheme, viewport, signedIn = true) {
  const ctx = await browser.newContext({ viewport, colorScheme: scheme });
  await ctx.addInitScript((s) => window.localStorage.setItem("mantine-color-scheme-value", s), scheme);
  const page = await ctx.newPage();
  if (signedIn) {
    await page.goto(`${BASE}/login`);
    await page.getByLabel("Email").fill(EMAIL);
    await page.getByRole("textbox", { name: "Password", exact: true }).fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.waitForURL((u) => !u.pathname.startsWith("/login"));
  }
  await page.goto(`${BASE}${path}`);
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${OUT}/${PREFIX}-${name}.png` });
  await ctx.close();
}

const desktop = { width: 1440, height: 900 };
const mobile = { width: 390, height: 844 };
for (const [name, path] of Object.entries(pages)) {
  if (only && !only.includes(name)) continue;
  for (const scheme of ["light", "dark"]) await shot(`${name}-${scheme}`, path, scheme, desktop);
}
if (!only || only.includes("mobile")) {
  await shot("login-mobile", "/login", "light", mobile, false);
  await shot("templates-mobile-dark", pages.templates, "dark", mobile);
}
await browser.close();
await api.dispose();
console.log("done", Object.keys(pages).join(","));
