# Razorpay Recurring Payments Flow

Razorpay has no notion of "subscriptions" here — we don't use Razorpay's
Plans/Subscriptions product. Instead we mirror PhonePe's merchant-controlled
setup → notify → execute pattern using Razorpay's Customer + tokenized-Order
primitives:

1. Create a Razorpay **Customer**.
2. Create an **authorization Order** carrying a `token` block. The customer
   authorizes it once (UPI intent/collect, e-mandate, or card) via Razorpay
   Checkout, and Razorpay returns a reusable `token_id`.
3. Every later charge is a new plain Order + `POST /payments/create/recurring`
   against that saved `token_id` — no further customer action needed.

All endpoints below live in [`app/router/razorpay_router.py`](app/router/razorpay_router.py)
under `router = APIRouter(prefix="/api/v1/{app_id}/razorpay", tags=["razorpay"])`,
and require `Authorization: Bearer <App.api_key>`.

## Data model

- `RazorpayApp` — per-app credentials (`razorpay_key_id`, `razorpay_key_secret`,
  `razorpay_webhook_secret`, `razorpay_environment`).
- `RazorpaySubscription` — one row per authorized "mandate": `razorpay_customer_id`,
  `razorpay_order_id` (the authorization order), `razorpay_token_id` (set once
  authorized), `state`, `frequency`, `next_payment_date`, `total_payments`.
- `RazorpayTransaction` — one row per individual charge attempt against a
  subscription: `razorpay_order_id` (the charge order), `razorpay_payment_id`,
  `state`.

## Flow

### 1. Setup — `POST /setup`

Creates the Razorpay customer, then an authorization order with a `token`
block sized to `max_amount`. Persists a `RazorpaySubscription` in state
`AUTHORIZATION_PENDING` and returns `razorpay_order_id` + `razorpay_customer_id`
for the client to complete via Razorpay Checkout (UPI/e-mandate/card, per
`method`).

```
curl -X POST "{base}/razorpay/setup" \
  -H "Authorization: Bearer <api_key>" -H "Content-Type: application/json" \
  -d '{"name":"Jane Doe","email":"jane@example.com","phone_number":"9876543210","amount":9900,"max_amount":50000,"frequency":"MONTHLY","method":"upi"}'
```

`name` and `email` are required: Razorpay needs the email to create every
later recurring payment, so a subscription without one could be authorised and
then never collected. `amount` must not exceed `max_amount`. For `method: upi`
the authorisation order carries `token.frequency` (mapped from `frequency`;
`ON_DEMAND` becomes `as_presented`), which Razorpay requires for UPI Autopay.

Optional `notes` (up to 12 string pairs, keys 1–40 characters, values up to 256)
label the subscription on the Razorpay dashboard, e.g.
`{"app": "restyle-ai", "app_name": "Restyle AI", "plan": "monthly"}`. They are
stored on the subscription and added to the notes of the customer, the
authorisation order and every recurring charge, next to autorev's own
`app_id`, `subscription_id` and `txn_id`, which can't be overridden
(migration `008_razorpay_notes.sql` adds the column).

### 2. Customer authorizes (client-side, outside our API)

The frontend/app completes the Razorpay Checkout flow for `razorpay_order_id`.
On success, Razorpay attaches a token to the customer.

### 3. Confirm authorization — `GET /status/{subscription_id}` (poll) or webhook (push)

- **Poll**: fetches the order; once `status == "paid"` and no token is stored
  yet, takes the token from the order's own authorisation payment
  (`GET /orders/{id}/payments`), flips the subscription to `ACTIVE`, and
  computes `next_payment_date`. Razorpay reuses a customer for the same phone
  number, so "the customer's first token" could be an old one; only when no
  payment names a token does it fall back to the customer's newest token.
- **Push**: the `order.paid` / `payment.authorized` / `payment.captured`
  webhooks (the payment carries `token_id`) and `token.confirmed` do the same
  thing automatically — no client poll required if webhooks are configured.

### 4. AutoRev collects every cycle — `app/razorpay_billing.py`

The integrator never collects. Two Celery tasks (`workers/razorpay_worker_helper.py`,
scheduled in `workers/phone_worker.py`) do it for every enabled app with keys:

- **`razorpay-collect-due`** (hourly, :20): every `ACTIVE` subscription due by
  tomorrow (IST) gets a charge order (`payment_capture: true`) and a charge
  against its token (`POST /payments/create/recurring` with the customer's
  `email` and `contact`). Razorpay sends the pre-debit notice itself and debits
  about 25 hours later, hence the day's lead. Each attempt is a
  `RazorpayTransaction` carrying the `payment_due_date` it pays for: a cycle is
  never charged while an attempt for it is in flight (72h), never after it is
  paid, retried 24h after a failure, and after 3 failures the subscription is
  `HALTED`.
- **`razorpay-reconcile`** (hourly, :40): charges unsettled after 6h are looked
  up at Razorpay (`GET /payments/{id}`) and settled; a charge order the worker
  created but never charged (it died in between) is failed after 1h.

`POST /notify-redemption` and `/execute-redemption` answer `410 Gone`.

### 5. Gate access — `GET /status/{subscription_id}` or `GET /{phone_number}/status`

Both return `next_payment_date`, `last_payment_status` and
`subscription_validity_end_date`: the due date plus a 6-day grace while
collecting (`ACTIVE`), just the due date once `HALTED`/`CANCELLED`, null if never
paid. User Status prefers `ACTIVE`, then `HALTED`, then `CANCELLED`, then newest.

### 6. Webhook settles charges — `POST /webhook`

Configure this URL in the Razorpay Dashboard with the `razorpay_webhook_secret`
saved on the app's Razorpay settings (`RazorpayApp`). Signature is verified via
HMAC-SHA256 over the raw body (`X-Razorpay-Signature` header). Every branch is
idempotent, since Razorpay redelivers.

**One Razorpay account, several apps.** Razorpay webhooks are per account, so
every registered URL receives every event of the account. The handler matches
orders and tokens across all apps with the same `razorpay_key_id`, applies the
event to the owning subscription and announces it to that subscription's app.
One webhook (any one app's URL and secret) is enough. Customers are shared
across those apps (`fail_existing=0`), so a `token.*` event that matches only by
customer is applied only when exactly one signup of that customer is pending;
otherwise the payment event, which names the order, activates the right one.

- `payment.captured` / `order.paid` on a charge order → transaction `SUCCESS`,
  `subscription.total_payments += 1`, `next_payment_date` moved one cycle on
  from the due date the charge was for (not from today, so collecting early
  does not drift the schedule). A `HALTED` subscription whose last attempt
  succeeds after all goes back to `ACTIVE`.
- `payment.failed` → transaction `FAILED`; the worker retries the next day.
- `token.confirmed` → activates a subscription awaiting authorisation;
  `token.rejected` → `FAILED`; `token.cancelled` → `CANCELLED`.

### 7. Revoke — `POST /revoke/{subscription_id}`

Cancels the token at Razorpay and marks the subscription `CANCELLED`. 409 if it
is already `CANCELLED`/`FAILED`.

### 8. Check a specific charge — `GET /redemption-order-status/{merchant_order_id}`

Returns the current transaction state and `razorpay_payment_id` without
calling Razorpay again.

## Endpoint reference

| Method | Path | Purpose |
|---|---|---|
| POST | `/setup` | Create customer + authorization order |
| GET | `/status/{subscription_id}` | Poll/confirm authorization, activate subscription |
| GET | `/{phone_number}/subscriptions` | List a user's subscriptions + their transactions |
| GET | `/{phone_number}/status` | State and paid-until date for a phone number |
| POST | `/notify-redemption/{subscription_id}` | Withdrawn (410): AutoRev collects |
| POST | `/execute-redemption/{merchant_order_id}` | Withdrawn (410): AutoRev collects |
| GET | `/redemption-order-status/{merchant_order_id}` | Check a specific charge's state |
| POST | `/revoke/{subscription_id}` | Cancel the token; subscription `CANCELLED` |
| POST | `/webhook` | Razorpay event receiver (signature-verified) |

Note: unlike Razorpay, the PhonePe flow (`router/phonepe_router.py`) has no
webhook receiver — it relies purely on the notify/execute-redemption + status
polling endpoints.

## Tests

The Razorpay flow has tests that run the real routes against a throwaway
Postgres database, with Razorpay's HTTP API replaced by a recorder:

```bash
(cd ../infra && docker compose up -d postgres)   # autorev_test is created with infra's Postgres
cd backend
uv run --python 3.12 --no-project --with-requirements requirements-dev.txt python -m pytest tests
```

Point them elsewhere with `AUTOREV_TEST_DATABASE_URL`. They drop and recreate
every table in that database, so never aim it at a real one.
