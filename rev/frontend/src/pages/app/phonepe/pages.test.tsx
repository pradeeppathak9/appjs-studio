import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test } from "vitest";
import { App } from "../../../App";
import { calls, page, renderAt, stubApi } from "../../../test/render";

const ME = { id: 3, email: "user@example.com", full_name: "User", is_admin: false };
const APP = {
  id: "app1",
  name: "Looksy",
  api_key: "APPKEY",
  enabled: true,
  phonepe_enabled: true,
  razorpay_enabled: false,
  phonepe_environment: "PROD",
  razorpay_environment: "TEST",
  phonepe_client_id: "cid",
  razorpay_key_id: null,
};
const SUB = {
  id: "sub_abc",
  app_id: "app1",
  phone_number: "9876543210",
  amount: 100,
  max_amount: 49900,
  amount_type: "VARIABLE",
  frequency: "MONTHLY",
  auth_workflow_type: "TRANSACTION",
  product_type: "UPI_MANDATE",
  state: "ACTIVE",
  phonepe_subscription_id: "OMS123",
  phonepe_order_id: "OMO123",
  next_payment_date: Date.UTC(2026, 11, 5),
  last_payment_status: "COMPLETED",
  total_payments: 2,
  trail_days: 3,
  expire_at: null,
  created_at: "2026-11-01T10:00:00+05:30",
};
const SCHED = {
  id: "sch_1",
  subscription_id: "sub_abc",
  payment_date: Date.UTC(2026, 10, 5),
  amount: 49900,
  state: "FAILED",
  attempts: 2,
  created_at: "2026-11-04T10:00:00+05:30",
  transaction_id: null,
  merchant_order_id: "MO_1",
};

const base = { "/api/auth/me": ME, "/api/apps": [APP], "/api/apps/app1": APP, "/api/health": { status: "ok" } };

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("token", "tok");
});

describe("PhonePe subscriptions", () => {
  test("lists rows, counts pills without the state filter, and counts only on page 0", async () => {
    const fetch = stubApi({
      ...base,
      "/api/apps/app1/subscriptions/state-counts": { ACTIVE: 60, FAILED: 3 },
      "/api/apps/app1/subscriptions": (u: URL) =>
        page(Array.from({ length: 50 }, (_, i) => ({ ...SUB, id: `sub_${i}` })), u.searchParams.get("with_count") === "true" ? 63 : null),
    });
    renderAt("/apps/app1/subscriptions", <App />);
    expect(await screen.findByText("sub_0")).toBeInTheDocument();
    expect(screen.getByText("63 results")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /All\s*63/ })).toBeInTheDocument();
    expect(screen.getByText(/Page 1 of 2/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Next/ }));
    await waitFor(() => expect(calls(fetch, "/subscriptions").some((u) => u.searchParams.get("offset") === "50")).toBe(true));
    const second = calls(fetch, "/subscriptions").find((u) => u.searchParams.get("offset") === "50")!;
    expect(second.searchParams.get("with_count")).toBe("false");
    expect(await screen.findByText(/Page 2 of 2/)).toBeInTheDocument();

    // Picking a state filters the list but not the counts.
    await userEvent.click(screen.getByRole("radio", { name: /Failed/ }));
    await waitFor(() => expect(calls(fetch, "/subscriptions").some((u) => u.searchParams.get("state") === "FAILED")).toBe(true));
    expect(calls(fetch, "/state-counts").every((u) => !u.searchParams.has("state"))).toBe(true);
    // ...and goes back to page 0.
    const filtered = calls(fetch, "/subscriptions").find((u) => u.searchParams.get("state") === "FAILED")!;
    expect(filtered.searchParams.get("offset")).toBe("0");
  });

  test("search sends a phone number or a subscription id; default window is today", async () => {
    const fetch = stubApi({ ...base, "/api/apps/app1/subscriptions": () => page([SUB], 1) });
    renderAt("/apps/app1/subscriptions", <App />);
    await screen.findByText("sub_abc");
    const first = calls(fetch, "/subscriptions")[0];
    expect(first.searchParams.get("start_date")).toBe(first.searchParams.get("end_date"));

    const box = screen.getByPlaceholderText("Phone or subscription ID");
    await userEvent.type(box, "9876543210{enter}");
    await waitFor(() => expect(calls(fetch, "/subscriptions").some((u) => u.searchParams.get("phone_number") === "9876543210")).toBe(true));
    await userEvent.click(screen.getByRole("button", { name: "Clear search" }));
    await userEvent.type(screen.getByPlaceholderText("Phone or subscription ID"), "sub_abc{enter}");
    await waitFor(() => expect(calls(fetch, "/subscriptions").some((u) => u.searchParams.get("subscription_id") === "sub_abc")).toBe(true));
  });

  test("an id opens the details drawer with its schedule", async () => {
    stubApi({
      ...base,
      "/api/apps/app1/subscriptions": () => page([SUB], 1),
      "/api/apps/app1/scheduled": (u: URL) => (u.searchParams.get("subscription_id") === "sub_abc" ? [SCHED] : []),
    });
    renderAt("/apps/app1/subscriptions", <App />);
    await userEvent.click(await screen.findByRole("button", { name: "sub_abc" }));
    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).getByText("OMS123")).toBeInTheDocument();
    expect(await within(drawer).findByText("MO_1")).toBeInTheDocument();
    expect(within(drawer).getByText("₹1.00 (3d)")).toBeInTheDocument();
  });

  test("the live status uses the app's API key, and its 401 does not sign out", async () => {
    const fetch = stubApi({
      ...base,
      "/api/apps/app1/subscriptions": () => page([SUB], 1),
      "/api/v1/app1/phonepay": () => new Response(JSON.stringify({ detail: "Invalid API key" }), { status: 401 }),
    });
    renderAt("/apps/app1/subscriptions", <App />);
    await userEvent.click(await screen.findByRole("button", { name: "9876543210" }));
    expect(await screen.findByText("Invalid API key")).toBeInTheDocument();
    const call = fetch.mock.calls.find(([u]) => String(u).includes("/phonepay/9876543210/status"))!;
    expect((call[1]?.headers as Record<string, string>).Authorization).toBe("Bearer APPKEY");
    expect(localStorage.getItem("token")).toBe("tok");
  });

  test("revoke posts the id and shows the new state", async () => {
    const fetch = stubApi({
      ...base,
      "/api/apps/app1/subscriptions": (u: URL, init?: RequestInit) =>
        init?.method === "POST" ? { ...SUB, state: "REVOKED" } : u.pathname.endsWith("/state-counts") ? {} : page([SUB], 1),
    });
    renderAt("/apps/app1/subscriptions", <App />);
    await userEvent.click(await screen.findByRole("button", { name: /Revoke a subscription/ }));
    await userEvent.type(await screen.findByLabelText("Subscription ID"), "sub_abc");
    await userEvent.click(screen.getByRole("button", { name: "Revoke subscription" }));
    expect(await screen.findByText("Mandate cancelled at PhonePe.")).toBeInTheDocument();
    const post = fetch.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(String(post[0])).toContain("/api/apps/app1/subscriptions/sub_abc/revoke");
  });
});

describe("PhonePe transactions", () => {
  test("a row opens its attempts; the subscription id opens the subscription", async () => {
    stubApi({
      ...base,
      "/api/apps/app1/scheduled": (u: URL) =>
        u.pathname.endsWith("/attempts")
          ? [{ id: "ORDER_1", subscription_id: "sub_abc", scheduled_transaction_id: "sch_1", amount: 49900, state: "FAILED", payment_due_date: null, transaction_id: "T1", created_at: "2026-11-04T10:00:00+05:30" }]
          : u.pathname.endsWith("/state-counts")
            ? { FAILED: 1 }
            : page([SCHED], 1),
      "/api/apps/app1/subscriptions/sub_abc": SUB,
    });
    renderAt("/apps/app1/transactions", <App />);
    await userEvent.click(await screen.findByRole("row", { name: /Payment attempts/ }));
    const drawer = await screen.findByRole("dialog");
    expect(await within(drawer).findByText("ORDER_1")).toBeInTheDocument();
    await userEvent.click(within(drawer).getByRole("button", { name: "sub_abc" }));
    expect(await screen.findByText("OMS123")).toBeInTheDocument();
  });
});

describe("PhonePe summary", () => {
  test("shows the totals for today", async () => {
    stubApi({
      ...base,
      "/api/apps/app1/summary": {
        subscriptions_total: 10,
        subscriptions_by_state: { ACTIVE: 4, FAILED: 6 },
        scheduled_total: 2,
        scheduled_by_state: { SCHEDULED: 2 },
        scheduled_value_paise: 99800,
        scheduled_value_by_state_paise: { SCHEDULED: 99800 },
        transactions_total: 3,
        transactions_by_state: { COMPLETED: 3 },
        revenue_collected_paise: 150000,
        payment_revenue_collected_paise: 149700,
        trial_revenue_collected_paise: 300,
        trial_setups_count: 3,
      },
    });
    renderAt("/apps/app1", <App />);
    expect(await screen.findByText("₹1,500")).toBeInTheDocument();
    expect(screen.getByText("40% of subscriptions created")).toBeInTheDocument();
    expect(screen.getByText("Subscriptions by state")).toBeInTheDocument();
  });
});
