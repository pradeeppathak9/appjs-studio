import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test } from "vitest";
import { App } from "../../../App";
import { renderAt, stubApi } from "../../../test/render";

const ME = { id: 3, email: "user@example.com", full_name: "User", is_admin: false };
const APP = {
  id: "fee3024f5d6c4696a0ca6e9e341122dc",
  name: "marktmakrs",
  api_key: "k".repeat(64),
  enabled: true,
  phonepe_enabled: true,
  razorpay_enabled: true,
  phonepe_environment: "PROD",
  razorpay_environment: "TEST",
  phonepe_client_id: "cid",
  razorpay_key_id: "rzp_test_x",
};

async function open(path: string, app = APP) {
  stubApi({ "/api/auth/me": ME, "/api/apps": [app], [`/api/apps/${app.id}`]: app });
  const r = renderAt(path, <App />);
  await screen.findByRole("heading", { name: "Integration guide" });
  return r.container;
}

const GUIDE = `/apps/${APP.id}/integration-guide`;

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("token", "tok");
});

describe("PhonePe guide", () => {
  test("documents every API, with anchors and this app's URLs", async () => {
    const html = (await open(GUIDE)).innerHTML;
    for (const t of ["Setup", "Subscription Status", "User Status", "User Subscriptions", "Invoices", "Revoke", "Report"]) {
      expect(html).toContain(t);
    }
    expect(html).toContain(`/api/v1/${APP.id}/phonepay/setup`);
    expect(html).toContain(`/api/v1/${APP.id}/phonepay/revoke/`);
    expect(html).toContain(`/api/v1/${APP.id}/phonepay/{phone_number}/subscriptions`);
    expect(html).toContain(`/api/v1/${APP.id}/phonepay/{phone_number}/invoices`);
    expect(html).toContain(`/api/v1/${APP.id}/phonepay/report`);
    for (const id of ["user-subscriptions", "invoices", "report"]) {
      expect(html).toContain(`id="${id}"`);
      expect(html).toContain(`href="#${id}"`);
    }
    expect(html).toContain(`"app_id": "${APP.id}"`);
    expect(html).not.toContain("{app_id}");
  });

  test("flags the field traps, required params, auth and errors", async () => {
    const html = (await open(GUIDE)).innerHTML;
    expect(html).toContain("epoch milliseconds");
    expect(html).toContain("SETUP");
    expect(html).toContain("RECURRING");
    expect(html).toContain("Required");
    expect(html).toContain("Optional");
    expect(html).toContain("Authorization: Bearer YOUR_API_KEY");
    expect(html).toContain("401");
    expect(html).toContain("502");
  });

  test("never leaks the real API key into the page", async () => {
    expect((await open(GUIDE)).innerHTML).not.toContain(APP.api_key);
    expect((await open(`${GUIDE}?gateway=razorpay`)).innerHTML).not.toContain(APP.api_key);
  });
});

describe("Razorpay guide", () => {
  test("a tab per enabled gateway; the Razorpay tab is linkable", async () => {
    await open(GUIDE);
    await userEvent.click(screen.getByRole("tab", { name: "Razorpay" }));
    expect(await screen.findByRole("heading", { name: "How AutoRev collects" })).toBeInTheDocument();
  });

  test("documents the whole Razorpay flow with this app's URLs", async () => {
    const html = (await open(`${GUIDE}?gateway=razorpay`)).innerHTML;
    const base = `/api/v1/${APP.id}/razorpay`;
    for (const path of [
      `${base}/setup`,
      `${base}/status/{subscription_id}`,
      `${base}/{phone_number}/status`,
      `${base}/{phone_number}/subscriptions`,
      `${base}/revoke/{subscription_id}`,
      `${base}/webhook`,
    ]) {
      expect(html).toContain(path);
    }
    // Checkout needs these three to authorise a recurring payment
    for (const opt of ["customer_id", "order_id", 'recurring: "1"']) expect(html).toContain(opt);
    // the setup body names every field the endpoint validates
    for (const f of ["name", "phone_number", "amount", "max_amount", "method", "frequency", "trail_days"]) {
      expect(screen.getAllByText(f, { selector: "code" }).length).toBeGreaterThan(0);
    }
    expect(html).toContain("marktmakrs");
  });

  test("the integrator only sets up and checks status; AutoRev collects", async () => {
    const html = (await open(`${GUIDE}?gateway=razorpay`)).innerHTML;
    // gating is on the paid-until date, and the old collection calls are documented as gone
    expect(html).toContain("subscription_validity_end_date");
    expect(html).toContain("410");
    expect(screen.getByRole("heading", { name: "How AutoRev collects" })).toBeInTheDocument();
    expect(screen.getByText(/3 attempts/)).toBeInTheDocument();
    // the example backend has no collection job
    expect(html).not.toContain("notify-redemption/&lt;");
    expect(html).not.toContain("collect_due");
    for (const e of ["token.confirmed", "token.rejected", "token.cancelled"]) expect(html).toContain(e);
  });

  test("a Razorpay-only app shows just its guide, no tabs", async () => {
    await open(GUIDE, { ...APP, phonepe_enabled: false });
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Open Checkout" })).toBeInTheDocument();
  });
});
