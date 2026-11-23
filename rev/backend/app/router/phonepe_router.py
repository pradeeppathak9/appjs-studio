import time
import logging
from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
from typing import Optional
from uuid import uuid4

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Path, Query
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    App,
    PhonePeApp,
    PhonePeScheduledTransaction,
    PhonePeSubscription,
    PhonePeSubscriptionArchive,
    PhonePeSubscriptionTransaction,
)
from app.api_handler.phonepe import (
    InvalidSubscriptionStateError,
    PhonePeException,
    get_handler,
)
from app import webhooks

logger = logging.getLogger("autorev")

router = APIRouter(prefix="/api/v1/{app_id}/phonepay", tags=["phonepay"])

# ── Auth / app resolution ──────────────────────────────────────────────────────

def get_app(
    app_id: str = Path(...),
    authorization: str = Header(...),
    db: Session = Depends(get_db),
) -> App:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    api_key = authorization[len("Bearer "):]
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    if app.api_key != api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return app


def _get_phonepe_detail(app_id: str, db: Session) -> PhonePeApp:
    return db.query(PhonePeApp).filter(PhonePeApp.app_id == app_id).first()


# ── Helpers ────────────────────────────────────────────────────────────────────

FREQUENCY_OFFSETS = {
    "DAILY":        lambda d: d + timedelta(days=1),
    "WEEKLY":       lambda d: d + timedelta(weeks=1),
    "FORTNIGHTLY":  lambda d: d + timedelta(weeks=2),
    "MONTHLY":      lambda d: d + relativedelta(months=1),
    "BIMONTHLY":    lambda d: d + relativedelta(months=2),
    "QUARTERLY":    lambda d: d + relativedelta(months=3),
    "HALFYEARLY":   lambda d: d + relativedelta(months=6),
    "YEARLY":       lambda d: d + relativedelta(years=1),
    "ON_DEMAND":    lambda d: None,
}


def get_next_payment_date(ref_date: date, frequency: str, trail_days: int = 0) -> Optional[date]:
    if trail_days > 0:
        return ref_date + timedelta(days=trail_days)
    fn = FREQUENCY_OFFSETS.get(frequency)
    if fn is None:
        raise ValueError(f"Unknown frequency: {frequency}")
    return fn(ref_date)


def _date_to_epoch_ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=IST).timestamp() * 1000)


IN_PROGRESS_STATES = ("INITIATED", "ACTIVATION_IN_PROGRESS")


def _sync_in_progress_state(sub: "PhonePeSubscription", app: App, db: Session) -> None:
    """Live-check PhonePe for a subscription still mid-setup; leave terminal states untouched."""
    if sub.state not in IN_PROGRESS_STATES:
        return
    try:
        detail = _get_phonepe_detail(app.id, db)
        handler = get_handler(detail, custom=True)
        db.commit()  # release the DB connection before the blocking PhonePe call
        response = handler.subscription_status(sub.id)
        was = sub.state
        sub.state = response.get("state", sub.state)
        db.commit()
        if sub.state != was:
            webhooks.dispatch_state_changes(db, [sub])
    except PhonePeException as e:
        logger.error(f"_sync_in_progress_state PhonePe error for sub {sub.id}: {e}")


# ── Request schema ─────────────────────────────────────────────────────────────

class SubscriptionSetupPayload(BaseModel):
    phone_number: str
    amount: Optional[int] = None
    max_amount: int
    amount_type: Optional[str] = "VARIABLE"
    frequency: Optional[str] = "ON_DEMAND"
    auth_workflow_type: Optional[str] = "TRANSACTION"
    trail_days: Optional[int] = None
    product_type: Optional[str] = "UPI_INTENT"
    device_os: Optional[str] = "Android"
    payment_target_app: Optional[str] = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v):
        if not v.isdigit() or len(v) != 10:
            raise ValueError("Phone number must be exactly 10 digits")
        return v

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v):
        if v is not None and v <= 0:
            raise ValueError("Amount must be greater than 0")
        return v

    @field_validator("max_amount")
    @classmethod
    def validate_max_amount(cls, v):
        if v <= 0:
            raise ValueError("Amount must be greater than 0")
        return v

    @field_validator("amount_type")
    @classmethod
    def validate_amount_type(cls, v):
        allowed = {"FIXED", "VARIABLE"}
        if v not in allowed:
            raise ValueError(f"amount_type must be one of {allowed}")
        return v

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v):
        allowed = {"DAILY", "WEEKLY", "MONTHLY", "FORTNIGHTLY", "BIMONTHLY", "QUARTERLY", "HALFYEARLY", "YEARLY", "ON_DEMAND"}
        if v not in allowed:
            raise ValueError(f"frequency must be one of {allowed}")
        return v

    @field_validator("auth_workflow_type")
    @classmethod
    def validate_auth_workflow_type(cls, v):
        allowed = {"TRANSACTION", "PENNY_DROP"}
        if v not in allowed:
            raise ValueError(f"auth_workflow_type must be one of {allowed}")
        return v

    @field_validator("device_os")
    @classmethod
    def validate_device_os(cls, v):
        if v not in {"Android", "iOS"}:
            raise ValueError("device_os must be Android or iOS")
        return v


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/setup")
def setup_subscription(
    body: SubscriptionSetupPayload = Body(...),
    app: App = Depends(get_app),
    db: Session = Depends(get_db),
):
    detail = _get_phonepe_detail(app.id, db)

    amount = body.amount
    if amount is None:
        amount = detail.trial_amount if detail and detail.trial_enabled else None
    if amount is None:
        raise HTTPException(status_code=400, detail="amount is required (or enable a trial with a trial_amount on the app)")

    trail_days = body.trail_days
    if trail_days is None:
        trail_days = detail.trial_period_days if detail and detail.trial_enabled else 0
    trail_days = trail_days or 0

    now_ms = int(time.time() * 1000)
    ten_years_ms = 10 * 365 * 24 * 60 * 60 * 1000

    subscription_id = merchant_order_id = uuid4().hex[:24]
    product_type = body.product_type
    custom = product_type == "UPI_INTENT"

    if product_type == "UPI_INTENT":
        payload = {
            "amount": amount,
            "expireAt": now_ms + (10 * 60 * 1000),
            "metaInfo": {},
            "paymentFlow": {
                "type": "SUBSCRIPTION_SETUP",
                "expireAt": now_ms + ten_years_ms,
                "frequency": body.frequency,
                "maxAmount": body.max_amount,
                "amountType": body.amount_type,
                "paymentMode": {
                    "type": "UPI_INTENT",
                    "targetApp": body.payment_target_app,
                },
                "authWorkflowType": body.auth_workflow_type,
                "merchantSubscriptionId": subscription_id,
            },
            "deviceContext": {"deviceOS": body.device_os},
            "merchantOrderId": merchant_order_id,
        }
    elif product_type == "UPI_MANDATE":
        payload = {
            "amount": amount,
            "expireAt": now_ms + (10 * 60 * 1000),
            "metaInfo": {},
            "paymentFlow": {
                "type": "SUBSCRIPTION_CHECKOUT_SETUP",
                "merchantUrls": {"redirectUrl": "", "cancelRedirectUrl": ""},
                "subscriptionDetails": {
                    "subscriptionType": "RECURRING",
                    "expireAt": now_ms + ten_years_ms,
                    "frequency": body.frequency,
                    "maxAmount": body.max_amount,
                    "amountType": body.amount_type,
                    "productType": "UPI_MANDATE",
                    "authWorkflowType": body.auth_workflow_type,
                    "merchantSubscriptionId": subscription_id,
                },
            },
            "merchantOrderId": merchant_order_id,
        }
    else:
        raise HTTPException(status_code=400, detail="Invalid product_type")

    sub = PhonePeSubscription(
        id=subscription_id,
        app_id=app.id,
        phone_number=body.phone_number,
        amount=amount,
        max_amount=body.max_amount,
        amount_type=body.amount_type,
        frequency=body.frequency,
        auth_workflow_type=body.auth_workflow_type,
        product_type=product_type,
        trail_days=trail_days,
        expire_at=now_ms + ten_years_ms,
        state="INITIATED",
    )

    try:
        handler = get_handler(detail, custom=custom)
        db.commit()  # release the DB connection before the blocking PhonePe call
        response = handler.subscription_setup(payload)
        sub.phonepe_order_id = response.get("orderId")
        db.add(sub)
        db.commit()
        response["subscription_id"] = sub.id
        return response
    except FastAPIHTTPException:
        raise
    except PhonePeException as e:
        db.rollback()
        logger.error(f"setup_subscription failed for app {app.id}: {e}")
        raise HTTPException(status_code=502, detail=f"PhonePe error: {e}")
    except Exception as e:
        db.rollback()
        logger.error(f"setup_subscription unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Payment setup failed")


@router.get("/status/{subscription_id}")
def subscription_status(
    subscription_id: str,
    app: App = Depends(get_app),
    db: Session = Depends(get_db),
):
    sub = db.query(PhonePeSubscription).filter(
        PhonePeSubscription.id == subscription_id,
        PhonePeSubscription.app_id == app.id,
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    try:
        detail = _get_phonepe_detail(app.id, db)
        handler = get_handler(detail, custom=True)
        db.commit()  # release the DB connection before the blocking PhonePe call
        response = handler.subscription_status(subscription_id)
        was_state = sub.state
        sub.state = response.get("state", sub.state)

        # An integration polling this endpoint activates the subscription locally
        # within seconds of setup — before the worker sweep ever sees the transition
        # and computes the date for it. Without this the row has no next_payment_date
        # until the 6-hourly _advance_payment_dates run, so the status API reports
        # null and no scheduled payment exists in the meantime. Mirrors the backfill
        # that GET /{phone_number}/status already does.
        if sub.state == "ACTIVE" and sub.next_payment_date is None:
            next_date = get_next_payment_date(
                sub.created_at.astimezone(IST).date(), sub.frequency, sub.trail_days or 0
            )
            if next_date:
                sub.next_payment_date = _date_to_epoch_ms(next_date)

        db.commit()

        # Fired after the commit so the payload carries the next_payment_date
        # just backfilled above. For ARTIFY-style integrations that poll here
        # seconds after setup this is the first thing to see the activation, and
        # the claim in webhooks.claim keeps it from racing the worker sweep.
        # This endpoint writes back whatever PhonePe reports, so it also catches
        # the ACTIVE → PAUSED/REVOKED drift that no sweep polls for.
        if sub.state != was_state:
            webhooks.dispatch_state_changes(db, [sub])

        return JSONResponse(content=response)
    except PhonePeException as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/order-status/{order_id}")
def subscription_order_status(
    order_id: str,
    app: App = Depends(get_app),
    db: Session = Depends(get_db),
):
    try:
        detail = _get_phonepe_detail(app.id, db)
        handler = get_handler(detail, custom=True)
        db.commit()  # release the DB connection before the blocking PhonePe call
        return JSONResponse(content=handler.subscription_order_status(order_id))
    except PhonePeException as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/{phone_number}/invoices")
def user_invoices(
    phone_number: str,
    app: App = Depends(get_app),
    db: Session = Depends(get_db),
):
    """Every payment made by a phone number, oldest first, as invoice records.

    Two things count as a payment: the setup charge, which is collected up front and
    never becomes a transaction row of its own (so the subscription id stands in as
    its transaction id), and each subsequent successful debit.
    """
    subs = (
        db.query(PhonePeSubscription)
        .filter(
            PhonePeSubscription.app_id == app.id,
            PhonePeSubscription.phone_number == phone_number,
        )
        .all()
    )
    if not subs:
        return JSONResponse(content={"phone_number": phone_number, "count": 0, "invoices": []})

    def _ist_date(dt) -> str:
        return dt.astimezone(IST).date().isoformat()

    rows = []

    # The setup payment, for subscriptions whose setup order actually went through.
    for sub in subs:
        if sub.state in SETUP_COMPLETED_STATES and sub.created_at:
            paid_on = _ist_date(sub.created_at)
            rows.append({
                "_sort": sub.created_at,
                "subscription_id": sub.id,
                "transaction_id": sub.id,
                "invoice_date": paid_on,
                "payment_date": paid_on,
                "amount": sub.amount,
                "type": "SETUP",
            })

    # Every subsequent successful debit.
    txns = (
        db.query(PhonePeSubscriptionTransaction, PhonePeScheduledTransaction)
        .outerjoin(
            PhonePeScheduledTransaction,
            PhonePeScheduledTransaction.id == PhonePeSubscriptionTransaction.scheduled_transaction_id,
        )
        .filter(
            PhonePeSubscriptionTransaction.subscription_id.in_([s.id for s in subs]),
            PhonePeSubscriptionTransaction.state == "COMPLETED",
        )
        .all()
    )
    for txn, sched in txns:
        # The invoice is dated when the payment was scheduled, not when it settled.
        due_ms = (sched.payment_date if sched else None) or txn.payment_due_date
        rows.append({
            "_sort": txn.created_at,
            "subscription_id": txn.subscription_id,
            "transaction_id": txn.transaction_id or txn.id,
            "invoice_date": (
                datetime.fromtimestamp(due_ms / 1000, tz=IST).date().isoformat()
                if due_ms else _ist_date(txn.created_at)
            ),
            "payment_date": _ist_date(txn.created_at),
            "amount": txn.amount,
            "type": "RECURRING",
        })

    rows.sort(key=lambda r: r["_sort"])

    # Numbered per subscription rather than across the whole number, so a
    # subscription's invoices read 1, 2, 3… behind its own id prefix.
    seq: dict[str, int] = {}
    invoices = []
    for row in rows:
        row.pop("_sort")
        sub_id = row["subscription_id"]
        seq[sub_id] = seq.get(sub_id, 0) + 1
        invoices.append({
            "invoice_id": f"{sub_id[:5]}{seq[sub_id]}",
            "phone_number": phone_number,
            **row,
        })

    return JSONResponse(content={
        "phone_number": phone_number,
        "count": len(invoices),
        "invoices": invoices,
    })


@router.get("/report")
def generate_report(
    start: Optional[datetime] = Query(None, description="Window start (inclusive, IST). Defaults to 1 hour before end."),
    end: Optional[datetime] = Query(None, description="Window end (exclusive, IST). Defaults to now."),
    app: App = Depends(get_app),
    db: Session = Depends(get_db),
):
    """Counts of subscriptions created and transactions recorded in a time window."""
    if end is None:
        end = datetime.now(IST)
    elif end.tzinfo is None:
        end = end.replace(tzinfo=IST)
    if start is None:
        start = end - timedelta(hours=1)
    elif start.tzinfo is None:
        start = start.replace(tzinfo=IST)

    if start >= end:
        raise HTTPException(status_code=400, detail="start must be before end")

    # Subscriptions created in the window (live table)
    subs_by_state = {
        state: count
        for state, count in (
            db.query(PhonePeSubscription.state, func.count())
            .filter(
                PhonePeSubscription.created_at >= start,
                PhonePeSubscription.created_at < end,
                PhonePeSubscription.app_id == app.id,
            )
            .group_by(PhonePeSubscription.state)
            .all()
        )
    }

    # Subscriptions created in the window but since archived (e.g. FAILED)
    for state, count in (
        db.query(PhonePeSubscriptionArchive.state, func.count())
        .filter(
            PhonePeSubscriptionArchive.created_at >= start,
            PhonePeSubscriptionArchive.created_at < end,
            PhonePeSubscriptionArchive.app_id == app.id,
        )
        .group_by(PhonePeSubscriptionArchive.state)
        .all()
    ):
        subs_by_state[state] = subs_by_state.get(state, 0) + count

    # Transactions created in the window
    txns_by_state = {
        state: count
        for state, count in (
            db.query(PhonePeSubscriptionTransaction.state, func.count())
            .join(PhonePeSubscription, PhonePeSubscriptionTransaction.subscription_id == PhonePeSubscription.id)
            .filter(
                PhonePeSubscriptionTransaction.created_at >= start,
                PhonePeSubscriptionTransaction.created_at < end,
                PhonePeSubscription.app_id == app.id,
            )
            .group_by(PhonePeSubscriptionTransaction.state)
            .all()
        )
    }

    return JSONResponse(content={
        "window_start": start.astimezone(IST).isoformat(),
        "window_end": end.astimezone(IST).isoformat(),
        "app_id": app.id,
        "subscriptions_created": {
            "total": sum(subs_by_state.values()),
            "by_state": subs_by_state,
        },
        "transactions": {
            "total": sum(txns_by_state.values()),
            "by_state": txns_by_state,
        },
    })


@router.get("/{phone_number}/subscriptions")
def user_subscriptions(
    phone_number: str,
    app: App = Depends(get_app),
    db: Session = Depends(get_db),
):
    subs = (
        db.query(PhonePeSubscription)
        .filter(PhonePeSubscription.app_id == app.id, PhonePeSubscription.phone_number == phone_number)
        .order_by(PhonePeSubscription.created_at.desc())
        .all()
    )
    if not subs:
        raise HTTPException(status_code=404, detail="No subscriptions found")

    for s in subs:
        _sync_in_progress_state(s, app, db)

    sub_ids = [s.id for s in subs]
    txns = (
        db.query(PhonePeSubscriptionTransaction)
        .filter(PhonePeSubscriptionTransaction.subscription_id.in_(sub_ids))
        .all()
    )
    txns_by_sub = {}
    for t in txns:
        txns_by_sub.setdefault(t.subscription_id, []).append({
            "id": t.id,
            "amount": t.amount,
            "state": t.state,
            "transaction_id": t.transaction_id,
            "created_at": t.created_at.isoformat(),
        })

    result = []
    for s in subs:
        result.append({
            "id": s.id,
            "phone_number": s.phone_number,
            "amount": s.amount,
            "frequency": s.frequency,
            "state": s.state,
            "next_payment_date": s.next_payment_date,
            "total_payments": s.total_payments,
            "created_at": s.created_at.isoformat(),
            "txns": txns_by_sub.get(s.id, []),
        })
    return JSONResponse(content={"subscriptions": result})


# Days of access granted past a billing date before the subscription lapses. Applied
# both after a completed payment and to the first billing date of a non-trial signup.
VALIDITY_GRACE_DAYS = 6

# Reaching any of these means the setup order was actually paid — the same test used
# for trial revenue and for the setup payment in _sync_total_payments.
SETUP_COMPLETED_STATES = ("ACTIVE", "PAUSED", "REVOKED")


def _subscription_validity_end_date(sub: PhonePeSubscription, db: Session) -> Optional[str]:
    last = (
        db.query(PhonePeScheduledTransaction)
        .filter(
            PhonePeScheduledTransaction.subscription_id == sub.id,
            PhonePeScheduledTransaction.state == "COMPLETED",
        )
        .order_by(PhonePeScheduledTransaction.payment_date.desc())
        .first()
    )
    if last is None:
        if sub.state not in ("ACTIVE", "PAUSED", "REVOKED"):
            return None

        trail_days = sub.trail_days or 0
        if trail_days > 0:
            return (sub.created_at.astimezone(IST).date() + timedelta(days=trail_days)).isoformat()

        # No trial and no completed payment yet. Setup charges `amount` up front, so
        # the payer has already covered the period running to their first billing
        # date — without this the endpoint returned null for every non-trial
        # subscription until its first successful debit.
        first_due_ms = sub.next_payment_date
        if first_due_ms is None:
            nxt = (
                db.query(PhonePeScheduledTransaction)
                .filter(
                    PhonePeScheduledTransaction.subscription_id == sub.id,
                    PhonePeScheduledTransaction.state == "SCHEDULED",
                )
                .order_by(PhonePeScheduledTransaction.payment_date.asc())
                .first()
            )
            first_due_ms = nxt.payment_date if nxt else None
        if first_due_ms is None:
            return None
        first_due = datetime.fromtimestamp(first_due_ms / 1000, tz=IST).date()
        return (first_due + timedelta(days=VALIDITY_GRACE_DAYS)).isoformat()

    last_paid_date = datetime.fromtimestamp(last.payment_date / 1000, tz=IST).date()
    end_date = get_next_payment_date(last_paid_date, sub.frequency)
    if end_date:
        end_date += timedelta(days=VALIDITY_GRACE_DAYS)
    return end_date.isoformat() if end_date else None


@router.get("/{phone_number}/status")
def user_subscription_status(
    phone_number: str,
    app: App = Depends(get_app),
    db: Session = Depends(get_db),
):
    base = db.query(PhonePeSubscription).filter(
        PhonePeSubscription.app_id == app.id,
        PhonePeSubscription.phone_number == phone_number,
    )
    _priority = case(
        (PhonePeSubscription.state == "ACTIVE", 0),
        (PhonePeSubscription.state.in_(["INITIATED", "ACTIVATION_IN_PROGRESS"]), 1),
        (PhonePeSubscription.state.in_(["PAUSED", "REVOKED"]), 2),
        else_=3,
    )
    sub = (
        base
        .order_by(_priority, PhonePeSubscription.created_at.desc())
        .first()
    )
    if not sub:
        return JSONResponse(content={"state": "NOT_FOUND"})

    _sync_in_progress_state(sub, app, db)

    if sub.state == "ACTIVE" and sub.next_payment_date is None:
        next_date = get_next_payment_date(sub.created_at.astimezone(IST).date(), sub.frequency, sub.trail_days or 0)
        if next_date:
            sub.next_payment_date = _date_to_epoch_ms(next_date)
            db.commit()

    def _ms_to_date(ms):
        if ms is None:
            return None
        return datetime.fromtimestamp(ms / 1000, tz=IST).strftime("%Y-%m-%d")

    trail_days = sub.trail_days or 0

    # subscription_start_date: first billing date (after trial ends)
    start_date = sub.created_at.astimezone(IST).date() + timedelta(days=trail_days)

    show_trial = sub.state in ("ACTIVE", "PAUSED", "REVOKED")

    if show_trial and trail_days > 0:
        trail_amount = sub.amount
        trail_status = "ACTIVE" if datetime.now(IST).date() < start_date else "EXPIRED"
    else:
        trail_amount = None
        trail_status = None

    return JSONResponse(content={
        "state":                          sub.state,
        "subscription_id":                sub.id,
        "subscription_start_date":        start_date.isoformat(),
        "subscription_validity_end_date": _subscription_validity_end_date(sub, db),
        "subscription_frequency":         sub.frequency,
        "next_payment_date":              _ms_to_date(sub.next_payment_date),
        "last_payment_status":            sub.last_payment_status,
        "number_of_successful_payments":  sub.total_payments or 0,
        "payment_amount":                 sub.max_amount,
        "trail_amount":                   trail_amount,
        "trail_status":                   trail_status,
    })


# ── Redemption is driven by AutoRev, not by the integration ───────────────────
#
# notify-redemption and execute-redemption used to let a caller drive the two
# PhonePe steps themselves. They are withdrawn: AutoRev's worker notifies every
# due subscription hourly with autoDebit, so PhonePe collects without a second
# call, and a caller racing that only produced a competing redemption on the
# same mandate — which PhonePe rejects with "Your subscription recurring
# transaction limit is breached", blocking the scheduled collection too.
#
# 410 rather than 404 so an integration still calling these gets told the
# capability is gone on purpose, instead of a status that reads like a bad
# subscription id. The implementations are in git history if they are ever
# needed again.

_REDEMPTION_WITHDRAWN = (
    "This endpoint has been withdrawn. AutoRev notifies and collects due "
    "subscription payments automatically; no call is needed. Use "
    "GET /status/{subscription_id} to follow a subscription, or "
    "GET /{phone_number}/invoices for collected payments."
)


@router.post("/notify-redemption/{subscription_id}", deprecated=True)
def notify_redemption(subscription_id: str, app: App = Depends(get_app)):
    logger.warning(
        f"app={app.id} called withdrawn notify-redemption for {subscription_id}"
    )
    raise HTTPException(status_code=410, detail=_REDEMPTION_WITHDRAWN)


@router.post("/execute-redemption/{merchant_order_id}", deprecated=True)
def execute_redemption(merchant_order_id: str, app: App = Depends(get_app)):
    logger.warning(
        f"app={app.id} called withdrawn execute-redemption for {merchant_order_id}"
    )
    raise HTTPException(status_code=410, detail=_REDEMPTION_WITHDRAWN)


@router.post("/revoke/{subscription_id}")
def revoke_subscription(
    subscription_id: str,
    app: App = Depends(get_app),
    db: Session = Depends(get_db),
):
    """Cancel a mandate at PhonePe, then sync the resulting state back onto the row.

    The API-key equivalent of the dashboard's revoke button, for integrations
    that cancel a plan from their own account screens. Both paths go through
    PhonePe and then trust whatever state it reports, rather than assuming
    REVOKED, because a cancellation can land on REVOKE_IN_PROGRESS first.
    """
    sub = db.query(PhonePeSubscription).filter(
        PhonePeSubscription.id == subscription_id,
        PhonePeSubscription.app_id == app.id,
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    # Checked before the call so a repeated request is a cheap 409 rather than a
    # PhonePe round trip that fails anyway.
    if sub.state in ("CANCELLED", "REVOKED"):
        raise HTTPException(status_code=409, detail=f"Subscription is already {sub.state}")

    was_state = sub.state
    detail = _get_phonepe_detail(app.id, db)
    handler = get_handler(detail, custom=True)
    db.commit()  # release the DB connection before the blocking PhonePe calls

    try:
        handler.cancel_subscription(subscription_id)
    except InvalidSubscriptionStateError as e:
        raise HTTPException(status_code=409, detail=f"PhonePe rejected the cancellation: {e}")
    except PhonePeException as e:
        logger.error(f"revoke_subscription failed for {subscription_id}: {e}")
        raise HTTPException(status_code=502, detail=f"PhonePe error: {e}")

    try:
        sub.state = handler.subscription_status(subscription_id).get("state", "REVOKED")
    except PhonePeException as e:
        # The cancellation itself succeeded, so the mandate is gone either way;
        # the state sweep reconciles the exact value on its next pass.
        logger.warning(
            f"revoke_subscription: cancel succeeded but status re-fetch failed for {subscription_id}: {e}"
        )
        sub.state = "REVOKED"

    db.add(sub)
    db.commit()

    # REVOKED fires subscription.revoked here; REVOKE_IN_PROGRESS maps to no
    # event and is announced by the sweep that polls the in-progress states once
    # PhonePe settles it.
    if sub.state != was_state:
        webhooks.dispatch_state_changes(db, [sub])

    return JSONResponse(content={"subscription_id": sub.id, "state": sub.state})


@router.get("/redemption-order-status/{merchant_order_id}")
def redemption_order_status(
    merchant_order_id: str,
    app: App = Depends(get_app),
    db: Session = Depends(get_db),
):
    try:
        detail = _get_phonepe_detail(app.id, db)
        handler = get_handler(detail, custom=True)
        db.commit()  # release the DB connection before the blocking PhonePe call
        return JSONResponse(content={"response": handler.redemption_order_status(merchant_order_id)})
    except PhonePeException as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/refresh-token")
def refresh_token(app: App = Depends(get_app), db: Session = Depends(get_db)):
    try:
        detail = _get_phonepe_detail(app.id, db)
        handler = get_handler(detail, custom=True)
        db.commit()  # release the DB connection before the blocking PhonePe call
        return JSONResponse(content=handler.force_refresh_token())
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
