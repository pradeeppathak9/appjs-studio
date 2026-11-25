import time
import logging
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Path, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import App, RazorpayApp, RazorpaySubscription, RazorpayTransaction
from app.api_handler.razorpay import RazorpayAPIHandler, RazorpayException, get_handler
from app import razorpay_billing as billing

logger = logging.getLogger("autorev")

router = APIRouter(prefix="/api/v1/{app_id}/razorpay", tags=["razorpay"])

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


def _get_razorpay_detail(app_id: str, db: Session) -> RazorpayApp:
    return db.query(RazorpayApp).filter(RazorpayApp.app_id == app_id).first()


# Activation, collection and settlement live in app.razorpay_billing, shared
# with the Celery worker that collects every subscription as it comes due.

# ── Request schema ─────────────────────────────────────────────────────────────

class RazorpaySetupPayload(BaseModel):
    name: str
    # Required: Razorpay will not create a recurring payment without the
    # customer's email, so a subscription set up without one could be
    # authorised and then never collected.
    email: EmailStr
    phone_number: str
    amount: Optional[int] = None
    max_amount: int
    amount_type: Optional[str] = "VARIABLE"
    frequency: Optional[str] = "ON_DEMAND"
    method: Optional[str] = "upi"          # upi | emandate | card
    trail_days: Optional[int] = None
    # The integration's own reference, echoed in status responses and webhooks.
    external_ref: Optional[str] = Field(None, max_length=200)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("name must not be empty")
        return v.strip()

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

    @field_validator("method")
    @classmethod
    def validate_method(cls, v):
        allowed = {"upi", "emandate", "card"}
        if v not in allowed:
            raise ValueError(f"method must be one of {allowed}")
        return v


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/setup")
def setup_subscription(
    body: RazorpaySetupPayload = Body(...),
    app: App = Depends(get_app),
    db: Session = Depends(get_db),
):
    amount = body.amount
    if amount is None:
        raise HTTPException(status_code=400, detail="amount is required")
    if amount > body.max_amount:
        # Razorpay refuses a UPI authorisation order larger than the token's max_amount,
        # and every later collection charges `amount` against that same ceiling.
        raise HTTPException(status_code=400, detail="amount must not exceed max_amount")

    trail_days = body.trail_days or 0

    now_s = int(time.time())
    ten_years_s = 10 * 365 * 24 * 60 * 60

    subscription_id = uuid4().hex[:24]

    detail = _get_razorpay_detail(app.id, db)
    handler = get_handler(detail)

    try:
        customer = handler.create_customer(
            name=body.name,
            contact=f"+91{body.phone_number}",
            email=body.email,
            notes={"app_id": app.id, "subscription_id": subscription_id},
        )
    except RazorpayException as e:
        logger.error(f"razorpay create_customer failed for app {app.id}: {e}")
        raise HTTPException(status_code=502, detail=f"Razorpay error: {e}")

    customer_id = customer.get("id")

    token_params = {
        "max_amount": body.max_amount,
        "expire_at": now_s + ten_years_s,
    }
    if body.method == "upi":
        token_params["frequency"] = billing.UPI_TOKEN_FREQUENCY[body.frequency]

    sub = RazorpaySubscription(
        id=subscription_id,
        app_id=app.id,
        phone_number=body.phone_number,
        name=body.name,
        email=body.email,
        amount=amount,
        max_amount=body.max_amount,
        amount_type=body.amount_type,
        frequency=body.frequency,
        method=body.method,
        trail_days=trail_days,
        external_ref=body.external_ref,
        expire_at=(now_s + ten_years_s) * 1000,
        razorpay_customer_id=customer_id,
        state="INITIATED",
    )

    try:
        order = handler.create_authorization_order(
            customer_id=customer_id,
            amount=amount,
            method=body.method,
            token_params=token_params,
            notes={"app_id": app.id, "subscription_id": subscription_id},
        )
        sub.razorpay_order_id = order.get("id")
        sub.state = "AUTHORIZATION_PENDING"
        db.add(sub)
        db.commit()
        return {
            "subscription_id": sub.id,
            "external_ref": sub.external_ref,
            # public: what Razorpay Checkout on the device opens the order with
            "razorpay_key_id": detail.razorpay_key_id if detail else None,
            "razorpay_customer_id": customer_id,
            "razorpay_order_id": order.get("id"),
            "amount": order.get("amount", amount),
            "currency": order.get("currency", "INR"),
        }
    except FastAPIHTTPException:
        raise
    except RazorpayException as e:
        db.rollback()
        logger.error(f"setup_subscription failed for app {app.id}: {e}")
        raise HTTPException(status_code=502, detail=f"Razorpay error: {e}")
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
    sub = db.query(RazorpaySubscription).filter(
        RazorpaySubscription.id == subscription_id,
        RazorpaySubscription.app_id == app.id,
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    handler = get_handler(_get_razorpay_detail(app.id, db))
    try:
        order = handler.fetch_order(sub.razorpay_order_id) if sub.razorpay_order_id else {}
    except RazorpayException as e:
        raise HTTPException(status_code=502, detail=str(e))

    before = sub.state
    if order.get("status") == "paid" and not sub.razorpay_token_id:
        try:
            token_id = billing.token_for_order(handler, sub)
            if token_id:
                billing.activate(sub, token_id)
        except RazorpayException as e:
            logger.error(f"razorpay token lookup failed for {sub.id}: {e}")
    db.commit()
    if sub.state != before:
        billing.announce(db, changed=[sub])

    return JSONResponse(content={
        "subscription_id": sub.id,
        "external_ref": sub.external_ref,
        "state": sub.state,
        "razorpay_order_status": order.get("status"),
        "razorpay_token_id": sub.razorpay_token_id,
        **_paid_up(sub),
    })


def _paid_up(sub: RazorpaySubscription) -> dict:
    """The fields an integration gates access on."""
    return {
        "next_payment_date": billing.epoch_ms_to_date(sub.next_payment_date).isoformat() if sub.next_payment_date else None,
        "last_payment_status": sub.last_payment_status,
        "subscription_validity_end_date": billing.validity_end_date(sub),
    }


@router.get("/{phone_number}/subscriptions")
def user_subscriptions(
    phone_number: str,
    app: App = Depends(get_app),
    db: Session = Depends(get_db),
):
    subs = (
        db.query(RazorpaySubscription)
        .filter(RazorpaySubscription.app_id == app.id, RazorpaySubscription.phone_number == phone_number)
        .order_by(RazorpaySubscription.created_at.desc())
        .all()
    )
    if not subs:
        raise HTTPException(status_code=404, detail="No subscriptions found")

    sub_ids = [s.id for s in subs]
    txns = (
        db.query(RazorpayTransaction)
        .filter(RazorpayTransaction.subscription_id.in_(sub_ids))
        .all()
    )
    txns_by_sub = {}
    for t in txns:
        txns_by_sub.setdefault(t.subscription_id, []).append({
            "id": t.id,
            "amount": t.amount,
            "state": t.state,
            "razorpay_payment_id": t.razorpay_payment_id,
            "created_at": t.created_at.isoformat(),
        })

    result = []
    for s in subs:
        result.append({
            "id": s.id,
            "phone_number": s.phone_number,
            "name": s.name,
            "email": s.email,
            "external_ref": s.external_ref,
            "amount": s.amount,
            "frequency": s.frequency,
            "state": s.state,
            "next_payment_date": s.next_payment_date,
            "total_payments": s.total_payments,
            "created_at": s.created_at.isoformat(),
            "txns": txns_by_sub.get(s.id, []),
        })
    return JSONResponse(content={"subscriptions": result})


# When a number holds several subscriptions, the one that answers "is this
# customer paid up?": a collecting one first, then one that stopped collecting
# (its paid period may not have run out), then the newest of the rest.
_STATUS_PREFERENCE = {"ACTIVE": 0, "HALTED": 1, "CANCELLED": 2}


@router.get("/{phone_number}/status")
def user_subscription_status(
    phone_number: str,
    app: App = Depends(get_app),
    db: Session = Depends(get_db),
):
    subs = (
        db.query(RazorpaySubscription)
        .filter(RazorpaySubscription.app_id == app.id, RazorpaySubscription.phone_number == phone_number)
        .order_by(RazorpaySubscription.created_at.desc())
        .limit(50)
        .all()
    )
    if not subs:
        return JSONResponse(content={"state": "NOT_FOUND"})
    sub = min(subs, key=lambda s: _STATUS_PREFERENCE.get(s.state, 3))  # stable: newest within a rank
    return JSONResponse(content={"subscription_id": sub.id, "state": sub.state, **_paid_up(sub)})


_COLLECTION_WITHDRAWN = (
    "AutoRev collects Razorpay subscriptions itself as they come due. "
    "Use GET /status/{subscription_id} or GET /{phone_number}/status to follow one."
)


@router.post("/notify-redemption/{subscription_id}", deprecated=True)
def notify_redemption(subscription_id: str, app: App = Depends(get_app)):
    logger.warning(f"app={app.id} called withdrawn razorpay notify-redemption for {subscription_id}")
    raise HTTPException(status_code=410, detail=_COLLECTION_WITHDRAWN)


@router.post("/execute-redemption/{merchant_order_id}", deprecated=True)
def execute_redemption(merchant_order_id: str, app: App = Depends(get_app)):
    logger.warning(f"app={app.id} called withdrawn razorpay execute-redemption for {merchant_order_id}")
    raise HTTPException(status_code=410, detail=_COLLECTION_WITHDRAWN)


@router.get("/redemption-order-status/{merchant_order_id}")
def redemption_order_status(
    merchant_order_id: str,
    app: App = Depends(get_app),
    db: Session = Depends(get_db),
):
    txn = (
        db.query(RazorpayTransaction)
        .join(RazorpaySubscription)
        .filter(RazorpayTransaction.id == merchant_order_id, RazorpaySubscription.app_id == app.id)
        .first()
    )
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return JSONResponse(content={"state": txn.state, "razorpay_payment_id": txn.razorpay_payment_id})


@router.post("/revoke/{subscription_id}")
def revoke_subscription(
    subscription_id: str,
    app: App = Depends(get_app),
    db: Session = Depends(get_db),
):
    """Cancel the subscription's token at Razorpay. Terminal: nothing more can be collected."""
    sub = db.query(RazorpaySubscription).filter(
        RazorpaySubscription.id == subscription_id,
        RazorpaySubscription.app_id == app.id,
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    if sub.state in ("CANCELLED", "FAILED"):
        raise HTTPException(status_code=409, detail=f"Subscription is already {sub.state}")

    if sub.razorpay_token_id:
        handler = get_handler(_get_razorpay_detail(app.id, db))
        try:
            handler.cancel_token(sub.razorpay_customer_id, sub.razorpay_token_id)
        except RazorpayException as e:
            raise HTTPException(status_code=502, detail=f"Razorpay error: {e}")
    # Without a token there is no mandate yet; cancelling only stops the setup.
    sub.state = "CANCELLED"
    db.commit()
    billing.announce(db, changed=[sub])
    return JSONResponse(content={"subscription_id": sub.id, "external_ref": sub.external_ref, "state": sub.state})


# ── Webhook ────────────────────────────────────────────────────────────────────

@router.post("/webhook")
async def razorpay_webhook(
    app_id: str = Path(...),
    x_razorpay_signature: str = Header(None, alias="X-Razorpay-Signature"),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Razorpay's events for this app. Every branch is idempotent: Razorpay
    redelivers, and an event that changes nothing is acknowledged all the same."""
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    detail = _get_razorpay_detail(app.id, db)
    secret = detail.razorpay_webhook_secret if detail else None
    if not secret:
        raise HTTPException(status_code=400, detail="Razorpay webhook secret not configured for this app")

    raw_body = await request.body()
    if not RazorpayAPIHandler.verify_webhook_signature(raw_body, x_razorpay_signature, secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    event = await request.json()
    event_type = event.get("event")
    payload = event.get("payload", {})
    payment = payload.get("payment", {}).get("entity", {})
    order_id = payment.get("order_id") or payload.get("order", {}).get("entity", {}).get("id")

    if event_type in ("payment.authorized", "order.paid", "payment.captured", "payment.failed") and order_id:
        txn = (
            db.query(RazorpayTransaction)
            .join(RazorpaySubscription)
            .filter(RazorpaySubscription.app_id == app_id, RazorpayTransaction.razorpay_order_id == order_id)
            .first()
        )
        announcement = {}
        if txn:
            if event_type in ("payment.captured", "order.paid"):
                sub = txn.subscription
                announcement = {"advanced": [(sub, sub.next_payment_date)], "changed": [sub]}
                billing.apply_success(txn, payment.get("id"))
            elif event_type == "payment.failed":
                billing.apply_failure(txn)
                announcement = {"failed": [txn]}
            # payment.authorized alone changes nothing: charge orders auto-capture.
        elif event_type != "payment.failed":
            # Not a collection: the customer's authorisation payment for a new mandate.
            sub = db.query(RazorpaySubscription).filter(
                RazorpaySubscription.app_id == app_id,
                RazorpaySubscription.razorpay_order_id == order_id,
            ).first()
            if sub and sub.state in ("INITIATED", "AUTHORIZATION_PENDING"):
                token_id = payment.get("token_id")
                if not token_id:
                    try:
                        token_id = billing.token_for_order(get_handler(detail), sub)
                    except RazorpayException as e:
                        logger.error(f"webhook token lookup failed for {sub.id}: {e}")
                if token_id:
                    billing.activate(sub, token_id)
                    announcement = {"changed": [sub]}
        db.commit()
        if announcement:
            billing.announce(db, **announcement)

    elif event_type in ("token.confirmed", "token.rejected", "token.cancelled"):
        token = payload.get("token", {}).get("entity", {})
        sub = _sub_for_token(db, app_id, token)
        if sub:
            if event_type == "token.confirmed" and sub.state in ("INITIATED", "AUTHORIZATION_PENDING"):
                billing.activate(sub, token["id"])
            elif event_type == "token.rejected" and sub.state != "CANCELLED":
                sub.state = "FAILED"
            elif event_type == "token.cancelled":
                # Cancelled by the customer in their UPI app, at the bank, or by us.
                sub.state = "CANCELLED"
            db.commit()
            billing.announce(db, changed=[sub])

    return JSONResponse(content={"status": "ok"})


def _sub_for_token(db: Session, app_id: str, token: dict) -> Optional[RazorpaySubscription]:
    """The subscription a token.* event is about: the one holding the token, else the
    newest subscription of that customer still waiting for authorisation."""
    token_id, customer_id = token.get("id"), token.get("customer_id")
    if not token_id:
        return None
    sub = db.query(RazorpaySubscription).filter(
        RazorpaySubscription.app_id == app_id,
        RazorpaySubscription.razorpay_token_id == token_id,
    ).first()
    if sub or not customer_id:
        return sub
    return (
        db.query(RazorpaySubscription)
        .filter(
            RazorpaySubscription.app_id == app_id,
            RazorpaySubscription.razorpay_customer_id == customer_id,
            RazorpaySubscription.state.in_(["INITIATED", "AUTHORIZATION_PENDING"]),
        )
        .order_by(RazorpaySubscription.created_at.desc())
        .first()
    )
