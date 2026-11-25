"""Dashboard-facing webhook configuration and delivery history.

Separate from apps.py because the webhook config is its own small resource with
its own validation, secret rotation and delivery log, and apps.py is already the
longest router in the project.
"""
import logging
import secrets
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import webhooks
from app.auth import get_current_user
from app.database import get_db
from app.models import App, User, WebhookDelivery
from app.router.apps import _get_accessible_app

logger = logging.getLogger("autorev")

router = APIRouter(prefix="/api/apps/{app_id}/webhook", tags=["webhooks"])


class WebhookConfigUpdate(BaseModel):
    url: Optional[str] = None
    enabled: Optional[bool] = None
    events: Optional[list[str]] = None
    # Omit to leave the stored credential alone; "" clears it. The UI sends it
    # only when the customer actually typed a new value, so a masked read is
    # never echoed back as the real thing.
    auth_header: Optional[str] = None
    auth_enabled: Optional[bool] = None


def _masked(secret: Optional[str]) -> Optional[str]:
    if not secret:
        return None
    return secret[:6] + "•" * 20 + secret[-4:]


def _config(app: App, reveal: bool = False) -> dict:
    return {
        "url": app.webhook_url,
        "enabled": bool(app.webhook_enabled),
        "events": app.webhook_events if app.webhook_events is not None else list(webhooks.EVENTS),
        "secret": app.webhook_secret if reveal else _masked(app.webhook_secret),
        "has_secret": bool(app.webhook_secret),
        # Each event ships the sample the docs panel renders. Generated from the
        # real payload builders, so it cannot drift from what gets delivered;
        # cheap enough to inline (four small objects) that the UI needs no
        # second round trip to show one.
        "available_events": [
            {
                "name": name,
                "description": desc,
                "sample": webhooks.sample_payload(
                    name, app.id, app.name, "phonepe" if app.phonepe_enabled else "razorpay"
                ),
                "sample_headers": webhooks.sample_headers(name),
            }
            for name, desc in webhooks.EVENTS.items()
        ],
        "signature_header": "X-Autorev-Signature",
        "max_attempts": webhooks.MAX_ATTEMPTS,
        # Write-only: the stored credential is never returned, revealed or not.
        # Unlike webhook_secret it is the customer's own credential for their
        # system, so there is no case where we need to hand it back.
        "auth_header": webhooks.mask_auth_header(app.webhook_auth_header),
        "has_auth_header": bool(app.webhook_auth_header),
        "auth_enabled": bool(app.webhook_auth_enabled),
    }


def _delivery(d: WebhookDelivery) -> dict:
    return {
        "id": d.id,
        "event": d.event,
        "object_id": d.object_id,
        "url": d.url,
        "status": d.status,
        "attempts": d.attempts,
        "response_code": d.response_code,
        "error": d.error,
        "payload": d.payload,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
    }


@router.get("")
def get_webhook(
    app_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = _get_accessible_app(app_id, current_user, db)
    return _config(app)


@router.put("")
def update_webhook(
    app_id: str,
    body: WebhookConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = _get_accessible_app(app_id, current_user, db)

    if body.events is not None:
        unknown = [e for e in body.events if e not in webhooks.EVENTS]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown event(s): {', '.join(unknown)}")
        app.webhook_events = body.events

    if body.url is not None:
        url = body.url.strip()
        if url:
            try:
                app.webhook_url = webhooks.validate_webhook_url(url)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
        else:
            # Clearing the URL disables delivery outright — leaving it enabled
            # with nowhere to send to would just queue failures.
            app.webhook_url = None
            app.webhook_enabled = False

    if body.enabled is not None:
        if body.enabled and not app.webhook_url:
            raise HTTPException(status_code=400, detail="Set a webhook URL before enabling delivery")
        app.webhook_enabled = body.enabled

    if body.auth_header is not None:
        value = body.auth_header.strip()
        if not value:
            # Clearing the credential also turns the header off: sending an empty
            # Authorization is worse than sending none.
            app.webhook_auth_header = None
            app.webhook_auth_enabled = False
        elif value == webhooks.mask_auth_header(app.webhook_auth_header):
            # The UI echoed its own masked read back. Leave the stored value
            # alone rather than overwriting a working credential with bullets.
            pass
        else:
            try:
                app.webhook_auth_header = webhooks.validate_auth_header(value)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

    if body.auth_enabled is not None:
        if body.auth_enabled and not app.webhook_auth_header:
            raise HTTPException(
                status_code=400,
                detail="Enter an Authorization header value before enabling it",
            )
        app.webhook_auth_enabled = body.auth_enabled

    # A secret is what makes the payload verifiable, so there is never a reason
    # to have a URL without one. Mint it on first save rather than making the
    # customer press a second button.
    if app.webhook_url and not app.webhook_secret:
        app.webhook_secret = "whsec_" + secrets.token_hex(32)

    db.commit()
    db.refresh(app)
    # Reveal once, on the save that created it: it cannot be shown again.
    return _config(app, reveal=True)


@router.post("/rotate-secret")
def rotate_secret(
    app_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = _get_accessible_app(app_id, current_user, db)
    app.webhook_secret = "whsec_" + secrets.token_hex(32)
    db.commit()
    db.refresh(app)
    return _config(app, reveal=True)


@router.post("/test")
def send_test(
    app_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = _get_accessible_app(app_id, current_user, db)
    if not app.webhook_url:
        raise HTTPException(status_code=400, detail="Set a webhook URL first")
    if not app.webhook_secret:
        raise HTTPException(status_code=400, detail="Webhook secret is missing — rotate it and try again")

    # object_id is the delivery's own id, so a test never collides with the
    # (app_id, event, object_id) uniqueness that real events rely on and can be
    # fired as many times as the customer likes. Bypasses webhook_enabled and
    # the subscribed-event list on purpose: this is how you check the endpoint
    # before turning delivery on.
    delivery_id = uuid4().hex
    db.add(WebhookDelivery(
        id=delivery_id,
        app_id=app.id,
        event=webhooks.TEST_EVENT,
        object_id=delivery_id,
        url=app.webhook_url,
        payload=webhooks.envelope(
            webhooks.TEST_EVENT, delivery_id, app.id, app.name,
            {"message": "This is a test event from AutoRev."},
        ),
        status="PENDING",
        attempts=0,
    ))
    db.commit()
    webhooks.enqueue([delivery_id])
    return {"delivery_id": delivery_id, "status": "PENDING"}


@router.get("/deliveries")
def list_deliveries(
    app_id: str,
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = _get_accessible_app(app_id, current_user, db)
    q = db.query(WebhookDelivery).filter(WebhookDelivery.app_id == app.id)
    if status:
        q = q.filter(WebhookDelivery.status == status)
    rows = q.order_by(WebhookDelivery.created_at.desc()).limit(limit).all()
    return {"deliveries": [_delivery(d) for d in rows]}


@router.post("/deliveries/{delivery_id}/retry")
def retry_delivery(
    app_id: str,
    delivery_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = _get_accessible_app(app_id, current_user, db)
    delivery = db.query(WebhookDelivery).filter(
        WebhookDelivery.id == delivery_id,
        WebhookDelivery.app_id == app.id,
    ).first()
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")

    # Resending the same event for the same object is only ever done through
    # here — a second claim would be swallowed by the uniqueness constraint.
    # The attempt counter resets so the customer gets a fresh set of retries,
    # and the URL is re-snapshotted in case it changed since the failure.
    delivery.status = "PENDING"
    delivery.attempts = 0
    delivery.error = None
    delivery.response_code = None
    delivery.url = app.webhook_url or delivery.url
    db.commit()

    webhooks.enqueue([delivery.id])
    return {"delivery_id": delivery.id, "status": "PENDING"}
