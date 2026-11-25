"""Outbound webhooks: the event registry, delivery claiming, signing and sending.

This lives under backend/app/ rather than workers/ because both processes need
it. State transitions are observed in two places at once — the FastAPI status
endpoints an integration polls, and the Celery sweeps — and workers/Dockerfile
puts backend/ on PYTHONPATH as `app.*`, so one module serves both.

Claiming and sending are split on purpose:

  * Claiming is a database write, done by whoever saw the transition. It is a
    single INSERT ... ON CONFLICT DO NOTHING RETURNING id against the unique
    (app_id, event, object_id) on webhook_deliveries, so concurrent observers of
    the same transition produce exactly one delivery. notify-redemption learned
    this the hard way with a lock; here the uniqueness constraint settles it.

  * Sending is always a Celery task, never inline. Customer endpoints are slow,
    down, or hanging, and none of that belongs in a request the integration is
    waiting on or in the middle of a poll batch. The task owns the retries.
"""
import hashlib
import hmac
import ipaddress
import json
import logging
import socket
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import ObjectDeletedError, StaleDataError

from app.config import settings
from app.models.app import App
from app.models.razorpay import RazorpaySubscription
from app.models.webhook import WebhookDelivery

logger = logging.getLogger("autorev.webhooks")

IST = timezone(timedelta(hours=5, minutes=30))

DELIVER_TASK = "autorev-webhook-deliver"

# Every event a customer can subscribe to, with the copy the Settings tab shows.
# Adding one here is all the UI and the /webhook config endpoint need: both read
# this registry rather than carrying their own list.
EVENTS: dict[str, str] = {
    "subscription.activated": (
        "The mandate was authorised and the subscription moved to ACTIVE. "
        "Fires once per subscription."
    ),
    "subscription.paused": (
        "PhonePe reports the mandate as PAUSED — usually the payer paused it in "
        "their UPI app. No debit will succeed until it resumes."
    ),
    "subscription.revoked": (
        "The mandate was revoked, by the payer, by PhonePe, or from the "
        "dashboard. It is terminal: no further payment will be collected."
    ),
    "subscription.next_payment_updated": (
        "A recurring payment was confirmed and the next payment date moved "
        "forward. Fires once per billing cycle and carries the previous date."
    ),
    "subscription.halted": (
        "Razorpay: every attempt to collect the current cycle failed, so AutoRev "
        "stopped collecting. The customer is paid up to next_payment_date. Fires "
        "once per subscription."
    ),
    "subscription.payment_failed": (
        "Razorpay: one attempt to collect a cycle failed. AutoRev retries the next "
        "day, up to 3 attempts per cycle, then halts the subscription. Fires once "
        "per failed attempt and carries the attempt in data.payment."
    ),
}

NEXT_PAYMENT_EVENT = "subscription.next_payment_updated"

# Which state a subscription has landed in, and therefore which event announces
# it. Dispatch reads the state back from the database and looks it up here, so
# every call site reports "this subscription changed" and does not have to know
# which event that means — and a state with no entry (INITIATED,
# ACTIVATION_IN_PROGRESS, the *_IN_PROGRESS trio, CANCELLED, FAILED) announces
# nothing. Adding an event for one of those is a line here plus a line in EVENTS.
STATE_EVENTS: dict[str, str] = {
    "ACTIVE": "subscription.activated",
    "PAUSED": "subscription.paused",
    "REVOKED": "subscription.revoked",
}

# The same idea for Razorpay subscriptions, whose states differ: HALTED is
# collection giving up, CANCELLED is the mandate ending (revoked by the payer,
# their bank, or through /revoke).
RAZORPAY_STATE_EVENTS: dict[str, str] = {
    "ACTIVE": "subscription.activated",
    "HALTED": "subscription.halted",
    "CANCELLED": "subscription.revoked",
}

PAYMENT_FAILED_EVENT = "subscription.payment_failed"

TEST_EVENT = "webhook.test"

HTTP_TIMEOUT = 10.0
MAX_RESPONSE_CHARS = 2000

# Attempt 1 is immediate; a failure then waits 30s, 2m, 10m, 1h, 6h — six
# attempts over about 7.5 hours, which covers a customer deploy or a short
# outage without hammering an endpoint that is simply gone.
RETRY_BACKOFF_SECONDS = (30, 120, 600, 3600, 21600)
MAX_ATTEMPTS = len(RETRY_BACKOFF_SECONDS) + 1


# ── URL safety ─────────────────────────────────────────────────────────────────

def validate_webhook_url(url: str) -> str:
    """Return the normalised URL, or raise ValueError.

    The worker fetches whatever is stored here, from inside the private network
    that also holds Postgres, Redis and RabbitMQ. An unchecked URL would make
    this endpoint a request forwarder into that network, so hosts that resolve
    to loopback, private, link-local (which includes the cloud metadata
    endpoint) or reserved ranges are rejected. Checked again at send time in
    _resolve_guard, because DNS can change between saving and sending.
    """
    url = (url or "").strip()
    if not url:
        raise ValueError("Webhook URL is required")
    if len(url) > 2000:
        raise ValueError("Webhook URL is too long")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Webhook URL must start with http:// or https://")
    if not parsed.hostname:
        raise ValueError("Webhook URL has no host")

    _resolve_guard(parsed.hostname)
    return url


def _resolve_guard(hostname: str) -> None:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise ValueError(f"Webhook host does not resolve: {hostname} ({e.strerror or e})")

    if settings.webhook_allow_private:  # development only (AUTOREV_WEBHOOK_ALLOW_PRIVATE)
        return
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError(
                f"Webhook host {hostname} resolves to a private address ({ip}). "
                "Use a publicly reachable URL."
            )


MAX_AUTH_HEADER_CHARS = 1024


def validate_auth_header(value: str) -> str:
    """Return the normalised Authorization value, or raise ValueError.

    A newline here would let the stored value inject extra headers — or a whole
    second request — into every delivery, so CR/LF is rejected outright rather
    than stripped. HTTP header values are latin-1, so anything outside it would
    fail at send time with a far less obvious error than this one.
    """
    value = (value or "").strip()
    if not value:
        raise ValueError("Authorization header value is required")
    if len(value) > MAX_AUTH_HEADER_CHARS:
        raise ValueError(f"Authorization header value must be under {MAX_AUTH_HEADER_CHARS} characters")
    if "\n" in value or "\r" in value:
        raise ValueError("Authorization header value cannot contain line breaks")
    try:
        value.encode("latin-1")
    except UnicodeEncodeError:
        raise ValueError("Authorization header value must contain only latin-1 characters")
    return value


def mask_auth_header(value: str | None) -> str | None:
    """A hint for the UI that leaks nothing.

    The scheme ("Bearer", "Basic") is not secret and tells the customer their
    value is stored the way they meant it; everything after it is withheld
    entirely rather than showing leading or trailing characters of the token.
    """
    if not value:
        return None
    scheme, _, rest = value.partition(" ")
    if rest:
        return f"{scheme} " + "•" * 16
    return "•" * 16


# ── Signing ────────────────────────────────────────────────────────────────────

def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ── Payloads ───────────────────────────────────────────────────────────────────

def _date_to_ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=IST).timestamp() * 1000)


def _ms_to_date(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=IST).strftime("%Y-%m-%d")


def _is_razorpay(sub) -> bool:
    return isinstance(sub, RazorpaySubscription) or getattr(sub, "gateway", None) == "razorpay"


def payload_for(sub) -> dict:
    """The subscription body for either gateway."""
    return razorpay_subscription_payload(sub) if _is_razorpay(sub) else subscription_payload(sub)


def _rz_date(ms: int | None) -> str | None:
    # Razorpay rows store dates as epoch ms of UTC midnight (app.razorpay_billing).
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def razorpay_subscription_payload(sub) -> dict:
    """The body of every subscription.* event about a Razorpay subscription.

    Field names follow GET /razorpay/status/{id}, plus external_ref: the
    integration's own reference given at /setup.
    """
    from app.razorpay_billing import validity_end_date

    return {
        "gateway": "razorpay",
        "subscription_id": sub.id,
        "app_id": sub.app_id,
        "external_ref": sub.external_ref,
        "phone_number": sub.phone_number,
        "email": sub.email,
        "state": sub.state,
        "amount": sub.amount,
        "max_amount": sub.max_amount,
        "frequency": sub.frequency,
        "method": sub.method,
        "next_payment_date": _rz_date(sub.next_payment_date),
        "subscription_validity_end_date": validity_end_date(sub),
        "total_payments": sub.total_payments or 0,
        "last_payment_status": sub.last_payment_status,
        "razorpay_customer_id": sub.razorpay_customer_id,
        "razorpay_token_id": sub.razorpay_token_id,
        "created_at": sub.created_at.astimezone(IST).isoformat() if sub.created_at else None,
    }


def subscription_payload(sub) -> dict:
    """The subscription body sent with every subscription.* event.

    Field names and date formats match GET /phonepay/{phone}/status, so an
    integration already reading that endpoint needs no second mapping.
    """
    return {
        "gateway": "phonepe",
        "subscription_id": sub.id,
        "app_id": sub.app_id,
        "phone_number": sub.phone_number,
        "state": sub.state,
        "amount": sub.amount,
        "max_amount": sub.max_amount,
        "amount_type": sub.amount_type,
        "frequency": sub.frequency,
        "auth_workflow_type": sub.auth_workflow_type,
        "product_type": sub.product_type,
        "trail_days": sub.trail_days or 0,
        "next_payment_date": _ms_to_date(sub.next_payment_date),
        "total_payments": sub.total_payments or 0,
        "last_payment_status": sub.last_payment_status,
        "phonepe_subscription_id": sub.phonepe_subscription_id,
        "phonepe_order_id": sub.phonepe_order_id,
        "created_at": sub.created_at.astimezone(IST).isoformat() if sub.created_at else None,
    }


def envelope(event: str, delivery_id: str, app_id: str, app_name: str | None, data: dict) -> dict:
    """Wrap an event body. The single place a delivered payload takes its shape.

    Both identifiers sit at the top level — app_id is the stable key to match
    on, app_name is what a human reads in a log or an alert — so a receiver
    handling several AutoRev apps on one endpoint routes on the envelope without
    reaching into a body whose shape depends on the event. They are stamped into
    `data` here as well, rather than by each caller, which is what lets
    sample_payload below render exactly what gets sent.
    """
    return {
        "event": event,
        "delivery_id": delivery_id,
        "app_id": app_id,
        "app_name": app_name,
        "created_at": datetime.now(IST).isoformat(),
        "data": {**data, "app_id": app_id, "app_name": app_name},
    }


# ── Samples for the dashboard ──────────────────────────────────────────────────

# The state a subscription is in when each event fires. Mirrors STATE_EVENTS,
# inverted, with the one non-state event pinned to ACTIVE because the mandate
# carries on billing.
_SAMPLE_STATE = {
    "subscription.activated": "ACTIVE",
    "subscription.paused": "PAUSED",
    "subscription.revoked": "REVOKED",
    NEXT_PAYMENT_EVENT: "ACTIVE",
}


_RAZORPAY_SAMPLE_STATE = {
    "subscription.activated": "ACTIVE",
    "subscription.halted": "HALTED",
    "subscription.revoked": "CANCELLED",
    "subscription.payment_failed": "ACTIVE",
    NEXT_PAYMENT_EVENT: "ACTIVE",
}

RAZORPAY_ONLY_EVENTS = {"subscription.halted", PAYMENT_FAILED_EVENT}
PHONEPE_ONLY_EVENTS = {"subscription.paused"}


def _razorpay_sample(event: str, app_id: str, app_name: str | None) -> dict:
    now = datetime.now(IST)
    due = (now + timedelta(days=30)).date()
    sub = SimpleNamespace(
        gateway="razorpay",
        id="5c2e9a7b1d3f4e6a8b0c2d4e",
        app_id=app_id,
        external_ref="studio:0b6f3c1e-8a2d-4f5b-9c7e-1d2a3b4c5d6e",
        phone_number="9876543210",
        email="jane@example.com",
        state=_RAZORPAY_SAMPLE_STATE.get(event, "ACTIVE"),
        amount=9900,
        max_amount=9900,
        frequency="MONTHLY",
        method="upi",
        next_payment_date=int(datetime(due.year, due.month, due.day, tzinfo=timezone.utc).timestamp() * 1000),
        total_payments=3,
        last_payment_status="FAILED" if event in RAZORPAY_ONLY_EVENTS else "SUCCESS",
        razorpay_customer_id="cust_N5bJ0kX9yZ1a2B",
        razorpay_token_id="token_N5bJ1mQ8wE3r4T",
        created_at=now - timedelta(days=90),
    )
    data = razorpay_subscription_payload(sub)
    if event == NEXT_PAYMENT_EVENT:
        data["previous_payment_date"] = now.date().isoformat()
    if event == PAYMENT_FAILED_EVENT:
        data["payment"] = {
            "attempt_id": "9f8e7d6c5b4a39281706f5e4d3c2b1a0",
            "amount": 9900,
            "state": "FAILED",
            "payment_due_date": data["next_payment_date"],
            "razorpay_order_id": "order_N5bJ2pL7vC5x6Y",
            "razorpay_payment_id": "pay_N5bJ3sK6uB7z8W",
        }
    return envelope(event, "7a1b9c3d5e7f41a2b3c4d5e6f7a8b9c0", app_id, app_name, data)


def sample_payload(event: str, app_id: str, app_name: str | None, gateway: str = "phonepe") -> dict | None:
    """A realistic payload for `event`, for the docs panel in Settings.

    Deliberately built by running the real builders over a stand-in
    subscription rather than by hand-writing JSON: a sample that is typed out
    separately drifts the moment a field is added, and a customer coding against
    a stale sample is worse off than one with no sample at all. Every field name,
    date format and envelope key here is therefore the same code path a
    delivered payload takes.
    """
    if event not in EVENTS:
        return None
    if event in RAZORPAY_ONLY_EVENTS or (gateway == "razorpay" and event not in PHONEPE_ONLY_EVENTS):
        return _razorpay_sample(event, app_id, app_name)

    now = datetime.now(IST)
    sub = SimpleNamespace(
        id="b3f1c8d9e4a24f7b8c1d2e3f4a5b6c7d",
        app_id=app_id,
        phone_number="9876543210",
        state=_SAMPLE_STATE.get(event, "ACTIVE"),
        amount=9900,
        max_amount=50000,
        amount_type="FIXED",
        frequency="MONTHLY",
        auth_workflow_type="TRANSACTION",
        product_type="UPI_INTENT",
        trail_days=0,
        next_payment_date=_date_to_ms((now + timedelta(days=30)).date()),
        total_payments=3,
        last_payment_status="COMPLETED",
        phonepe_subscription_id="OMS2410081234567890",
        phonepe_order_id="OMO2410081234567890",
        created_at=now - timedelta(days=90),
    )

    data = subscription_payload(sub)
    if event == NEXT_PAYMENT_EVENT:
        data["previous_payment_date"] = _ms_to_date(_date_to_ms(now.date()))

    return envelope(event, "7a1b9c3d5e7f41a2b3c4d5e6f7a8b9c0", app_id, app_name, data)


def sample_headers(event: str) -> dict:
    """The header set a delivery carries, with the signature shown as a shape."""
    return {
        "Content-Type": "application/json",
        "User-Agent": "autorev-webhooks/1",
        "X-Autorev-Event": event,
        "X-Autorev-Delivery": "7a1b9c3d5e7f41a2b3c4d5e6f7a8b9c0",
        "X-Autorev-Timestamp": str(int(datetime.now(timezone.utc).timestamp())),
        "X-Autorev-Signature": "sha256=<hmac-sha256 of the raw body, keyed by your signing secret>",
    }


# ── Claiming ───────────────────────────────────────────────────────────────────

def _subscribes_to(app: App, event: str) -> bool:
    if not app.webhook_enabled or not app.webhook_url or not app.webhook_secret:
        return False
    events = app.webhook_events
    if events is None:
        return True          # unset means every registered event
    return event in events


def claim(db: Session, event: str, items: list[tuple[str, str, dict]]) -> list[str]:
    """Claim `items` as (app_id, object_id, data) and return the delivery ids won.

    One statement for the whole batch, so a poll run that activates 400
    subscriptions costs one round trip rather than 400. Rows already claimed by
    another process are dropped by ON CONFLICT and simply do not come back.

    Commits, because the row has to be durable before the task that reads it is
    enqueued — otherwise the worker can pick the job up and find nothing there.
    """
    if not items:
        return []

    app_ids = {app_id for app_id, _, _ in items}
    apps = {a.id: a for a in db.query(App).filter(App.id.in_(app_ids)).all()}

    rows = []
    for app_id, object_id, data in items:
        app = apps.get(app_id)
        if not app or not _subscribes_to(app, event):
            continue
        delivery_id = uuid4().hex
        # app.name comes from the App rows already loaded above, so it costs
        # nothing here, whereas reaching sub.app from a payload builder would be
        # one query per subscription across a batch that can run to hundreds.
        rows.append({
            "id": delivery_id,
            "app_id": app_id,
            "event": event,
            "object_id": object_id,
            "url": app.webhook_url,
            "payload": envelope(event, delivery_id, app_id, app.name, data),
            "status": "PENDING",
            "attempts": 0,
        })

    if not rows:
        return []

    stmt = (
        pg_insert(WebhookDelivery)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["app_id", "event", "object_id"])
        .returning(WebhookDelivery.id)
    )
    try:
        claimed = [r[0] for r in db.execute(stmt).all()]
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"webhook claim failed for {event} ({len(rows)} rows): {e}")
        return []

    skipped = len(rows) - len(claimed)
    if skipped:
        logger.info(f"[webhook] {event}: claimed {len(claimed)}, {skipped} already claimed elsewhere")
    return claimed


def enqueue(delivery_ids: list[str]) -> None:
    """Hand claimed deliveries to the worker. Never raises into the caller.

    A broker hiccup here leaves the rows PENDING, which the
    autorev-webhook-maintenance sweep picks up — losing the event outright
    would be worse than sending it late.
    """
    if not delivery_ids:
        return
    from app.celery_client import celery_client

    for delivery_id in delivery_ids:
        try:
            celery_client.send_task(DELIVER_TASK, args=[delivery_id])
        except Exception as e:
            logger.error(f"[webhook] could not enqueue delivery {delivery_id}: {e}")


def dispatch_state_changes(db: Session, subs: list) -> None:
    """Announce whatever state these subscriptions are now in.

    The event is derived from each row's own state via STATE_EVENTS, so callers
    pass "these subscriptions changed" and never name an event. Two things fall
    out of that:

      * A state nobody subscribes to is silently skipped, so the in-progress and
        mid-setup states cost nothing.
      * The row is the authority. If a caller saw a transition in a PhonePe
        response but the write never landed — a rolled-back batch, say — the
        state read back here is the old one and the wrong event cannot be sent.
        Claiming is permanent, so sending it would have suppressed the real
        event for good.

    `subs` must be ORM rows loaded on this thread. Safe to call from every path
    that observes a transition: the claim makes duplicates free.
    """
    by_event: dict[str, list[tuple[str, str, dict]]] = {}
    for sub in subs:
        event = (RAZORPAY_STATE_EVENTS if _is_razorpay(sub) else STATE_EVENTS).get(sub.state)
        if not event:
            continue
        by_event.setdefault(event, []).append((sub.app_id, sub.id, payload_for(sub)))

    for event, items in by_event.items():
        enqueue(claim(db, event, items))


def dispatch_next_payment_updated(db: Session, subs_with_previous: list[tuple]) -> None:
    """Announce a confirmed recurring payment and the date it moved the cycle to.

    Unlike the state events this one repeats — once per billing cycle, for the
    life of the mandate — so it cannot be claimed against the subscription id
    alone: the uniqueness constraint would let the first cycle through and
    silently swallow every one after it. The claim key is therefore the
    subscription *and* the date being announced:

        object_id = "<subscription_id>:<next_payment_date epoch ms>"

    Each cycle advances to a distinct date, so that is one delivery per cycle,
    while two processes computing the same advance still collapse to one. The
    subscription id stays in data.subscription_id for anything matching on it.

    `subs_with_previous` is (ORM subscription, previous next_payment_date in ms),
    read after the advance has been committed so the row carries the new date.
    """
    items = []
    for sub, previous_ms in subs_with_previous:
        if sub.next_payment_date is None:
            continue
        data = payload_for(sub)
        data["previous_payment_date"] = (_rz_date if _is_razorpay(sub) else _ms_to_date)(previous_ms)
        items.append((sub.app_id, f"{sub.id}:{sub.next_payment_date}", data))

    enqueue(claim(db, NEXT_PAYMENT_EVENT, items))


def dispatch_payment_failed(db: Session, txns: list) -> None:
    """Announce failed collection attempts (Razorpay transactions), one delivery per attempt.

    Claimed against the transaction id, so a failure seen by both the webhook and
    the reconcile sweep is announced once.
    """
    items = []
    for txn in txns:
        sub = txn.subscription
        data = payload_for(sub)
        data["payment"] = {
            "attempt_id": txn.id,
            "amount": txn.amount,
            "state": txn.state,
            "payment_due_date": _rz_date(txn.payment_due_date),
            "razorpay_order_id": txn.razorpay_order_id,
            "razorpay_payment_id": txn.razorpay_payment_id,
        }
        items.append((sub.app_id, txn.id, data))
    enqueue(claim(db, PAYMENT_FAILED_EVENT, items))


# ── Sending ────────────────────────────────────────────────────────────────────

class DeliveryOutcome:
    __slots__ = ("delivered", "retryable", "detail", "attempts")

    def __init__(self, delivered: bool, retryable: bool, detail: str, attempts: int):
        self.delivered = delivered
        self.retryable = retryable
        self.detail = detail
        self.attempts = attempts


def deliver(db: Session, delivery_id: str) -> DeliveryOutcome:
    """POST one delivery and record the result. Returns whether to retry.

    4xx other than 408/429 is treated as final: the endpoint understood the
    request and rejected it, so repeating it changes nothing. Everything else —
    5xx, timeouts, connection errors — is the endpoint being temporarily
    unavailable and is worth another attempt.
    """
    delivery = db.query(WebhookDelivery).filter(WebhookDelivery.id == delivery_id).first()
    if not delivery:
        return DeliveryOutcome(False, False, "delivery row not found", 0)
    if delivery.status == "DELIVERED":
        return DeliveryOutcome(True, False, "already delivered", delivery.attempts)

    app = db.query(App).filter(App.id == delivery.app_id).first()
    secret = app.webhook_secret if app else None
    if not secret:
        return _record(db, delivery, None, "webhook secret is not configured", retryable=False)

    body = json.dumps(delivery.payload, separators=(",", ":")).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "autorev-webhooks/1",
        "X-Autorev-Event": delivery.event,
        "X-Autorev-Delivery": delivery.id,
        "X-Autorev-Timestamp": str(int(datetime.now(timezone.utc).timestamp())),
        "X-Autorev-Signature": sign(secret, body),
    }

    # Read at send time, not snapshotted onto the delivery row: the row is served
    # to the dashboard, and a credential that never lands there cannot leak from
    # there. It also means rotating the token fixes deliveries already queued.
    if app.webhook_auth_enabled and app.webhook_auth_header:
        headers["Authorization"] = app.webhook_auth_header

    # Re-check the host: the URL was validated when it was saved, but DNS it
    # resolves to can change afterwards.
    try:
        _resolve_guard(urlparse(delivery.url).hostname or "")
    except ValueError as e:
        return _record(db, delivery, None, str(e), retryable=False)

    db.commit()  # release the connection before the blocking HTTP call
    try:
        response = httpx.post(delivery.url, content=body, headers=headers, timeout=HTTP_TIMEOUT)
    except Exception as e:
        return _record(db, delivery, None, f"{type(e).__name__}: {e}", retryable=True)

    if 200 <= response.status_code < 300:
        return _record(db, delivery, response.status_code, None, retryable=False)

    retryable = response.status_code >= 500 or response.status_code in (408, 429)
    detail = (response.text or "")[:MAX_RESPONSE_CHARS]
    return _record(db, delivery, response.status_code, detail or f"HTTP {response.status_code}", retryable=retryable)


def _record(db, delivery, code: int | None, error: str | None, retryable: bool) -> DeliveryOutcome:
    # The row can disappear between the check at the top of deliver() and here:
    # webhook_deliveries cascades from apps, so deleting an app discards rows
    # for deliveries already in flight. Writing the result then fails on a row
    # that no longer exists, which must not surface as a task crash — there is
    # nothing left to retry into.
    delivery_id = delivery.id
    event = delivery.event
    try:
        delivery.attempts = (delivery.attempts or 0) + 1
        delivery.response_code = code
        delivery.error = error

        delivered = error is None
        exhausted = delivery.attempts >= MAX_ATTEMPTS
        if delivered:
            delivery.status = "DELIVERED"
            delivery.delivered_at = datetime.now(timezone.utc)
        elif retryable and not exhausted:
            delivery.status = "PENDING"
        else:
            delivery.status = "FAILED"

        attempts = delivery.attempts
        status = delivery.status
        db.commit()
    except (ObjectDeletedError, StaleDataError):
        db.rollback()
        logger.warning(
            f"[webhook] {event} {delivery_id} was deleted while in flight; discarding the result"
        )
        return DeliveryOutcome(False, False, "delivery row deleted while in flight", 0)

    if delivered:
        logger.info(f"[webhook] {event} {delivery_id} → {code} (attempt {attempts})")
    else:
        logger.warning(
            f"[webhook] {event} {delivery_id} attempt {attempts} failed "
            f"({code or 'no response'}): {error} — status now {status}"
        )

    return DeliveryOutcome(delivered, retryable and not exhausted, error or "", attempts)


def retry_countdown(attempts: int) -> int:
    """Seconds to wait before the attempt that follows `attempts` failures."""
    index = max(attempts - 1, 0)
    return RETRY_BACKOFF_SECONDS[min(index, len(RETRY_BACKOFF_SECONDS) - 1)]
