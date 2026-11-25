# Plan: subscriptions through autorev

Status: P1 and P2 built for Razorpay (2026-11-26): autorev's events and `external_ref`, Studio's checkout,
webhook receiver and console settings, and restyle-web's checkout. PhonePe (P3) and operations (P4) are
still to do. This replaces the
2026-11-03 plan, which had Studio call Razorpay and PhonePe directly.

## Context

Each app in AppJs Studio (e.g. Restyle, slug `restyle-ai`) has end users who sign in, pay credits per
generation and get credits from **subscription plans** (see [PLAN.md](PLAN.md), "App users, credits and
subscriptions"). Today an admin gives a plan by hand (`subscriptions.provider = "manual"`). The apps show
prices but can't take payment.

Already in Studio:
- **App settings → Payments** stores, per app, the gateway (`none | razorpay | phonepe`), the mode
  (`test | live`) and the gateway's public id (`razorpay_key_id`, `phonepe_merchant_id`; migration 0006).
- `GET /v1/app` tells the app `payments: {provider, mode, razorpay_key_id}`.
- Plans (price in paise, billing period, credits per month, optional trial), subscriptions, and the
  credit ledger with idempotent grants (`BillingService.grant_subscription`, `grant_due_credits`).
- A placeholder `PaymentProvider` protocol in `studio/endusers/billing.py`.
- Encrypted per-app secrets (the `box` used for provider keys, migration 0008).

## The decision: autorev is the payment engine

`../autorev` (same repo, separate service) already does the hard part for both gateways:

| | PhonePe | Razorpay |
|---|---|---|
| Mandate setup | `POST /api/v1/{app_id}/phonepay/setup` (UPI Autopay) | `POST /api/v1/{app_id}/razorpay/setup` (customer + token order: UPI, e-mandate or card) |
| Status | `GET …/phonepay/status/{subscription_id}` | `GET …/razorpay/status/{subscription_id}` |
| Cancel | `POST …/phonepay/revoke/{subscription_id}` | `POST …/razorpay/revoke/{subscription_id}` |
| Each cycle | Celery workers send the pre-debit notice and charge | Celery `razorpay-collect-due` charges the saved token; Razorpay sends the notice |
| Tells us | signed outbound webhooks with retries | **nothing yet** (gap, below) |

Calls authenticate with `Authorization: Bearer <autorev app api_key>`. Webhooks carry
`X-Autorev-Event`, `X-Autorev-Delivery`, `X-Autorev-Timestamp` and
`X-Autorev-Signature: sha256=<HMAC-SHA256 of the raw body with the signing secret>`. The body is
`{event, delivery_id, app_id, app_name, created_at, data: <subscription>}`.

So Studio never holds gateway secrets, never talks to Razorpay or PhonePe, and runs no renewal job. It
starts a checkout through autorev, and turns autorev's webhooks into subscription and credit changes.
Studio and autorev share no code: HTTP one way, webhooks the other (see `../CLAUDE.md`).

```
app ──POST /v1/app/subscriptions──▶ Studio ──POST /{app}/razorpay|phonepay/setup──▶ autorev ──▶ gateway
app ◀── checkout details ────────── Studio ◀── order / intent ─────────────────────── autorev
app ── opens Razorpay Checkout / PhonePe SDK, user approves the mandate ────────────────────▶ gateway
                                    Studio ◀── webhook subscription.activated ─────── autorev ◀── gateway
                                    (grant month 1)
                every cycle:        Studio ◀── webhook subscription.next_payment_updated ── autorev charges
```

## 0. Before writing code

1. **Google Play billing.** If Restyle ships on the Play Store, subscriptions to digital content must go
   through Play Billing. In India, *user choice billing* and *alternative billing* allow another
   gateway, but need enrollment, the matching Play Billing Library APIs and a reduced service fee to
   Google. This decides whether Razorpay/PhonePe is the only method, an extra option, or for web and
   direct installs only. **Decide this first.**
2. **Gateway accounts.** Razorpay recurring payments (tokens / UPI Autopay) enabled; PhonePe Autopay
   approved by PhonePe's business team. Both are configured in autorev, not Studio.
3. **Products.** Subscriptions only, or one-time **credit packs** too? A pack is a single payment with
   no mandate and could ship first.
4. **Cancellation.** Stop at the end of the paid period (recommended), or immediately with a pro-rata
   refund?

## 1. autorev changes

| Change | Why |
|---|---|
| **Razorpay sends webhooks.** Call the state and next-payment dispatch from the Razorpay paths (`app/razorpay_billing.py`, `app/router/razorpay_router.py`), as `workers/phone_worker_helper.py` does for PhonePe. Add Razorpay's states to `STATE_EVENTS` and its fields to the payload. | Today only PhonePe emits `subscription.*` events, so Studio would never hear that a Razorpay mandate was activated or charged. |
| **External reference.** Accept an optional `external_ref` (string, e.g. `studio:<app_user_id>:<plan_id>:<order_id>`) on both setup endpoints, store it, and return it in every webhook payload and status response. | Subscriptions are keyed by phone number. Studio needs to match an event to its own order without relying on the phone. |
| **Payment failures as events.** `subscription.payment_failed` per failed attempt, and `subscription.halted` when collection gives up. | Studio stops renewal at the paid-up date instead of waiting for a revoke. |
| **Razorpay-only servers.** `AUTOREV_GATEWAYS=razorpay`: no PhonePe routes or tasks. | Production runs Razorpay only for now. |
| **Turn it back on in production.** `fab deploy --with-autorev`, live gateway keys in autorev's console, gateway webhooks pointed at `AUTOREV_DOMAIN`. | autorev is switched off in production today. |

Each change gets autorev tests; this is money movement (`../CLAUDE.md`: never call live gateways from
tests, and don't change idempotency, signatures or retries without a test).

## 2. Studio backend

### Settings and secrets

Per app, next to the existing Payments settings:
- `autorev_app_id` (plain) and `autorev_api_key` + `autorev_webhook_secret` (encrypted with `box`,
  write-only like provider keys). The base URL is one server setting, `AUTOREV_URL`
  (`http://autorev-backend:8000` on the Docker network `appjs`).
- `payment_provider` keeps choosing the gateway; it now selects which autorev setup route to call.
- `razorpay_key_id` stays: Razorpay Checkout needs it on the device.

### Data (one migration)

| Table | Purpose |
|---|---|
| `payment_orders` | One row per checkout attempt: app, user, plan, gateway, mode, amount (from the plan), autorev subscription id, the `external_ref` sent, status `created → pending → active / failed / expired`. |
| `payment_events` | Every autorev webhook received: delivery id (unique, so a repeated delivery is applied once), event, payload, signature valid, processed at, error. |
| `subscriptions` (exists) | New statuses `pending` and `halted`. `provider = "autorev"`, `provider_ref` = autorev subscription id. |

### Endpoints

| Endpoint | Who | Does |
|---|---|---|
| `POST /v1/app/subscriptions {plan_id}` | signed-in app user | Create a `payment_orders` row, call autorev setup with the plan's amount, return checkout details |
| `GET /v1/app/subscriptions/{order_id}` | signed-in app user | Status for the app to poll after checkout; asks autorev when still pending |
| `POST /v1/app/subscriptions/current/cancel` | signed-in app user | Call autorev revoke; access lasts to the end of the paid period |
| `POST /v1/webhooks/autorev` | autorev | Verify `X-Autorev-Signature` on the raw body with the app's secret, reject stale timestamps, dedupe on delivery id, apply |
| `POST /v1/admin/apps/{app_id}/payments/test` | admin | "Test connection": an authenticated call to autorev |

The setup call sends what the gateway needs: Razorpay requires the user's **name, email and phone**,
PhonePe the **phone**. App users sign in with Google (email, maybe no phone) or phone OTP (phone, no
email), so checkout asks for whichever is missing and stores it on the app user.

Amounts: `amount = max_amount = plan.price` (fixed amount) and `frequency` from the plan's billing
period. Amounts and plans come only from the server, never from the app.

### Applying webhooks

| autorev event | Studio does |
|---|---|
| `subscription.activated` | Order `active`; `grant_subscription` (starts the period, grants month 1) |
| `subscription.next_payment_updated` | New `BillingService.renew(subscription, paid_until)` extends `current_period_end` |
| `subscription.payment_failed` | Subscription `halted`; access until the paid period ends |
| `subscription.paused` | Subscription `halted` |
| `subscription.revoked` | Stop at the end of the paid period |

Monthly credit grants keep working unchanged, so a yearly plan is charged once and still grants credits
monthly. All grants stay idempotent through the ledger's unique keys. Events can arrive out of order or
twice; each handler checks the subscription's current state first.

The placeholder `PaymentProvider` protocol becomes a small `AutorevClient` (setup, status, revoke) plus
the webhook handler; there is one engine, so no per-gateway classes.

## 3. Clients

`docs/APPS_API.md` changes first, then the clients (`../CLAUDE.md`).

- **restyle-web** (first, fastest to test): Razorpay Checkout JS with the returned order and
  `razorpay_key_id`; PhonePe via redirect. Then poll the order until `active` and show the new credits.
  Its nginx already forwards `/v1/app/*`.
- **restyle (Android)**: `com.razorpay:checkout` and the PhonePe PG SDK, chosen by `payments.provider`
  from `GET /v1/app`. Subscribe screen: create → checkout → poll → new credits. Profile: plan, renewal
  date, **Cancel subscription**. With `provider = none`, keep "Payments are coming soon".

## 4. Console (App settings → Payments)

- autorev connection: app id, write-only API key and webhook secret ("set / not set", Replace), and
  **Test connection**.
- The webhook URL to paste into autorev (`https://<STUDIO_DOMAIN>/api/v1/webhooks/autorev`), with a copy
  button.
- Users drawer: the autorev subscription id, orders and received events.
- A **go-live checklist** before switching to Live: live keys in autorev, live webhook set, one real
  low-value payment end to end.

## 5. Security and correctness

- Never trust the app's checkout callback alone: activation comes from autorev's webhook or status.
- Webhooks: verify the HMAC on the raw body, reject old timestamps, dedupe on delivery id.
- autorev API keys and webhook secrets are encrypted at rest and never logged or returned.
- Studio reaches autorev over the private Docker network; only autorev's gateway webhooks need the public
  `AUTOREV_DOMAIN`.
- Refunds and GST invoices: decide before going live (Razorpay can issue invoices).

## 6. Phases

| Phase | Scope |
|---|---|
| **P0** | Play billing decision; gateway products enabled in autorev's accounts |
| **P1** | autorev: Razorpay webhooks, `external_ref`, payment-failed and halted events, Razorpay-only switch (done) |
| **P2** | Studio: settings, migration, subscribe/status/cancel endpoints, webhook receiver; **Razorpay end to end in test mode** with restyle-web (done) |
| **P3** | Android checkout; PhonePe Autopay (once approved) |
| **P4** | Operations: admin payment views, reconciliation (poll autorev for orders stuck in `pending`), refunds, going live |

## 7. Testing

- **Studio:** replay signed autorev webhooks; mock autorev with `respx`; duplicate and out-of-order
  deliveries, failed and halted renewals, cancel at period end. No real gateway calls.
- **autorev:** its own tests for the new events and `external_ref`, against mocked gateways.
- **End to end in test mode:** Razorpay test cards and `success@razorpay` / `failure@razorpay`; PhonePe
  UAT sandbox. Studio and autorev both on the local Docker network; gateway webhooks into autorev
  through a tunnel (cloudflared or ngrok).
