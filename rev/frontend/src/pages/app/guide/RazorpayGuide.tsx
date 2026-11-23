import { Anchor, List, Stack } from "@mantine/core";
import type { ReactNode } from "react";
import type { App } from "../../../api/types";
import { AuthSection } from "./PhonePeGuide";
import { C, CodeBlock, GuideSection, Note, P, Params, RefTable, Toc } from "./parts";

const RZP_DOCS = {
  authorise: "https://razorpay.com/docs/api/payments/recurring-payments/upi/create-authorization-transaction/",
  subsequent: "https://razorpay.com/docs/api/payments/recurring-payments/upi/create-subsequent-payments/",
  webhooks: "https://razorpay.com/docs/api/payments/recurring-payments/webhooks/",
};

const NAV: [string, string][] = [
  ["rz-how", "How it works"],
  ["rz-connect", "Connect Razorpay"],
  ["rz-auth", "Authentication"],
  ["rz-setup", "Setup"],
  ["rz-checkout", "Open Checkout"],
  ["rz-status", "Subscription Status"],
  ["rz-user-status", "User Status"],
  ["rz-user-subscriptions", "User Subscriptions"],
  ["rz-billing", "How AutoRev collects"],
  ["rz-webhook", "Webhook"],
  ["rz-revoke", "Revoke"],
  ["rz-example", "Example backend"],
  ["rz-errors", "Errors"],
];

function Ext({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Anchor href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </Anchor>
  );
}

export function RazorpayGuide({ app, apiBase }: { app: App; apiBase: string }) {
  const base = `${apiBase}/api/v1/${app.id}/razorpay`;
  const webhookUrl = `${base}/webhook`;
  return (
    <Stack gap="lg">
      <P>
        Everything your server needs to put <strong>{app.name}</strong> customers on a recurring Razorpay payment. Your side
        is two calls — <Anchor href="#rz-setup">Setup</Anchor> and <Anchor href="#rz-status">Status</Anchor> — plus opening
        Razorpay Checkout once. AutoRev collects every payment after that. The URLs below already carry this app's ID.
      </P>
      <Toc items={NAV} />

      <GuideSection id="rz-how" title="How it works">
        <RefTable
          head={["Step", "Who", "What happens"]}
          rows={[
            ["1. Setup", "Your server → AutoRev", "AutoRev creates the Razorpay customer and an authorisation order. State AUTHORIZATION_PENDING."],
            ["2. Authorise", "Customer, in Razorpay Standard Checkout", "Pays the first period and approves the UPI Autopay mandate."],
            ["3. Activate", "AutoRev", "On Razorpay's webhook (or your Status call) the subscription becomes ACTIVE, with a paid-until date."],
            ["4. Collect", "AutoRev, every cycle", "Charges the saved mandate a day before each due date, retries failures, and moves the paid-until date on."],
            ["5. Check", "Your server → AutoRev", "Reads Status and gives access while subscription_validity_end_date has not passed."],
          ]}
        />
        <Note>
          There is no "charge now" call: you never collect. The old <C>notify-redemption</C> and{" "}
          <C>execute-redemption</C> calls answer <C>410 Gone</C>.
        </Note>
        <P>
          Money is <strong>paise</strong> as an integer (<C>9900</C> is ₹99.00). Dates are calendar dates,{" "}
          <C>YYYY-MM-DD</C>, in IST.
        </P>
        <Note tone="warn" title="Before you go live">
          Run the whole flow in Razorpay <strong>test mode</strong> first: authorise, wait for a collection, revoke. UPI
          Autopay is the method AutoRev is built and tested against (<Ext href={RZP_DOCS.authorise}>Razorpay docs</Ext>);
          e-mandate and card have their own rules and have not been tried. There are no outbound <C>subscription.*</C>{" "}
          webhooks for Razorpay yet — read Status instead.
        </Note>
      </GuideSection>

      <GuideSection id="rz-connect" title="Connect Razorpay">
        <P>Once per app and per mode (test, then live):</P>
        <List type="ordered" size="sm" spacing={6}>
          <List.Item>In the Razorpay Dashboard, make sure Recurring Payments (UPI Autopay) is enabled on the account.</List.Item>
          <List.Item>
            In AutoRev, open <strong>Settings → Razorpay Credentials</strong>: choose the environment, then save the Key ID, Key
            Secret and a webhook secret of your choosing. <strong>Test Connection</strong> checks the keys.
          </List.Item>
          <List.Item>
            In the Razorpay Dashboard, add a webhook with the same secret, pointing at:
            <CodeBlock label="webhook url">{webhookUrl}</CodeBlock>
            Subscribe it to <C>payment.authorized</C>, <C>order.paid</C>, <C>payment.captured</C>, <C>payment.failed</C>,{" "}
            <C>token.confirmed</C>, <C>token.rejected</C> and <C>token.cancelled</C>.
          </List.Item>
          <List.Item>
            Give your own backend the same account's <strong>Key ID</strong> (Checkout opens with it; the order only exists in
            that account). The Key Secret stays in AutoRev.
          </List.Item>
        </List>
      </GuideSection>

      <AuthSection id="rz-auth" />

      <GuideSection id="rz-setup" title="Setup" method="POST" path={`${base}/setup`}>
        <P>Creates (or reuses) the Razorpay customer for this phone number and an authorisation order for Checkout.</P>
        <Params
          rows={[
            { name: "name", type: "string", required: true, notes: "Customer name, stored on the Razorpay customer" },
            { name: "email", type: "string", required: true, notes: "Razorpay needs it for every collection" },
            { name: "phone_number", type: "string", required: true, notes: "Exactly 10 digits, no country code; sent to Razorpay as +91…" },
            { name: "amount", type: "int (paise)", required: true, notes: "The price. Paid at authorisation for the first period, then collected every cycle. At least 100 (₹1); more than max_amount is a 400" },
            { name: "max_amount", type: "int (paise)", required: true, notes: "Most the mandate may debit at once. Razorpay caps UPI at ₹99,999 for most businesses" },
            { name: "frequency", type: "enum", required: false, def: "ON_DEMAND", notes: "DAILY · WEEKLY · FORTNIGHTLY · MONTHLY · BIMONTHLY · QUARTERLY · HALFYEARLY · YEARLY. Pass one: ON_DEMAND has no schedule, so nothing is ever collected" },
            { name: "method", type: "enum", required: false, def: "upi", notes: "upi (tested) · emandate · card" },
            { name: "trail_days", type: "int", required: false, def: "0", notes: "First collection this many days after setup instead of one cycle. The authorisation still charges amount" },
            { name: "amount_type", type: "enum", required: false, def: "VARIABLE", notes: "FIXED or VARIABLE. Stored only" },
          ]}
        />
        <Note tone="warn" title="Hard to change later">
          <C>amount</C> is the price for the life of the subscription; a new price means a new setup. Leave headroom in{" "}
          <C>max_amount</C>: the mandate's ceiling cannot be raised without the customer approving a new one.
        </Note>
        <CodeBlock>{`curl -X POST \\
  "${base}/setup" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
  "name": "Jane Doe",
  "email": "jane@example.com",
  "phone_number": "9876543210",
  "amount": 9900,
  "max_amount": 29900,
  "frequency": "MONTHLY",
  "method": "upi"
}'`}</CodeBlock>
        <CodeBlock label="response">{`{
  "subscription_id": "3f9a21c0e4b0c9e1d2a77c0f",
  "razorpay_customer_id": "cust_Nx1234567890ab",
  "razorpay_order_id": "order_Nx1234567890ab",
  "amount": 9900,
  "currency": "INR"
}`}</CodeBlock>
        <P muted>
          Keep <C>subscription_id</C> against your user; Status takes it.
        </P>
      </GuideSection>

      <GuideSection id="rz-checkout" title="Open Checkout">
        <P>
          In the browser or app, open Razorpay Standard Checkout on the order from Setup, with recurring turned on (
          <Ext href={RZP_DOCS.authorise}>Razorpay docs</Ext>).
        </P>
        <CodeBlock label="javascript">{`<script src="https://checkout.razorpay.com/v1/checkout.js"></script>
<script>
  // setup = what your server got back from AutoRev's /setup
  const rzp = new Razorpay({
    key: "rzp_test_xxxxxxxx",            // Key ID of the account saved in AutoRev Settings
    customer_id: setup.razorpay_customer_id,
    order_id: setup.razorpay_order_id,
    recurring: "1",
    name: "${app.name}",
    description: "Monthly subscription",
    prefill: { name: "Jane Doe", email: "jane@example.com", contact: "+919876543210" },
    handler: () => checkStatusOnServer(setup.subscription_id),
  });
  rzp.open();
</script>`}</CodeBlock>
        <Note>
          The <C>handler</C> callback is not proof of payment. Unlock access only once{" "}
          <Anchor href="#rz-status">Subscription Status</Anchor> says <C>ACTIVE</C>.
        </Note>
      </GuideSection>

      <GuideSection id="rz-status" title="Subscription Status" method="GET" path={`${base}/status/{subscription_id}`}>
        <P>
          The call to gate access on. It also checks the authorisation order with Razorpay, so polling it right after Checkout
          activates the subscription even before the webhook lands.
        </P>
        <CodeBlock>{`curl "${base}/status/<subscription_id>" \\
  -H "Authorization: Bearer YOUR_API_KEY"`}</CodeBlock>
        <CodeBlock label="response">{`{
  "subscription_id": "3f9a21c0e4b0c9e1d2a77c0f",
  "state": "ACTIVE",
  "razorpay_order_status": "paid",
  "razorpay_token_id": "token_Nx1234567890ab",
  "next_payment_date": "2026-12-05",
  "last_payment_status": "SUCCESS",
  "subscription_validity_end_date": "2026-12-11"
}`}</CodeBlock>
        <RefTable
          head={["Field", "Notes"]}
          rows={[
            ["state", "AUTHORIZATION_PENDING · ACTIVE · HALTED (collection gave up) · CANCELLED · FAILED (mandate rejected)"],
            ["next_payment_date", "The next due date. Moves one cycle on when a collection succeeds"],
            ["last_payment_status", "SUCCESS, FAILED, or null before the first collection"],
            ["subscription_validity_end_date", "Last day the customer has paid for: the due date plus a 6-day grace while AutoRev is still collecting; just the due date once HALTED or CANCELLED; null if they never paid"],
          ]}
        />
        <Note>
          Give access while today is on or before <C>subscription_validity_end_date</C> — not by <C>state</C>. A customer who
          cancels keeps the period they paid for, and one whose payment is being retried keeps access through the grace days.
        </Note>
      </GuideSection>

      <GuideSection id="rz-user-status" title="User Status" method="GET" path={`${base}/{phone_number}/status`}>
        <P>
          The same answer looked up by phone number. Where a number holds several subscriptions it picks the{" "}
          <C>ACTIVE</C> one, then <C>HALTED</C>, then <C>CANCELLED</C>, then the newest. An unknown number returns{" "}
          <C>{`{"state": "NOT_FOUND"}`}</C>.
        </P>
        <CodeBlock>{`curl "${base}/9876543210/status" \\
  -H "Authorization: Bearer YOUR_API_KEY"`}</CodeBlock>
        <P muted>
          Fields: <C>subscription_id</C>, <C>state</C>, <C>next_payment_date</C>, <C>last_payment_status</C>,{" "}
          <C>subscription_validity_end_date</C>, as above.
        </P>
      </GuideSection>

      <GuideSection
        id="rz-user-subscriptions"
        title="User Subscriptions"
        method="GET"
        path={`${base}/{phone_number}/subscriptions`}
      >
        <P>Every subscription a phone number holds, newest first, each with its collections — for support and history.</P>
        <RefTable
          head={["Field", "Notes"]}
          rows={[
            ["id", "The subscription ID"],
            ["name, email, phone_number", ""],
            ["amount", "Paise"],
            ["frequency, state", ""],
            ["next_payment_date", "Epoch milliseconds — not the YYYY-MM-DD of the Status calls"],
            ["total_payments", "Successful collections so far (the authorisation payment is not counted)"],
            ["created_at", "ISO 8601"],
            ["txns", "Collections: id, amount, state (NOTIFIED · INITIATED · SUCCESS · FAILED), razorpay_payment_id, created_at"],
          ]}
        />
        <Note tone="warn">
          An unknown number returns <C>404 No subscriptions found</C> here, where PhonePe returns an empty list.
        </Note>
        <CodeBlock>{`curl "${base}/9876543210/subscriptions" \\
  -H "Authorization: Bearer YOUR_API_KEY"`}</CodeBlock>
      </GuideSection>

      <GuideSection id="rz-billing" title="How AutoRev collects">
        <P>Nothing here needs a call from you; it explains what Status will show.</P>
        <List size="sm" spacing={6}>
          <List.Item>
            <strong>A day early.</strong> An <C>ACTIVE</C> subscription is charged the day before its due date. Razorpay sends the
            customer the pre-debit notice and debits about 25 hours later; a UPI payment can take 24–36 hours to confirm (
            <Ext href={RZP_DOCS.subsequent}>Razorpay docs</Ext>).
          </List.Item>
          <List.Item>
            <strong>One at a time.</strong> A cycle is never charged while an earlier charge for it is still settling, and never
            twice once paid.
          </List.Item>
          <List.Item>
            <strong>On success</strong> <C>next_payment_date</C> moves one cycle on from the due date (so collecting early never
            drifts the schedule) and the paid-until date moves with it.
          </List.Item>
          <List.Item>
            <strong>On failure</strong> AutoRev tries again a day later, up to <strong>3 attempts</strong> per cycle. After the
            third the subscription is <C>HALTED</C>: no more attempts, and access ends on the unpaid due date. The customer
            subscribes again with a new Setup.
          </List.Item>
          <List.Item>
            <strong>Lost webhooks</strong> are covered: charges still unsettled after 6 hours are checked with Razorpay directly.
          </List.Item>
        </List>
      </GuideSection>

      <GuideSection id="rz-webhook" title="Webhook" method="POST" path={webhookUrl}>
        <P>
          Called by Razorpay, not by you. AutoRev checks <C>X-Razorpay-Signature</C> (HMAC-SHA256 of the raw body with the
          webhook secret from Settings) and applies these events (<Ext href={RZP_DOCS.webhooks}>Razorpay docs</Ext>):
        </P>
        <RefTable
          head={["Event", "Effect in AutoRev"]}
          rows={[
            ["payment.authorized, order.paid, payment.captured", "Authorisation order: the subscription becomes ACTIVE. Collection: SUCCESS, and the cycle moves on"],
            ["payment.failed", "That collection attempt FAILED; AutoRev retries the next day"],
            ["token.confirmed", "Activates a subscription still waiting for authorisation"],
            ["token.rejected", "The bank rejected the mandate: subscription FAILED"],
            ["token.cancelled", "Cancelled by the customer, their bank, or Revoke: subscription CANCELLED"],
          ]}
        />
        <P muted>
          Every event is safe to receive twice. Without a webhook secret in Settings the endpoint answers <C>400</C>; with a
          wrong signature, <C>401</C>.
        </P>
      </GuideSection>

      <GuideSection id="rz-revoke" title="Revoke" method="POST" path={`${base}/revoke/{subscription_id}`}>
        <P>
          Cancels the mandate at Razorpay. No body. Nothing more is collected and there is no un-revoke; the customer keeps
          access until <C>subscription_validity_end_date</C>.
        </P>
        <CodeBlock>{`curl -X POST "${base}/revoke/<subscription_id>" \\
  -H "Authorization: Bearer YOUR_API_KEY"`}</CodeBlock>
        <CodeBlock label="response">{`{"subscription_id": "3f9a21c0e4b0c9e1d2a77c0f", "state": "CANCELLED"}`}</CodeBlock>
        <RefTable
          head={["Response", "Meaning"]}
          rows={[
            ["404 Subscription not found", "Unknown ID, or it belongs to another app"],
            ["409 Subscription is already CANCELLED/FAILED", "Nothing to cancel"],
            ["502 Razorpay error", "Razorpay refused or was unreachable; nothing changed"],
          ]}
        />
        <P muted>
          A customer can also cancel from their UPI app; the <C>token.cancelled</C> webhook marks the subscription{" "}
          <C>CANCELLED</C> the same way.
        </P>
      </GuideSection>

      <GuideSection id="rz-example" title={`Example: ${app.name} backend`}>
        <P>
          The whole server side, in Python (FastAPI + requests). The price comes from your configuration, never from the
          request. If your users sign in without a phone number, ask for one when they subscribe — Razorpay needs it.
        </P>
        <CodeBlock label="python">{`import os
from datetime import date
import requests
from fastapi import APIRouter, Depends, HTTPException

AUTOREV = "${base}"
HEADERS = {"Authorization": f"Bearer {os.environ['AUTOREV_API_KEY']}"}
PRICE_PAISE = int(os.environ["PREMIUM_PRICE_PAISE"])      # e.g. 9900
RAZORPAY_KEY_ID = os.environ["RAZORPAY_KEY_ID"]           # same account as in AutoRev

router = APIRouter(prefix="/api/billing")

@router.post("/subscribe")
def subscribe(body: SubscribeRequest, user=Depends(current_user)):
    r = requests.post(f"{AUTOREV}/setup", headers=HEADERS, timeout=30, json={
        "name": user.name, "email": user.email, "phone_number": body.phone_number,
        "amount": PRICE_PAISE, "max_amount": PRICE_PAISE * 3,
        "frequency": "MONTHLY", "method": "upi",
    })
    if not r.ok:
        raise HTTPException(502, r.json().get("detail", "Could not start the subscription"))
    setup = r.json()
    save_subscription_id(user, setup["subscription_id"])
    # everything the browser needs to open Checkout
    return {"key": RAZORPAY_KEY_ID, "customer_id": setup["razorpay_customer_id"],
            "order_id": setup["razorpay_order_id"], "subscription_id": setup["subscription_id"]}

@router.get("/status")
def status(user=Depends(current_user)):
    sub_id = subscription_id_of(user)
    if not sub_id:
        return {"premium": False}
    r = requests.get(f"{AUTOREV}/status/{sub_id}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    s = r.json()
    until = s["subscription_validity_end_date"]
    return {"premium": bool(until) and date.fromisoformat(until) >= date.today(),
            "state": s["state"], "paid_until": until}`}</CodeBlock>
        <P muted>
          <C>SubscribeRequest</C>, <C>current_user</C> and the two storage helpers are your app's own. Keep{" "}
          <C>AUTOREV_API_KEY</C> on the server only. That is the whole integration: no collection job on your side.
        </P>
      </GuideSection>

      <GuideSection id="rz-errors" title="Errors">
        <P>
          Every error is JSON: <C>{`{"detail": "<message>"}`}</C>.
        </P>
        <RefTable
          head={["Status", "Meaning", "Retry?"]}
          rows={[
            ["400", "Validation failed, amount above max_amount, or Razorpay credentials not configured", "No — fix the request or Settings"],
            ["401", "Missing or wrong API key", "No"],
            ["404", "No such app or subscription under this app", "No"],
            ["409", "Already cancelled", "No"],
            ["410", "notify-redemption / execute-redemption: AutoRev collects now", "No"],
            ["422", "Body failed schema validation; the message names the field", "No"],
            ["500", "Unexpected failure; nothing was created", "Yes"],
            ["502", "Razorpay rejected the call or was unreachable; the message is Razorpay's", "Yes, with backoff"],
          ]}
        />
      </GuideSection>
    </Stack>
  );
}
