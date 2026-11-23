import { expect, test, type Page } from "@playwright/test";
import { appNav, firstSignIn, logOut, RUN, signIn, signInAdmin } from "./helpers";

test.describe.configure({ mode: "serial" });

const appName = `Pixel Fun ${RUN}`;
const appSlug = `pixel-fun-${RUN}`;
const editor = { email: `editor-${RUN}@example.com`, name: `Editor ${RUN}`, password: `editor-pass-${RUN}`, temp: "" };
const tester = { email: `tester-${RUN}@example.com`, name: `Tester ${RUN}`, password: `tester-pass-${RUN}`, temp: "" };
let appUrl = "";

async function addUser(page: Page, u: typeof editor) {
  await page.getByRole("button", { name: "Add user" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Email").fill(u.email);
  await dialog.getByLabel("Name").fill(u.name);
  await dialog.getByRole("button", { name: "Create" }).click();
  const temp = page.getByTestId("temp-password");
  await expect(temp).toBeVisible();
  u.temp = (await temp.textContent())!.trim();
  await page.getByRole("button", { name: "Done" }).click();
  await expect(page.getByTestId("users-table").locator(`tr[data-email="${u.email}"]`)).toBeVisible();
}

function appCard(page: Page, slug = appSlug) {
  return page.locator(`[data-testid="app-card"][data-slug="${slug}"]`);
}

test("admin creates the app and two users, and assigns them", async ({ page }) => {
  await signInAdmin(page);
  await expect(page.getByTestId("health")).toContainText("All systems normal");
  await page.getByRole("link", { name: "Admin" }).click();
  await expect(page).toHaveURL(/\/admin\/users$/);

  await addUser(page, editor);
  await addUser(page, tester);

  await page.getByRole("tab", { name: "Apps" }).click();
  await page.getByRole("button", { name: "New app" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Name").fill(appName);
  await dialog.getByLabel("Slug").fill(appSlug);
  await dialog.getByRole("button", { name: "Create app" }).click();
  await expect(page).toHaveURL(/\/admin\/apps\/[0-9a-f-]{36}$/);
  appUrl = page.url();

  // Add the editor from the app's Members section.
  await page.getByRole("combobox", { name: "Add member" }).click();
  await page.getByRole("option", { name: new RegExp(editor.email) }).click();
  await page.getByRole("combobox", { name: "New member role" }).click();
  await page.getByRole("option", { name: "editor", exact: true }).click();
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByTestId("members-table").locator(`tr[data-email="${editor.email}"]`)).toBeVisible();

  // Add the tester from the user's Apps panel.
  await page.getByRole("tab", { name: "Users" }).click();
  await page.getByTestId("users-table").locator(`tr[data-email="${tester.email}"]`).getByRole("button", { name: "Apps" }).click();
  const apps = page.getByTestId("user-apps");
  await apps.getByRole("combobox", { name: "Add to app" }).click();
  await page.getByRole("option", { name: appName, exact: true }).click();
  await apps.getByRole("button", { name: "Add", exact: true }).click();
  await expect(apps.locator("tr[data-app]", { hasText: appName })).toBeVisible();
  await page.keyboard.press("Escape");

  // The admin sees every app on the home page, with the admin role.
  await page.goto("/");
  await expect(appCard(page).getByTestId("app-role")).toHaveText("admin");
});

test("tester changes the temporary password, sees only their app and no admin", async ({ page }) => {
  await firstSignIn(page, tester.email, tester.temp, tester.password);
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByTestId("app-card")).toHaveCount(1);
  await expect(appCard(page).getByTestId("app-role")).toHaveText("tester");
  await expect(page.getByRole("link", { name: "Admin" })).toHaveCount(0);

  await appCard(page).click();
  await expect(appNav(page)).toHaveText(["Templates", "Test", "Jobs"]);
  await page.goto(`${new URL(page.url()).pathname}/free`);
  await expect(page.getByTestId("forbidden")).toBeVisible();

  await page.goto("/admin");
  await expect(page.getByText("Your role can't do this")).toBeVisible();
  // The server enforces it too.
  const r = await page.request.get("/v1/admin/users");
  expect(r.status()).toBe(403);
});

test("editor sees only Pixel Fun, with editor tabs", async ({ page }) => {
  await firstSignIn(page, editor.email, editor.temp, editor.password);
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByTestId("app-card")).toHaveCount(1);
  await expect(appCard(page).getByTestId("app-role")).toHaveText("editor");
  await appCard(page).click();
  await expect(appNav(page)).toHaveText(["Templates", "Test", "Free prompt", "Jobs", "Android preview", "Integration guide"]);
});

test("signed-out visit goes to login and returns to the page after sign-in", async ({ page }) => {
  await page.goto("/account");
  await expect(page).toHaveURL(/\/login\?next=%2Faccount$/);
  await page.getByLabel("Email").fill(editor.email);
  await page.getByRole("textbox", { name: "Password", exact: true }).fill("wrong-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("login-error")).toBeVisible();
  await page.getByRole("textbox", { name: "Password", exact: true }).fill(editor.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/account$/);
});

test("old paths redirect to My apps", async ({ page }) => {
  await signIn(page, editor.email, editor.password);
  for (const path of ["/use", "/templates", "/generate", "/users", "/apps"]) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/$/);
  }
});

test("account: an API token is shown once, works as Bearer, and stops working when revoked", async ({
  page,
  playwright,
}) => {
  await signIn(page, tester.email, tester.password);
  await page.goto("/account");
  await page.getByRole("button", { name: "New token" }).click();
  await page.getByRole("dialog").getByLabel("Name").fill("e2e");
  await page.getByRole("button", { name: "Create token" }).click();
  const token = (await page.getByTestId("new-token").textContent())!.trim();
  expect(token).toMatch(/^crt_/);
  await page.getByRole("button", { name: "Done" }).click();

  const bearer = await playwright.request.newContext({
    baseURL: new URL(page.url()).origin,
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
  });
  expect((await bearer.get("/v1/apps")).status()).toBe(200);
  page.once("dialog", (d) => d.accept());
  await page.getByTestId("token-table").getByRole("button", { name: "Revoke" }).first().click();
  await expect.poll(async () => (await bearer.get("/v1/auth/me")).status()).toBe(401);
  await bearer.dispose();
});

test("admin resets a password; the user must change it again", async ({ page }) => {
  await signInAdmin(page);
  await page.goto("/admin/users");
  page.once("dialog", (d) => d.accept());
  const row = page.getByTestId("users-table").locator(`tr[data-email="${tester.email}"]`);
  await row.getByRole("button", { name: "Actions" }).click();
  await page.getByRole("menuitem", { name: "Reset password" }).click();
  const temp = (await page.getByTestId("temp-password").textContent())!.trim();
  await page.getByRole("button", { name: "Done" }).click();
  await logOut(page);
  await expect(page).toHaveURL(/\/login$/);
  tester.password = `tester-pass2-${RUN}`;
  await firstSignIn(page, tester.email, temp, tester.password);
  await expect(page).toHaveURL(/\/$/);
});

test("admin removes the tester from the app; the app leaves their home", async ({ page, browser }) => {
  await signInAdmin(page);
  await page.goto(appUrl);
  await page.getByTestId("members-table").locator("tr", { hasText: tester.email }).getByRole("button", { name: "Remove" }).click();
  await expect(page.getByTestId("members-table").locator("tr", { hasText: tester.email })).toHaveCount(0);

  const t = await browser.newPage();
  await signIn(t, tester.email, tester.password);
  await expect(t.getByTestId("no-apps")).toContainText("Ask an admin to add you to an app");
  await t.close();
});

test("admin deletes a user; they can't sign in any more", async ({ page }) => {
  await signInAdmin(page);
  await page.goto("/admin/users");
  const row = page.getByTestId("users-table").locator(`tr[data-email="${tester.email}"]`);
  await row.getByRole("button", { name: "Actions" }).click();
  await page.getByRole("menuitem", { name: "Delete user" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("their name stays on the jobs");
  await dialog.getByRole("button", { name: "Delete user" }).click();
  await expect(row).toHaveCount(0);

  // No delete on your own row.
  const own = page.getByTestId("users-table").locator("tr", { hasText: "(you)" });
  await own.getByRole("button", { name: "Actions" }).click();
  await expect(page.getByRole("menuitem", { name: "Delete user" })).toHaveCount(0);
  await page.keyboard.press("Escape");

  await logOut(page);
  await page.getByLabel("Email").fill(tester.email);
  await page.getByRole("textbox", { name: "Password", exact: true }).fill(tester.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("login-error")).toBeVisible();
});

test("admin deletes the app after typing its slug", async ({ page }) => {
  await signInAdmin(page);
  await page.goto(appUrl);
  await page.getByRole("button", { name: "Delete app" }).click();
  const dialog = page.getByRole("dialog");
  const confirm = dialog.getByRole("button", { name: "Delete app" });
  await expect(confirm).toBeDisabled();
  await dialog.getByRole("textbox").fill(appSlug);
  await confirm.click();
  await expect(page).toHaveURL(/\/admin\/apps$/);
  await expect(page.getByTestId("admin-apps-table").locator(`tr[data-slug="${appSlug}"]`)).toHaveCount(0);
  await page.goto("/");
  await expect(appCard(page)).toHaveCount(0);
});
