import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test } from "vitest";
import { App } from "../../../App";
import { calls, renderAt, stubApi } from "../../../test/render";

const ME = { id: 3, email: "user@example.com", full_name: "User", is_admin: false };
const APP = {
  id: "app1", name: "Acme", api_key: "k", enabled: true, phonepe_enabled: false, razorpay_enabled: true,
  phonepe_environment: "UAT", razorpay_environment: "TEST", phonepe_client_id: null, razorpay_key_id: "rzp",
};
const SUB = {
  id: "rsub_1", app_id: "app1", phone_number: "9876543210", name: "Jane Doe", email: null, amount: 9900, max_amount: 50000,
  amount_type: "FIXED", frequency: "MONTHLY", method: "upi", state: "ACTIVE", razorpay_customer_id: "cust_1",
  razorpay_order_id: "order_1", razorpay_token_id: "token_1", next_payment_date: null, last_payment_status: null,
  total_payments: 1, trail_days: 0, expire_at: null, created_at: "2026-11-01T10:00:00+05:30",
};

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("token", "tok");
});

test("Razorpay-only apps land on subscriptions; with no count, Next follows a full page", async () => {
  const fetch = stubApi({
    "/api/auth/me": ME,
    "/api/apps": [APP],
    "/api/apps/app1": APP,
    "/api/apps/app1/razorpay-subscriptions": (u: URL) =>
      u.pathname.endsWith("/transactions")
        ? [{ id: "tx_1", subscription_id: "rsub_1", amount: 9900, state: "SUCCESS", razorpay_order_id: "order_2", razorpay_payment_id: "pay_1", created_at: "2026-11-02T10:00:00+05:30" }]
        : u.searchParams.get("offset") === "0"
          ? Array.from({ length: 50 }, (_, i) => ({ ...SUB, id: `rsub_${i}` }))
          : [SUB],
  });
  renderAt("/apps/app1", <App />);
  expect(await screen.findByText("rsub_0")).toBeInTheDocument();
  expect(screen.getByText("Page 1")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /Next/ }));
  expect(await screen.findByText("Page 2")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Next/ })).toBeDisabled();
  expect(calls(fetch, "/razorpay-subscriptions").map((u) => u.searchParams.get("offset"))).toContain("50");

  await userEvent.click(screen.getByRole("button", { name: "rsub_1" }));
  const drawer = await screen.findByRole("dialog");
  expect(await within(drawer).findByText("pay_1")).toBeInTheDocument();
  await waitFor(() => expect(within(drawer).getByText("token_1")).toBeInTheDocument());
});
