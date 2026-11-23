import { Anchor, Stack } from "@mantine/core";
import type { App } from "../../../api/types";
import { C, CodeBlock, GuideSection, Note, P, Params, RefTable, Toc } from "./parts";

const NAV: [string, string][] = [
  ["how-it-works", "How billing works"],
  ["auth", "Authentication"],
  ["setup", "Setup"],
  ["status", "Subscription Status"],
  ["user-status", "User Status"],
  ["user-subscriptions", "User Subscriptions"],
  ["invoices", "Invoices"],
  ["revoke", "Revoke"],
  ["report", "Report"],
  ["errors", "Errors"],
];

/** Shared by both gateways: the same app ID and API key authenticate every call. */
export function AuthSection({ id }: { id: string }) {
  return (
    <GuideSection id={id} title="Authentication">
      <P>
        Every request carries this app's ID in the path and your API key as a bearer token. Both are on the Settings page
        under App Credentials.
      </P>
      <CodeBlock label="headers">{`Authorization: Bearer YOUR_API_KEY
Content-Type: application/json`}</CodeBlock>
      <P>
        The key authorises creating and cancelling mandates on your merchant account. Keep it server-side — never in an app
        binary or a browser bundle. If it leaks, reset it from Settings; the old key stops working immediately, so deploy the
        new one first.
      </P>
      <P muted>
        App ID and key are checked together. A subscription belonging to another app is reported as{" "}
        <C>404 Subscription not found</C>, never exposed.
      </P>
    </GuideSection>
  );
}

export function PhonePeGuide({ app, apiBase }: { app: App; apiBase: string }) {
  const base = `${apiBase}/api/v1/${app.id}/phonepay`;
  return (
    <Stack gap="lg">
      <P>
        Everything your server needs to put <strong>{app.name}</strong> customers on a PhonePe subscription. The URLs below
        already carry this app's ID — copy them as they are.
      </P>
      <Toc items={NAV} />

      <GuideSection id="how-it-works" title="How billing works">
        <P>You create a subscription. AutoRev collects every payment on it after that.</P>
        <Note>
          There is no "charge now" call. Notifying the payer, collecting on the due date, retrying a failure and advancing to
          the next cycle all run inside AutoRev on a schedule. To find out what happened, use webhooks or poll the status
          endpoint.
        </Note>
        <P>
          A subscription moves <C>INITIATED</C> → <C>ACTIVE</C> once the payer approves the UPI mandate, and stays there until
          it is paused or revoked. Any state ending in <C>_IN_PROGRESS</C> means PhonePe is still settling a change — read it
          again shortly rather than treating it as final.
        </P>
        <P>
          Two conventions apply everywhere: <strong>money is paise</strong> as an integer (<C>4900</C> is ₹49.00), and{" "}
          <strong>dates are IST</strong>.
        </P>
      </GuideSection>

      <AuthSection id="auth" />

      <GuideSection id="setup" title="Setup" method="POST" path={`${base}/setup`}>
        <P>
          Creates the mandate and returns the PhonePe intent for the payer to approve. The subscription stays{" "}
          <C>INITIATED</C> until they do.
        </P>
        <Params
          rows={[
            { name: "phone_number", type: "string", required: true, notes: "Exactly 10 digits, no country code" },
            { name: "max_amount", type: "int (paise)", required: true, notes: "Ceiling the payer authorises per debit. Must be > 0" },
            { name: "amount", type: "int (paise)", required: false, def: "app trial amount", notes: "Charged at setup. Required unless the app has a trial amount configured" },
            { name: "frequency", type: "enum", required: false, def: "ON_DEMAND", notes: "DAILY · WEEKLY · FORTNIGHTLY · MONTHLY · BIMONTHLY · QUARTERLY · HALFYEARLY · YEARLY · ON_DEMAND" },
            { name: "amount_type", type: "enum", required: false, def: "VARIABLE", notes: "FIXED or VARIABLE" },
            { name: "trail_days", type: "int", required: false, def: "app trial period, else 0", notes: "Free-trial length. First recurring debit lands this many days after setup" },
            { name: "auth_workflow_type", type: "enum", required: false, def: "TRANSACTION", notes: "TRANSACTION or PENNY_DROP" },
            { name: "product_type", type: "enum", required: false, def: "UPI_INTENT", notes: "UPI_INTENT or UPI_MANDATE" },
            { name: "device_os", type: "enum", required: false, def: "Android", notes: "Android or iOS. Used only for UPI_INTENT" },
            { name: "payment_target_app", type: "string", required: false, def: "null", notes: "Open a specific UPI app for the intent" },
          ]}
        />
        <Note tone="warn" title="Two things that are hard to undo">
          Set <C>max_amount</C> to the most you could ever charge in one debit, not today's price — raising it later needs a
          brand-new mandate and a fresh approval. And <C>ON_DEMAND</C>, the default <C>frequency</C>, has no schedule, so
          nothing is ever collected automatically. Pass a real frequency for recurring billing.
        </Note>
        <CodeBlock>{`curl -X POST \\
  "${base}/setup" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
  "phone_number": "9876543210",
  "amount": 4900,
  "max_amount": 49900,
  "amount_type": "VARIABLE",
  "frequency": "MONTHLY",
  "trail_days": 7
}'`}</CodeBlock>
        <P>
          The response is PhonePe's, plus the <C>subscription_id</C> AutoRev assigned — a 24-character hex string you cannot
          choose. Send the payer to the intent URL it carries.
        </P>
        <P muted>
          The setup order expires <strong>10 minutes</strong> after creation. If the payer does not act, start a new setup
          rather than retrying the old subscription ID.
        </P>
      </GuideSection>

      <GuideSection id="status" title="Subscription Status" method="GET" path={`${base}/status/{subscription_id}`}>
        <P>Reads the mandate live from PhonePe, saves the result, and returns PhonePe's response. No query parameters.</P>
        <P>
          Poll this after setup to find out whether the payer approved. It is also what promotes an approved mandate to{" "}
          <C>ACTIVE</C> and computes its first payment date, so polling does real work rather than just reporting.
        </P>
        <CodeBlock>{`curl "${base}/status/<subscription_id>" \\
  -H "Authorization: Bearer YOUR_API_KEY"`}</CodeBlock>
        <P muted>
          Returns <C>404</C> if the subscription is not yours, <C>502</C> if PhonePe is unreachable. Polling suits the setup
          window; for the recurring life of a mandate, webhooks cost less than a poll loop.
        </P>
      </GuideSection>

      <GuideSection id="user-status" title="User Status" method="GET" path={`${base}/{phone_number}/status`}>
        <P>
          The single best call for "is this customer subscribed?". Takes a 10-digit number and no query parameters. Where a
          number holds several subscriptions it picks one, preferring <C>ACTIVE</C>, then mid-setup, then <C>PAUSED</C>/
          <C>REVOKED</C>. An unknown number returns <C>{`{"state": "NOT_FOUND"}`}</C>.
        </P>
        <RefTable
          head={["Field", "Notes"]}
          rows={[
            ["state", "Subscription state, or NOT_FOUND"],
            ["subscription_id", ""],
            ["subscription_start_date", "First billing date — setup date plus trail_days"],
            ["subscription_validity_end_date", "Paid up to, including a 6-day grace period"],
            ["subscription_frequency", ""],
            ["next_payment_date", "YYYY-MM-DD, or null for ON_DEMAND"],
            ["last_payment_status", "COMPLETED, FAILED, PENDING, or null"],
            ["number_of_successful_payments", ""],
            ["payment_amount", "The mandate's max_amount, in paise"],
            ["trail_amount", "Trial charge, or null when there is no trial"],
            ["trail_status", "ACTIVE or EXPIRED during a trial, else null"],
          ]}
        />
        <Note>
          To gate access, read <C>subscription_validity_end_date</C>, not <C>state</C>. A mandate can be <C>REVOKED</C> while
          the customer is still inside a period they already paid for — cutting them off on state alone takes away time they
          bought.
        </Note>
        <CodeBlock>{`curl "${base}/9876543210/status" \\
  -H "Authorization: Bearer YOUR_API_KEY"`}</CodeBlock>
        <P muted>
          This answers for one subscription. For every subscription a number holds, see{" "}
          <Anchor href="#user-subscriptions">User Subscriptions</Anchor>; for what they have actually paid, see{" "}
          <Anchor href="#invoices">Invoices</Anchor>.
        </P>
      </GuideSection>

      <GuideSection id="user-subscriptions" title="User Subscriptions" method="GET" path={`${base}/{phone_number}/subscriptions`}>
        <P>
          Every subscription a phone number holds, newest first, each with its collection attempts. No query parameters. Use
          this when one answer is not enough — a customer who resubscribed, or a support question about which mandate is
          charging them.
        </P>
        <RefTable
          head={["Field", "Notes"]}
          rows={[
            ["id", "The subscription ID"],
            ["phone_number", ""],
            ["amount", "Paise"],
            ["frequency", ""],
            ["state", ""],
            ["next_payment_date", "Epoch milliseconds — not the YYYY-MM-DD used elsewhere"],
            ["total_payments", "Successful collections so far"],
            ["created_at", "ISO 8601"],
            ["txns", "Array of attempts: id, amount, state, transaction_id, created_at"],
          ]}
        />
        <Note tone="warn">
          <C>next_payment_date</C> is <strong>epoch milliseconds</strong> here, while User Status returns the same field as{" "}
          <C>YYYY-MM-DD</C>. Parsing one as the other is the easiest mistake to make against this API.
        </Note>
        <CodeBlock>{`curl "${base}/9876543210/subscriptions" \\
  -H "Authorization: Bearer YOUR_API_KEY"`}</CodeBlock>
        <P muted>
          An unknown number returns an empty <C>subscriptions</C> array, not a 404.
        </P>
      </GuideSection>

      <GuideSection id="invoices" title="Invoices" method="GET" path={`${base}/{phone_number}/invoices`}>
        <P>
          Every payment a number has actually made, oldest first, across all of its subscriptions. No query parameters. This
          is the billing history to show a customer or reconcile against.
        </P>
        <RefTable
          head={["Field", "Notes"]}
          rows={[
            ["invoice_id", "First 5 characters of the subscription ID plus a per-subscription sequence number"],
            ["phone_number", ""],
            ["subscription_id", "Which mandate this payment belongs to"],
            ["transaction_id", "PhonePe's transaction ID; for a setup charge, the subscription ID"],
            ["invoice_date", "Scheduled date of the payment (YYYY-MM-DD)"],
            ["payment_date", "When it actually settled (YYYY-MM-DD)"],
            ["amount", "Paise"],
            ["type", "SETUP for the charge taken at signup, RECURRING after"],
          ]}
        />
        <P>
          The response wraps them: <C>{`{"phone_number", "count", "invoices": [...]}`}</C>.
        </P>
        <Note>
          The <C>SETUP</C> row is money collected at signup, which never becomes a transaction of its own — so its{" "}
          <C>transaction_id</C> is the subscription ID rather than a PhonePe transaction. Counting only <C>RECURRING</C> rows
          undercounts what the customer paid by one.
        </Note>
        <CodeBlock>{`curl "${base}/9876543210/invoices" \\
  -H "Authorization: Bearer YOUR_API_KEY"`}</CodeBlock>
        <P muted>
          An unknown number returns <C>count: 0</C> and an empty array.
        </P>
      </GuideSection>

      <GuideSection id="revoke" title="Revoke" method="POST" path={`${base}/revoke/{subscription_id}`}>
        <P>Cancels the mandate at PhonePe. No body, no query parameters.</P>
        <CodeBlock>{`curl -X POST \\
  "${base}/revoke/<subscription_id>" \\
  -H "Authorization: Bearer YOUR_API_KEY"`}</CodeBlock>
        <CodeBlock label="response">{`{"subscription_id": "b3f1c8d9e4a24f7b8c1d2e3f4a5b6c7d", "state": "REVOKED"}`}</CodeBlock>
        <P>
          The <C>state</C> is whatever PhonePe reports, not an assumption. A cancellation can land on{" "}
          <C>REVOKE_IN_PROGRESS</C> and settle to <C>REVOKED</C> minutes later, so wait for the <C>subscription.revoked</C>{" "}
          webhook or re-read the status before telling the customer it is done.
        </P>
        <Note tone="warn">
          This is terminal. Nothing further is collected and there is no un-revoke — the customer has to go through setup
          again.
        </Note>
        <RefTable
          head={["Response", "Meaning"]}
          rows={[
            ["404 Subscription not found", "Unknown ID, or it belongs to another app"],
            ["409 Subscription is already CANCELLED/REVOKED", "Checked before calling PhonePe, so a repeat is cheap"],
            ["409 PhonePe rejected the cancellation", "PhonePe disagrees about the mandate's state"],
            ["502 PhonePe error", "PhonePe unreachable; nothing changed"],
          ]}
        />
      </GuideSection>

      <GuideSection id="report" title="Report" method="GET" path={`${base}/report`}>
        <P>
          Counts of subscriptions created and transactions recorded in a time window, grouped by state. Useful for a daily
          reconciliation job or a health dashboard.
        </P>
        <Params
          rows={[
            { name: "start", type: "ISO datetime (IST)", required: false, def: "one hour before end", notes: "Inclusive" },
            { name: "end", type: "ISO datetime (IST)", required: false, def: "now", notes: "Exclusive" },
          ]}
        />
        <CodeBlock>{`# default window: the last hour
curl "${base}/report" \\
  -H "Authorization: Bearer YOUR_API_KEY"

# an explicit day, IST
curl "${base}/report?start=2026-10-15T00:00:00&end=2026-10-16T00:00:00" \\
  -H "Authorization: Bearer YOUR_API_KEY"`}</CodeBlock>
        <CodeBlock label="response">{`{
  "window_start": "2026-10-15T00:00:00+05:30",
  "window_end":   "2026-10-16T00:00:00+05:30",
  "app_id": "${app.id}",
  "subscriptions_created": { "total": 240, "by_state": { "ACTIVE": 180, "FAILED": 60 } },
  "transactions":          { "total": 310, "by_state": { "COMPLETED": 290, "FAILED": 20 } }
}`}</CodeBlock>
        <Note>
          Both figures are windowed on <strong>creation</strong> time, and each row is reported in whatever state it holds
          right now. A transaction created inside the window but settled after it still appears under this window. So a
          one-hour report shows almost no <C>COMPLETED</C> — PhonePe requires 24 hours' notice before a debit, so nothing
          created in the last hour can have collected yet. Compare days, not minutes.
        </Note>
      </GuideSection>

      <GuideSection id="errors" title="Errors">
        <P>
          Every error is JSON: <C>{`{"detail": "<message>"}`}</C>.
        </P>
        <RefTable
          head={["Status", "Meaning", "Retry?"]}
          rows={[
            ["400", "Validation failed or a required value is missing", "No — fix the request"],
            ["401", "Missing or wrong API key", "No"],
            ["404", "No such app, subscription or order under this app", "No"],
            ["409", "Conflicts with current state, e.g. already revoked", "No — re-read first"],
            ["410", "Endpoint withdrawn", "No"],
            ["422", "Body failed schema validation; the message names the field", "No"],
            ["500", "Unexpected failure; nothing was created", "Yes"],
            ["502", "PhonePe errored or was unreachable", "Yes, with backoff"],
          ]}
        />
        <Note tone="warn">
          A setup call that returns <C>502</C> may still have created a mandate at PhonePe. Check{" "}
          <C>{"GET /{phone_number}/subscriptions"}</C> before retrying, or the customer can end up with two.
        </Note>
      </GuideSection>
    </Stack>
  );
}
