import { expect, request, test, type APIRequestContext } from "@playwright/test";
import fs from "node:fs";
import { ADMIN, apiAs, BASE_URL, createApp, createTemplate, PHOTO, RUN, signIn, signInAdmin } from "./helpers";

test.describe.configure({ mode: "serial" });

const appName = `Android ${RUN}`;
const appSlug = `android-${RUN}`;
const first = { slug: `app-first-${RUN}`, title: `First ${RUN}` };
const second = { slug: `app-second-${RUN}`, title: `Second ${RUN}` };
let appId = "";
let appKey = "";
let admin: APIRequestContext;

test.beforeAll(async ({ browser }) => {
  const page = await browser.newPage();
  await signInAdmin(page);
  await page.close();
  admin = await apiAs(ADMIN.email, ADMIN.password);
  appId = await createApp(admin, appSlug, appName);
  const a = await createTemplate(admin, appId, first);
  const b = await createTemplate(admin, appId, second);
  // Show the second one first.
  const r = await admin.put(`/v1/apps/${appId}/manage/templates/order`, { data: { template_ids: [b, a] } });
  expect(r.status(), await r.text()).toBe(204);
});

test.afterAll(async () => {
  await admin?.dispose();
});

test("admin creates an app key, shown once with Android curl examples", async ({ page }) => {
  await signIn(page, ADMIN.email, ADMIN.password);
  await page.goto("/admin/apps");
  await page.getByTestId("admin-apps-table").locator(`tr[data-slug="${appSlug}"]`).click();
  await page.getByRole("button", { name: "New key" }).click();
  await page.getByRole("dialog").getByLabel("Name").fill("e2e");
  await page.getByRole("button", { name: "Create key" }).click();
  appKey = (await page.getByTestId("new-app-key").textContent())!.trim();
  expect(appKey).toMatch(/^cak_/);
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("X-Device-Id: <install id>");
  await expect(dialog).toContainText("/v1/app/templates");
  await expect(dialog).toContainText("/v1/app/generations/<job id>");
  await page.getByRole("button", { name: "Done" }).click();
});

test("the app key lists the catalog in order, runs a template and downloads the result", async ({ page }) => {
  const app = await request.newContext({
    baseURL: BASE_URL,
    extraHTTPHeaders: { "X-App-Key": appKey, "X-Device-Id": `e2e-device-${RUN}` },
  });
  const catalog = await (await app.get("/v1/app/templates")).json();
  expect(catalog.app.slug).toBe(appSlug);
  expect(catalog.templates.map((t: { slug: string }) => t.slug)).toEqual([second.slug, first.slug]);
  expect(JSON.stringify(catalog)).not.toContain("poster"); // no prompt in the catalog

  const run = await app.post(`/v1/app/templates/${first.slug}/generations`, {
    multipart: {
      photo: { name: "photo.png", mimeType: "image/png", buffer: fs.readFileSync(PHOTO) },
      variables: JSON.stringify({ style: "neon" }),
    },
  });
  expect(run.status(), await run.text()).toBe(202);
  const job = await run.json();
  let done = job;
  await expect
    .poll(
      async () => {
        done = await (await app.get(`/v1/app/generations/${job.id}`)).json();
        return done.status;
      },
      { timeout: 30_000 },
    )
    .toBe("succeeded");
  const asset = await app.get(done.assets[0].url);
  expect(asset.status()).toBe(200);
  expect(asset.headers()["content-type"]).toMatch(/^image\//);
  await app.dispose();

  // In the console, the app's jobs (source: Android app) show which device ran it.
  await signIn(page, ADMIN.email, ADMIN.password);
  await page.goto(`/apps/${appId}/jobs`);
  await page.getByRole("combobox", { name: "Source filter" }).click();
  await page.getByRole("option", { name: "Android app" }).click();
  const row = page.getByTestId("job-list").locator(`tr[data-job="${job.id}"]`);
  await expect(row).toContainText(`App: ${appName} (device e2e-device`);
  await row.click();
  await expect(page.getByTestId("job-detail")).toContainText(`(device e2e-device-${RUN})`);
  await expect(page.getByTestId("job-app-link")).toHaveText(appName);
});

test("a disabled app gets 403 app_disabled", async ({ page }) => {
  await signIn(page, ADMIN.email, ADMIN.password);
  await page.goto(`/admin/apps/${appId}`);
  await page.locator("label", { hasText: /^Disabled$/ }).click();
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByTestId("app-status")).toHaveText("disabled");
  const app = await request.newContext({ baseURL: BASE_URL, extraHTTPHeaders: { "X-App-Key": appKey } });
  const r = await app.get("/v1/app/templates");
  expect(r.status()).toBe(403);
  expect((await r.json()).error.code).toBe("app_disabled");
  await app.dispose();
});
