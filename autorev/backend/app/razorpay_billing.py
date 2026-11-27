"""Razorpay recurring billing: activation, collection and settlement.

AutoRev collects Razorpay subscriptions itself, as it does PhonePe. The
integrator sets a subscription up and reads its status; everything after the
customer's authorisation runs here:

  * collect_due      charges every ACTIVE subscription coming due (Celery, hourly)
  * reconcile        settles charges whose webhook never arrived (Celery, hourly)
  * apply_* helpers  called by the webhook and the status endpoint

It lives under backend/app/ because both the API and the Celery workers use it
(workers/Dockerfile puts backend/ on PYTHONPATH as `app.*`).

Dates. `next_payment_date` and `payment_due_date` are epoch milliseconds of a
calendar date (UTC midnight of that date), the same convention as the rest of
the Razorpay tables. "Today" is the IST calendar day.
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from app.api_handler.razorpay import RazorpayAPIHandler, RazorpayException
from app.models import RazorpaySubscription, RazorpayTransaction

logger = logging.getLogger("autorev.razorpay")

IST = timezone(timedelta(hours=5, minutes=30))

# Start collecting this far ahead of the due date. Razorpay debits a UPI
# customer about 25 hours after the pre-debit notification it sends when the
# charge is created, so a charge started the day before lands on the due date.
COLLECT_AHEAD_DAYS = 1

# Attempts per billing cycle, and the wait between them. After the last one
# fails the subscription is HALTED: no further attempts, and the customer's
# paid-up period runs out on its own.
MAX_ATTEMPTS_PER_CYCLE = 3
RETRY_AFTER = timedelta(hours=24)

# A charge submitted and not yet settled blocks another for the same
# subscription for this long. UPI payments can take 24-36 hours to confirm;
# past this the reconcile sweep has had ample time to settle it.
IN_FLIGHT_WINDOW = timedelta(hours=72)

# Unsettled charges older than this are asked about directly (a lost webhook).
RECONCILE_AFTER = timedelta(hours=6)
# A charge order whose charge call never completed (worker died in between).
ABANDONED_AFTER = timedelta(hours=1)

# Access continues this long past the due date while collection is retried,
# matching PhonePe's VALIDITY_GRACE_DAYS.
VALIDITY_GRACE_DAYS = 6

# Razorpay's token.frequency values for UPI Autopay (mandatory on a UPI
# authorisation order). ON_DEMAND has no fixed cycle: Razorpay's as_presented.
UPI_TOKEN_FREQUENCY = {
    "DAILY": "daily",
    "WEEKLY": "weekly",
    "FORTNIGHTLY": "fortnightly",
    "MONTHLY": "monthly",
    "BIMONTHLY": "bimonthly",
    "QUARTERLY": "quarterly",
    "HALFYEARLY": "half_yearly",
    "YEARLY": "yearly",
    "ON_DEMAND": "as_presented",
}

FREQUENCY_OFFSETS = {
    "DAILY": lambda d: d + timedelta(days=1),
    "WEEKLY": lambda d: d + timedelta(weeks=1),
    "FORTNIGHTLY": lambda d: d + timedelta(weeks=2),
    "MONTHLY": lambda d: d + relativedelta(months=1),
    "BIMONTHLY": lambda d: d + relativedelta(months=2),
    "QUARTERLY": lambda d: d + relativedelta(months=3),
    "HALFYEARLY": lambda d: d + relativedelta(months=6),
    "YEARLY": lambda d: d + relativedelta(years=1),
    "ON_DEMAND": lambda d: None,
}


# ── Dates ─────────────────────────────────────────────────────────────────────

# Razorpay keeps at most 15 notes per entity; autorev's own ids take up to 3 of them.
MAX_EXTRA_NOTES = 12
RESERVED_NOTES = ("app_id", "subscription_id", "txn_id")


def razorpay_notes(extra: Optional[dict], **ours: str) -> dict:
    """The integration's notes plus autorev's ids. Ours win, so a caller can't relabel them."""
    return {**(extra or {}), **ours}


def get_next_payment_date(ref_date: date, frequency: str, trail_days: int = 0) -> Optional[date]:
    if trail_days > 0:
        return ref_date + timedelta(days=trail_days)
    fn = FREQUENCY_OFFSETS.get(frequency)
    if fn is None:
        raise ValueError(f"Unknown frequency: {frequency}")
    return fn(ref_date)


def date_to_epoch_ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


def epoch_ms_to_date(ms: int) -> date:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date()


def today_ist(now: Optional[datetime] = None) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(IST).date()


def validity_end_date(sub: RazorpaySubscription) -> Optional[str]:
    """The last day the customer has paid for (YYYY-MM-DD), or None if they have not paid.

    The authorisation payment covers the first period, so an ACTIVE
    subscription is paid up to its next due date. While AutoRev is still
    collecting (ACTIVE) the customer also gets the retry grace period; once
    collection has stopped (HALTED, CANCELLED) access ends on the due date.
    """
    if not sub.next_payment_date:
        return None
    due = epoch_ms_to_date(sub.next_payment_date)
    if sub.state == "ACTIVE":
        return (due + timedelta(days=VALIDITY_GRACE_DAYS)).isoformat()
    if sub.state in ("HALTED", "CANCELLED"):
        return due.isoformat()
    return None


# ── Outbound webhooks ─────────────────────────────────────────────────────────

def announce(db: Session, *, changed=(), advanced=(), failed=()) -> None:
    """Send the integration's webhooks for what just happened. Call after the commit.

    changed   subscriptions whose state may have moved (activated / halted / revoked;
              the event comes from the state read back, and each is claimed once)
    advanced  (subscription, previous next_payment_date) after a successful collection
    failed    transactions whose collection attempt failed

    Never raises: a webhook problem must not undo or fail a billing change. Claims
    are unique, so announcing the same thing twice sends it once.
    """
    from app import webhooks

    try:
        if changed:
            webhooks.dispatch_state_changes(db, list(changed))
        moved = [(sub, prev) for sub, prev in advanced if sub.next_payment_date and sub.next_payment_date != prev]
        if moved:
            webhooks.dispatch_next_payment_updated(db, moved)
        failures = [t for t in failed if t.state == "FAILED"]
        if failures:
            webhooks.dispatch_payment_failed(db, failures)
    except Exception as e:
        db.rollback()
        logger.error(f"razorpay webhook dispatch failed: {e}")


# ── Activation ────────────────────────────────────────────────────────────────

def token_for_order(handler: RazorpayAPIHandler, sub: RazorpaySubscription) -> Optional[str]:
    """The token created by this subscription's authorisation payment.

    Razorpay reuses an existing customer for the same contact number, so the
    customer can hold tokens from earlier subscriptions. The authorisation
    payment names its own token; only if no payment carries one do we fall back
    to the customer's newest token.
    """
    if sub.razorpay_order_id:
        payments = handler.fetch_order_payments(sub.razorpay_order_id).get("items", [])
        ranked = sorted(payments, key=lambda p: p.get("status") != "captured")  # captured first
        for p in ranked:
            if p.get("token_id"):
                return p["token_id"]
    tokens = handler.list_tokens(sub.razorpay_customer_id).get("items", [])
    if not tokens:
        return None
    return max(tokens, key=lambda t: t.get("created_at") or 0).get("id")


def activate(sub: RazorpaySubscription, token_id: str) -> None:
    """Mark an authorised subscription ACTIVE on `token_id` and schedule its first collection."""
    sub.razorpay_token_id = token_id
    sub.state = "ACTIVE"
    if not sub.next_payment_date:
        start = sub.created_at.astimezone(IST).date() if sub.created_at else today_ist()
        next_date = get_next_payment_date(start, sub.frequency, sub.trail_days or 0)
        if next_date:
            sub.next_payment_date = date_to_epoch_ms(next_date)


# ── Settlement ────────────────────────────────────────────────────────────────

def apply_success(txn: RazorpayTransaction, payment_id: Optional[str]) -> None:
    """A collection was captured. Idempotent: a repeat changes nothing."""
    if txn.state == "SUCCESS":
        return
    sub = txn.subscription
    txn.state = "SUCCESS"
    txn.razorpay_payment_id = payment_id or txn.razorpay_payment_id
    sub.total_payments = (sub.total_payments or 0) + 1
    sub.last_payment_status = "SUCCESS"
    # Advance from the cycle this payment was for (not from today: collection
    # starts early, and counting from the settle day would drift the schedule).
    # Only when it is still the subscription's current cycle, so a late webhook
    # for an old cycle cannot skip one.
    paid_for = txn.payment_due_date or sub.next_payment_date
    if paid_for and paid_for == sub.next_payment_date:
        next_date = get_next_payment_date(epoch_ms_to_date(paid_for), sub.frequency, 0)
        if next_date:
            sub.next_payment_date = date_to_epoch_ms(next_date)
    if sub.state == "HALTED":
        # A retry that was already in flight went through after all.
        sub.state = "ACTIVE"


def apply_failure(txn: RazorpayTransaction) -> None:
    """A collection failed. Idempotent; never undoes a success."""
    if txn.state in ("SUCCESS", "FAILED"):
        return
    txn.state = "FAILED"
    txn.subscription.last_payment_status = "FAILED"


# ── Collection ────────────────────────────────────────────────────────────────

def _cycle_attempts(db: Session, sub: RazorpaySubscription) -> list[RazorpayTransaction]:
    return (
        db.query(RazorpayTransaction)
        .filter(
            RazorpayTransaction.subscription_id == sub.id,
            RazorpayTransaction.payment_due_date == sub.next_payment_date,
        )
        .order_by(RazorpayTransaction.created_at.desc())
        .all()
    )


def next_action(db: Session, sub: RazorpaySubscription, now: datetime) -> str:
    """What collection should do with `sub` now: "collect", "wait", "halt" or "skip"."""
    if sub.state != "ACTIVE" or not sub.razorpay_token_id or not sub.next_payment_date:
        return "skip"
    due = epoch_ms_to_date(sub.next_payment_date)
    if due > today_ist(now) + timedelta(days=COLLECT_AHEAD_DAYS):
        return "skip"
    attempts = _cycle_attempts(db, sub)
    for a in attempts:
        if a.state == "SUCCESS":
            return "skip"  # paid; next_payment_date moves on with the success
        if a.state in ("NOTIFIED", "INITIATED") and a.created_at > now - IN_FLIGHT_WINDOW:
            return "wait"
    failed = [a for a in attempts if a.state == "FAILED"]
    if len(failed) >= MAX_ATTEMPTS_PER_CYCLE:
        return "halt"
    if failed and failed[0].created_at > now - RETRY_AFTER:
        return "wait"
    return "collect"


def start_collection(db: Session, handler: RazorpayAPIHandler, sub: RazorpaySubscription,
                     now: Optional[datetime] = None) -> RazorpayTransaction:
    """Create the charge order and charge the token for `sub`'s current cycle.

    The transaction is committed as NOTIFIED before the charge call, so a crash
    in between leaves a row the reconcile sweep can find, never a silent charge.
    """
    txn = RazorpayTransaction(
        id=uuid4().hex,
        subscription_id=sub.id,
        amount=sub.amount,
        state="NOTIFIED",
        payment_due_date=sub.next_payment_date,
        # Retry spacing and the in-flight window are measured from here.
        created_at=now or datetime.now(timezone.utc),
    )
    notes = razorpay_notes(sub.notes, app_id=sub.app_id, subscription_id=sub.id, txn_id=txn.id)
    try:
        order = handler.create_recurring_charge_order(
            customer_id=sub.razorpay_customer_id, amount=sub.amount, notes=notes
        )
    except RazorpayException as e:
        txn.state = "FAILED"
        txn.response_payload = {"error": str(e), "stage": "order"}
        sub.last_payment_status = "FAILED"
        db.add(txn)
        db.commit()
        logger.warning(f"razorpay charge order failed for {sub.id}: {e}")
        return txn

    txn.razorpay_order_id = order.get("id")
    txn.request_payload = {"customer_id": sub.razorpay_customer_id, "amount": sub.amount}
    db.add(txn)
    db.commit()

    try:
        payment = handler.charge_token(
            customer_id=sub.razorpay_customer_id,
            order_id=txn.razorpay_order_id,
            token_id=sub.razorpay_token_id,
            amount=txn.amount,
            email=sub.email,
            contact=f"+91{sub.phone_number}",
            notes=notes,
        )
    except RazorpayException as e:
        txn.state = "FAILED"
        txn.response_payload = {"error": str(e), "stage": "charge"}
        sub.last_payment_status = "FAILED"
        db.commit()
        logger.warning(f"razorpay charge failed for {sub.id}: {e}")
        return txn

    # The recurring-payment API answers {"razorpay_payment_id": ...}, not a payment entity.
    txn.razorpay_payment_id = payment.get("razorpay_payment_id") or payment.get("id")
    txn.response_payload = payment
    if txn.state == "NOTIFIED":  # a fast webhook may already have settled it
        txn.state = "INITIATED"
    db.commit()
    return txn


def collect_due(db: Session, handler: RazorpayAPIHandler, app_id: str, now: Optional[datetime] = None,
                limit: int = 500) -> dict:
    """Start collection for one app's subscriptions coming due. Returns counts per action."""
    now = now or datetime.now(timezone.utc)
    horizon = date_to_epoch_ms(today_ist(now) + timedelta(days=COLLECT_AHEAD_DAYS))
    subs = (
        db.query(RazorpaySubscription)
        .filter(
            RazorpaySubscription.app_id == app_id,
            RazorpaySubscription.state == "ACTIVE",
            RazorpaySubscription.next_payment_date <= horizon,
        )
        .order_by(RazorpaySubscription.next_payment_date)
        .limit(limit)
        .all()
    )
    counts = {"collect": 0, "wait": 0, "halt": 0, "skip": 0}
    halted, failed = [], []
    for sub in subs:
        action = next_action(db, sub, now)
        counts[action] += 1
        if action == "collect":
            failed.append(start_collection(db, handler, sub, now))
        elif action == "halt":
            sub.state = "HALTED"
            sub.last_payment_status = "FAILED"
            db.commit()
            halted.append(sub)
            logger.info(f"razorpay subscription {sub.id} halted after {MAX_ATTEMPTS_PER_CYCLE} failed attempts")
    announce(db, changed=halted, failed=failed)
    return counts


def reconcile(db: Session, handler: RazorpayAPIHandler, app_id: str, now: Optional[datetime] = None,
              limit: int = 200) -> dict:
    """Settle one app's charges that a webhook should have settled by now."""
    now = now or datetime.now(timezone.utc)
    rows = (
        db.query(RazorpayTransaction)
        .join(RazorpaySubscription)
        .filter(
            RazorpaySubscription.app_id == app_id,
            RazorpayTransaction.state.in_(["NOTIFIED", "INITIATED"]),
            RazorpayTransaction.created_at < now - min(RECONCILE_AFTER, ABANDONED_AFTER),
        )
        .order_by(RazorpayTransaction.created_at)
        .limit(limit)
        .all()
    )
    counts = {"success": 0, "failed": 0, "pending": 0}
    advanced, failed, changed = [], [], []
    for txn in rows:
        if txn.state == "INITIATED" and txn.created_at > now - RECONCILE_AFTER:
            continue
        try:
            payment = _payment_of(handler, txn)
        except RazorpayException as e:
            logger.warning(f"razorpay reconcile lookup failed for {txn.id}: {e}")
            continue
        status = (payment or {}).get("status")
        if status == "captured":
            sub = txn.subscription
            advanced.append((sub, sub.next_payment_date))
            changed.append(sub)  # a HALTED subscription goes back to ACTIVE
            apply_success(txn, payment.get("id"))
            counts["success"] += 1
        elif status == "failed" or (payment is None and txn.state == "NOTIFIED"):
            # failed at Razorpay, or a charge order that was never charged
            apply_failure(txn)
            failed.append(txn)
            counts["failed"] += 1
        else:
            if payment and txn.state == "NOTIFIED":
                txn.state = "INITIATED"  # the charge went through before the worker died
                txn.razorpay_payment_id = payment.get("id")
            counts["pending"] += 1
        db.commit()
    announce(db, changed=changed, advanced=advanced, failed=failed)
    return counts


def _payment_of(handler: RazorpayAPIHandler, txn: RazorpayTransaction) -> Optional[dict]:
    if txn.razorpay_payment_id:
        return handler.fetch_payment(txn.razorpay_payment_id)
    if txn.razorpay_order_id:
        items = handler.fetch_order_payments(txn.razorpay_order_id).get("items", [])
        return items[0] if items else None
    return None
