# Plan: Razorpay and PhonePe subscriptions

Status: proposed (2026-11-03). Nothing in this document is built yet.

## Context

Each app in AppJs Studio (e.g. Restyle, slug `restyle-ai`) has end users who sign in, pay credits per
generation and get credits from **subscription plans** (see [PLAN.md](PLAN.md), "App users, credits and
subscriptions"). Today an admin gives a plan by hand (`subscriptions.provider = "manual"`); the apps show
prices but can't take payment.

Already in place:
- **App settings → Payments** in the console stores, per app, the gateway (`none | razorpay | phonepe`),
  the mode (`test | live`) and the gateway's public id (Razorpay Key ID, PhonePe Merchant ID).
- `GET /v1/app` tells the app `payments: {provider, mode, razorpay_key_id}`.
- Plans (`plans` table: price in paise, billing period, credits per month), subscriptions, and the credit
  ledger with idempotent grants (`BillingService.grant_subscription`, `grant_due_credits`).
- A placeholder `PaymentProvider` protocol in `studio/endusers/billing.py`.

This plan adds real payments through **Razorpay** or **PhonePe**, chosen per app.

### The design point that shapes everything

The two gateways renew subscriptions differently:

- **Razorpay is gateway-driven.** Razorpay Subscriptions charge the user every cycle themselves and
  report each charge by webhook.
- **PhonePe is merchant-driven.** PhonePe subscriptions are UPI Autopay mandates: each cycle, *our server*
  sends the pre-debit notice and then triggers the charge.

So there is one interface with two quite different implementations, and a renewal job of our own for
PhonePe.

## 0. Before writing code

1. **Google Play's billing rules.** If the app ships on the Play Store, subscriptions to digital content
   must go through Play Billing. In India, Google's *user choice billing* and *alternative billing*
   programs allow another gateway, but they require enrollment, the matching Play Billing Library APIs,
   and a (reduced) service fee to Google. This decides whether Razorpay/PhonePe is the only payment method,
   an extra option next to Play Billing, or only for web/direct installs. **Decide this first.**
2. **Gateway products.** Razorpay **Subscriptions** must be enabled on the Razorpay account. PhonePe
   **Autopay** (subscriptions) needs approval from PhonePe's business team.
3. **PhonePe API version.** The current PhonePe PG API (v2) uses OAuth credentials (client id, client
   secret, client version); the older v1 used a salt key with an `X-VERIFY` checksum. Build against the
   credentials your PhonePe dashboard actually issues, and check request/response shapes against PhonePe's
   current documentation when implementing.

## 1. Backend (`appjs-studio`)

### Provider interface

`PaymentProvider` (`studio/endusers/billing.py`), one implementation per gateway:

| Method | Does |
|---|---|
| `ensure_plan(plan, mode)` | Create or find the gateway's plan for one of our plans |
| `start_subscription(user, plan)` | Create the subscription with the gateway; return what the app needs to open checkout |
| `confirm(order, payload)` | Check the app's success callback (signature, or a status fetch) |
| `handle_webhook(headers, raw_body)` | Verify, record and apply a gateway event |
| `cancel(subscription, at_period_end)` | Cancel with the gateway |
| `renew_due(now)` | PhonePe only: notify and charge subscriptions that are due |

### Data (migration 0007)

| Table | Purpose |
|---|---|
| `app_payment_secrets` | Per-app secrets: Razorpay key secret and webhook secret; PhonePe client id, secret, version and webhook credentials. **Encrypted with Fernet** using a `PAYMENTS_ENCRYPTION_KEY` env var (the `cryptography` package is already installed). The console can set and replace them, never read them back. |
| `payment_orders` | One row per checkout attempt: app, user, plan, provider, mode, the gateway's ids, amount, status (`created → authorized → active / failed / expired`). |
| `payment_events` | Raw webhook log, unique on `(provider, event_id)` so a repeated delivery is applied once: payload, signature valid or not, processed at, error. |
| `plans.external_ids` (exists) | The gateway's plan id per mode, e.g. `{"razorpay": {"test": "plan_…"}}`. |
| `subscriptions` (exists) | New statuses `pending` and `halted`; `provider` and `provider_ref` already exist. |

### Endpoints

| Endpoint | Who | Does |
|---|---|---|
| `POST /v1/app/subscriptions {plan_id}` | signed-in app user | Create the gateway subscription; return checkout details |
| `POST /v1/app/subscriptions/{order_id}/confirm` | signed-in app user | Check the checkout result; activate and grant credits |
| `POST /v1/app/subscriptions/current/cancel` | signed-in app user | Cancel at the end of the paid period |
| `POST /v1/webhooks/razorpay/{app_slug}` | Razorpay | Verify the signature on the raw body, record, apply |
| `POST /v1/webhooks/phonepe/{app_slug}` | PhonePe | Verify the authorization header, record, apply |
| `POST /v1/admin/apps/{app_id}/payments/test` | admin | "Test connection": authenticate against the gateway |

### Credits

A successful first payment calls the existing `grant_subscription` (starts the subscription and grants the
first month). Each renewal calls a new `renew(subscription, paid_until)` that extends
`current_period_end`. Monthly grants keep working unchanged, so a yearly plan is charged once and still
grants credits monthly. All grants stay idempotent through the ledger's unique keys.

## 2. Razorpay flow

1. **Plan sync.** On the first purchase of a plan in a mode, create the Razorpay plan (period `monthly` or
   `yearly`, interval 1, amount in paise) and store its id in `plans.external_ids`. Razorpay plans can't be
   edited: a price change creates a new Razorpay plan, and existing subscribers keep their price.
2. **Purchase.** The server creates a Razorpay subscription (`plan_id`, a long `total_count`, our ids in
   `notes`) and returns `{provider: "razorpay", key_id, subscription_id, order_id}`. The app opens Razorpay
   Checkout with `subscription_id`; the user authorizes a UPI Autopay mandate or a card.
3. **Confirm.** The app sends `razorpay_payment_id`, `razorpay_subscription_id` and `razorpay_signature`.
   The server checks `HMAC-SHA256(payment_id + "|" + subscription_id, key_secret)`. If it matches, the
   subscription is activated and month 1 is granted.
4. **Webhooks are the source of truth** (the app may die mid-checkout). The signature is in
   `X-Razorpay-Signature`: HMAC-SHA256 of the raw body with the webhook secret.

   | Event | Action |
   |---|---|
   | `subscription.activated`, `subscription.charged` | Activate or renew; grant credits |
   | `subscription.halted` | Mark `halted`; keep access until the paid period ends |
   | `subscription.cancelled`, `subscription.completed` | Stop at the end of the paid period |
   | `payment.failed` | Record it |

## 3. PhonePe flow (Autopay)

1. **Setup.** The server calls PhonePe's subscription setup (amount, frequency, maximum amount) and gets a
   token. The app opens the PhonePe PG SDK (or a UPI intent); the user approves the mandate in their UPI
   app.
2. **Activation** comes from the webhook, backed up by polling the order status. Whether the first payment
   is taken at setup or as a separate charge must be confirmed against PhonePe's current documentation.
3. **Renewals are ours.** A worker sweep, next to `grant_due_credits`, finds subscriptions coming due,
   sends the pre-debit notice ahead of time (UPI rules require advance notice, at least a day), then
   triggers the charge on the due date. Failures retry a limited number of times; after that the
   subscription is `halted`.
4. **Webhooks** are checked with PhonePe's authorization header; a reconciliation job polls anything left
   pending. PhonePe Autopay is UPI only (no cards).

## 4. Android (Restyle)

- Add `com.razorpay:checkout` and the PhonePe PG SDK; pick one from `payments.provider` in `GET /v1/app`
  (already returned).
- **Subscribe screen:** create subscription → open the SDK → confirm → poll `/v1/app/me` until the plan is
  active → show the new credits. Cancel or failure shows a clear message; nothing is charged. With
  `provider = none`, keep today's "Payments are coming soon".
- **Profile:** plan, renewal date and **Cancel subscription**.

## 5. Console (App settings → Payments)

- Write-only secret fields showing "set / not set", with Replace.
- The webhook URL to paste into each gateway's dashboard, with a copy button.
- **Test connection.**
- Each plan's sync status with the gateway (Razorpay plan id per mode).
- Users drawer: the gateway subscription id and payment history.
- A **go-live checklist** before switching to Live: live keys, live webhook set up, one real low-value
  payment end to end.

## 6. Security and correctness

- Never trust the app's success callback alone: check its signature or fetch the status from the gateway.
- Amounts and plans come only from the server.
- Webhooks are deduplicated by event id; every credit grant is idempotent (ledger keys).
- Secrets are encrypted at rest and never logged or returned by the API.
- Webhooks need a **public HTTPS URL**. For local development, use a tunnel (cloudflared or ngrok) to the
  Docker stack; in production the API sits behind HTTPS.
- Decide refund handling and GST invoices (Razorpay can help with invoices).

## 7. Phases

| Phase | Scope |
|---|---|
| **P0** | Play billing decision; Razorpay Subscriptions and PhonePe Autopay enabled on the accounts |
| **P1** | Backend foundation (encrypted secrets, orders, events, webhook endpoints, provider interface) and **Razorpay end to end in test mode**, including Android checkout |
| **P2** | PhonePe Autopay: setup, renewal sweep, status reconciliation |
| **P3** | Operations: reconciliation job, admin payment views, cancellations and refunds, going live |

## 8. Testing

- **Backend:** replay recorded webhook payloads with real signatures; mock gateway APIs with `respx`;
  test duplicate deliveries, out-of-order events, failed and halted renewals, and cancel at period end.
- **Razorpay test mode:** test cards, and `success@razorpay` / `failure@razorpay` as test UPI ids.
- **PhonePe UAT sandbox.**
- **End to end:** webhooks through a tunnel into the local Docker stack; checkout on the Android emulator.

## 9. Open decisions

1. Play Store route: user choice billing, alternative billing only, or not on Play for now?
2. Is Razorpay Subscriptions enabled? Has PhonePe approved Autopay, and which credentials (API version)
   were issued?
3. Add one-time **credit packs** next to subscriptions? (Simpler: an order and a one-time payment.)
4. Cancellation: stop at the end of the paid period (recommended), or immediately with a pro-rata refund?
