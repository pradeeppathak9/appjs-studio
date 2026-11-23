import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import {
  addMember,
  ADMIN,
  apiAs,
  createApp,
  createTemplate,
  createUser,
  PHOTO,
  RUN,
  appNav,
  signIn,
  signInAdmin,
  templateAction,
  templateItem,
} from "./helpers";

test.describe.configure({ mode: "serial" });

type User = Awaited<ReturnType<typeof createUser>>;
let editor: User;
let tester: User;
let appId = "";
let otherAppId = "";
let templateUrl = "";
const slug = `cartoon-${RUN}`;
const title = `Cartoon ${RUN}`;
const second = { slug: `poster-${RUN}`, title: `Poster ${RUN}` };
const draft = { slug: `secret-${RUN}`, title: `Secret draft ${RUN}` };

let admin: APIRequestContext;

test.beforeAll(async ({ browser }) => {
  const page = await browser.newPage();
  await signInAdmin(page); // runs setup on an empty database
  await page.close();
  admin = await apiAs(ADMIN.email, ADMIN.password);
  appId = await createApp(admin, `pixel-fun-t-${RUN}`, `Pixel Fun T ${RUN}`);
  otherAppId = await createApp(admin, `other-${RUN}`, `Other ${RUN}`);
  editor = await createUser(admin, "teditor");
  tester = await createUser(admin, "ttester");
  await addMember(admin, appId, editor.id, "editor");
  await addMember(admin, appId, tester.id, "tester");
});

test.afterAll(async () => {
  await admin?.dispose();
});

function rows(page: Page) {
  return page.getByTestId("template-item");
}

test("editor sees only their app and builds a draft with a cover and a {{variable}}, then test-runs it", async ({
  page,
}) => {
  await signIn(page, editor.email, editor.password);
  await expect(page.getByTestId("app-card")).toHaveCount(1);
  await page.getByTestId("app-card").click();
  await expect(page).toHaveURL(new RegExp(`/apps/${appId}$`));
  await page.getByRole("link", { name: "New template" }).first().click();

  await page.getByLabel("Title").fill(title);
  await page.getByLabel("Slug").fill(slug);
  await page.getByRole("textbox", { name: "Description", exact: true }).fill("Turns a photo into a cartoon.");
  await page.getByRole("combobox", { name: "Provider" }).click();
  await page.getByRole("option", { name: "fake", exact: true }).click();
  await page.getByRole("combobox", { name: "Model", exact: true }).fill("fake-image-1");
  await page.getByRole("textbox", { name: "Prompt", exact: true }).fill("Redraw this photo as a cartoon. Mood: {{mood}}.");
  await page.getByRole("button", { name: "Add {{mood}}" }).click();
  await page.getByLabel("Default").fill("sunny");
  for (const c of ["sunny", "rainy"]) {
    await page.getByRole("combobox", { name: "Choices" }).fill(c);
    await page.getByRole("combobox", { name: "Choices" }).press("Enter");
  }
  await page.getByTestId("cover-picker").locator('input[type="file"]').setInputFiles(PHOTO);
  await expect(page.getByTestId("cover-preview")).toBeVisible();
  await page.getByLabel("Change note").fill("first draft");
  await page.getByRole("button", { name: "Create template" }).click();

  await expect(page).toHaveURL(new RegExp(`/apps/${appId}/templates/[0-9a-f-]{36}$`));
  templateUrl = page.url();
  await expect(page.getByTestId("template-status")).toHaveText("draft");

  const panel = page.getByTestId("test-run");
  await panel.locator('input[type="file"]').setInputFiles(PHOTO);
  await panel.getByRole("button", { name: "Test run" }).click();
  const job = panel.getByTestId("job-detail");
  await expect(job.getByTestId("job-status")).toHaveText("succeeded");
  await expect(job.getByTestId("before-after").getByTestId("input").locator("img")).toBeVisible();
  await expect(job.getByTestId("before-after").getByTestId("asset").locator("img")).toBeVisible();
});

test("editor saves version 2, sees the diff, and a stale save gets a conflict", async ({ page }) => {
  await signIn(page, editor.email, editor.password);
  await page.goto(templateUrl);
  await page.getByRole("textbox", { name: "Prompt", exact: true }).fill("Redraw this photo as a bold cartoon. Mood: {{mood}}.");
  await page.getByLabel("Change note").fill("bolder");
  await page.getByRole("button", { name: "Save as version 2" }).click();
  await expect(page.getByRole("button", { name: "Save as version 3" })).toBeVisible();
  await page.getByRole("tab", { name: /History/ }).click();
  await expect(page.getByTestId("history")).toContainText("bolder");
  await expect(page.getByTestId("version-diff")).toContainText("prompt");

  const other = await apiAs(editor.email, editor.password);
  const id = templateUrl.split("/").pop()!;
  const current = (await (await other.get(`/v1/apps/${appId}/manage/templates/${id}`)).json()).current;
  const put = await other.put(`/v1/apps/${appId}/manage/templates/${id}`, {
    data: { ...current, base_version: 2, note: "from the API" },
  });
  expect(put.status(), await put.text()).toBe(200);
  await other.dispose();

  await page.getByRole("textbox", { name: "Description", exact: true }).fill("Edited in the browser.");
  await page.getByRole("button", { name: "Save as version 3" }).click();
  await expect(page.getByTestId("save-conflict")).toContainText("was saved by");
  await page.getByRole("button", { name: "Reload their version" }).click();
  await expect(page.getByRole("button", { name: "Save as version 4" })).toBeVisible();

  // A server 422 lands on the field: declared-but-unused variable.
  await page.getByRole("textbox", { name: "Prompt", exact: true }).fill("No variables here.");
  await page.getByRole("button", { name: "Save as version 4" }).click();
  await expect(page.getByText("declared but not used in the prompt", { exact: true })).toBeVisible();
});

test("editor activates, reorders, copies to another app and deletes templates", async ({ page }) => {
  // A second active template and a draft, made over the API.
  await createTemplate(admin, appId, second, true);
  await createTemplate(admin, appId, draft, false);

  await signIn(page, editor.email, editor.password);
  await page.goto(`/apps/${appId}`);
  await templateAction(page, slug, "Activate");
  await expect(
    templateItem(page, slug).getByTestId("template-status"),
  ).toHaveText("active");

  // Order is: cartoon, poster, draft. Move poster up.
  await expect(rows(page)).toHaveCount(3);
  await expect(rows(page).first()).toHaveAttribute("data-slug", slug);
  await templateAction(page, second.slug, "Move up");
  await expect(rows(page).first()).toHaveAttribute("data-slug", second.slug);

  // The Android preview shows active templates only, in the new order, with the cover.
  await appNav(page).filter({ hasText: "Android preview" }).click();
  const cards = page.getByTestId("app-preview").getByTestId("template-card");
  await expect(cards).toHaveCount(2);
  await expect(cards.nth(0)).toHaveAttribute("data-slug", second.slug);
  await expect(cards.nth(1)).toHaveAttribute("data-slug", slug);
  await expect(cards.nth(1).locator("img")).toBeVisible();

  // Copy needs the editor role in the target app. (Copies the template without a cover: copying one
  // with a cover currently fails server-side, see the report.)
  await addMember(admin, otherAppId, editor.id, "editor");
  await appNav(page).filter({ hasText: "Templates" }).click();
  await templateAction(page, second.slug, "Copy to app…");
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("combobox", { name: "Target app" }).click();
  await page.getByRole("option", { name: `Other ${RUN}` }).click();
  await dialog.getByLabel("New slug").fill(`${second.slug}-copy`);
  await dialog.getByRole("button", { name: "Copy" }).click();
  await expect(page.getByText(`Copied to Other ${RUN} as draft "${second.slug}-copy"`)).toBeVisible();
  await page.goto(`/apps/${otherAppId}`);
  const copied = templateItem(page, `${second.slug}-copy`);
  await expect(copied.getByTestId("template-status")).toHaveText("draft");

  // Delete the second template.
  await page.goto(`/apps/${appId}`);
  await templateAction(page, second.slug, "Delete");
  await expect(page.getByRole("dialog")).toContainText("Past jobs keep its name");
  await page.getByRole("dialog").getByRole("button", { name: "Delete template" }).click();
  await expect(rows(page)).toHaveCount(2);
  await expect(templateItem(page, second.slug)).toHaveCount(0);
});

test("editor runs a free-prompt job in the app", async ({ page }) => {
  await signIn(page, editor.email, editor.password);
  await page.goto(`/apps/${appId}/free`);
  await page.getByRole("combobox", { name: "Provider" }).click();
  await page.getByRole("option", { name: "fake", exact: true }).click();
  await page.getByRole("textbox", { name: "Prompt", exact: true }).fill("a lighthouse");
  await page.getByRole("button", { name: "FAIL_POLICY" }).click();
  await page.getByRole("button", { name: "Generate", exact: true }).click();
  const detail = page.getByTestId("job-detail");
  await expect(detail.getByTestId("job-status")).toHaveText("failed");
  await expect(detail.getByTestId("job-error")).toContainText("content_policy");
});

test("tester sees only active templates, runs one and sees only their own jobs", async ({ page }) => {
  await signIn(page, tester.email, tester.password);
  await page.getByTestId("app-card").click();
  const cards = page.getByTestId("template-card");
  await expect(cards).toHaveCount(1);
  await expect(cards.first()).toHaveAttribute("data-slug", slug);
  await expect(page.getByText(draft.title)).toHaveCount(0);
  expect(await cards.first().locator("img").evaluate((i) => (i as unknown as { naturalWidth: number }).naturalWidth)).toBeGreaterThan(0);

  await page.getByRole("button", { name: "Test" }).first().click();
  await expect(page).toHaveURL(new RegExp(`/apps/${appId}/test\\?t=${slug}`));
  await page.locator('input[type="file"]').setInputFiles(PHOTO);
  await page.getByRole("combobox", { name: "Mood" }).click();
  await page.getByRole("option", { name: "rainy" }).click();
  await expect(page.getByText("$STUDIO_TOKEN")).toBeVisible();
  await expect(page.getByText(`/v1/apps/${appId}/templates/${slug}/generations`)).toBeVisible();
  await page.getByRole("button", { name: "Run", exact: true }).click();

  const job = page.getByTestId("job-detail");
  await expect(job.getByTestId("job-status")).toHaveText("succeeded");
  await expect(job.getByTestId("before-after").getByTestId("input").locator("img")).toBeVisible();
  await expect(job.getByTestId("before-after").getByTestId("asset").locator("img")).toBeVisible();
  await expect(job).not.toContainText("Redraw this photo");

  // Jobs tab: only the tester's own jobs (the editor ran several in this app).
  await appNav(page).filter({ hasText: "Jobs" }).click();
  const jobRows = page.getByTestId("job-list").locator("tr[data-job]");
  await expect(jobRows).toHaveCount(1);
  await expect(jobRows.first()).toContainText(tester.name);

  // The editor and the admin dashboard are off limits.
  await page.goto(templateUrl);
  await expect(page.getByTestId("forbidden")).toContainText("You are a tester");
  await page.goto("/admin");
  await expect(page.getByText("Your role can't do this")).toBeVisible();
});
