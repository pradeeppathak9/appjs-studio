"""App users buying plans, through autorev (../autorev).

autorev holds the gateway credentials, sets up the payer's mandate and collects every cycle. Studio
starts a checkout through it, then turns what autorev reports into subscriptions and credits:

  * checkout     create a `payment_orders` row, ask autorev to set up the mandate, and hand the client
                 what its gateway SDK needs (Razorpay Checkout: key id, order id, customer id)
  * order        the client polls this after checkout; while pending it asks autorev, so activation
                 works even where autorev's webhooks can't reach Studio (local development)
  * webhook      autorev's signed events: activated / next_payment_updated / halted / revoked /
                 payment_failed. Each delivery is applied once (payment_events.delivery_id).
  * cancel       revoke the mandate at autorev; the subscription runs to the end of the paid period

Only Razorpay is wired for now (autorev's PhonePe flow has no checkout here yet).

Dates. autorev reports `subscription_validity_end_date` (YYYY-MM-DD, IST): the day the payer is paid
up to, plus a grace period while it is still collecting. The Studio subscription's
`current_period_end` follows it (end of that day, IST), so access matches autorev's gate.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from uuid import UUID

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studio.apps.service import AppService
from studio.config import Settings
from studio.db.tables import App, AppUser, PaymentEvent, PaymentOrder, Plan, Subscription
from studio.endusers.billing import BillingService, next_grant_after_extension, start_subscription
from studio.errors import ConflictError, NotFoundError, ServiceError, ValidationFailed

log = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
WEBHOOK_MAX_AGE_S = 60 * 60  # autorev retries for hours, but each attempt is signed afresh
REF_PREFIX = "studio:"


class PaymentsUnavailable(ServiceError):
    status, code = 409, "payments_unavailable"


class GatewayError(ServiceError):
    status, code = 502, "payment_gateway_error"


class WebhookRejected(ServiceError):
    status, code = 401, "invalid_signature"


# ---- autorev ------------------------------------------------------------------------------------


class AutorevClient:
    """autorev's API for one autorev app (`Authorization: Bearer <api key>`)."""

    def __init__(self, http: httpx.AsyncClient, base_url: str, app_id: str, api_key: str, timeout: float):
        self.http, self.base, self.app_id, self.api_key, self.timeout = (
            http,
            base_url.rstrip("/"),
            app_id,
            api_key,
            timeout,
        )

    async def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{self.base}/api/v1/{self.app_id}{path}"
        try:
            r = await self.http.request(
                method,
                url,
                json=body,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            log.warning("autorev %s %s failed: %s", method, path, e)
            raise GatewayError("the payment service can't be reached; try again in a moment") from e
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail")
            except ValueError:
                detail = None
            log.warning("autorev %s %s -> %s %s", method, path, r.status_code, detail)
            if r.status_code in (401, 404):
                raise PaymentsUnavailable("payments aren't set up for this app (autorev rejected its key)")
            raise GatewayError(str(detail or f"payment service error ({r.status_code})"))
        return r.json()

    async def config(self) -> dict:
        return await self._call("GET", "/config")

    async def razorpay_setup(self, body: dict) -> dict:
        return await self._call("POST", "/razorpay/setup", body)

    async def razorpay_status(self, subscription_id: str) -> dict:
        return await self._call("GET", f"/razorpay/status/{subscription_id}")

    async def razorpay_revoke(self, subscription_id: str) -> dict:
        return await self._call("POST", f"/razorpay/revoke/{subscription_id}")


def sign(secret: str, body: bytes) -> str:
    """autorev's X-Autorev-Signature: sha256=<HMAC-SHA256 of the raw body>."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def validity_end(value: str | None) -> datetime | None:
    """autorev's paid-until date (YYYY-MM-DD, IST) as the end of that day."""
    if not value:
        return None
    try:
        d = date.fromisoformat(value)
    except ValueError:
        return None
    return datetime(d.year, d.month, d.day, tzinfo=IST) + timedelta(days=1)


def indian_mobile(raw: str | None) -> str | None:
    """10 digits starting 6-9 from "+91 98765 43210", "919876543210" or "9876543210"; else None."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits if re.fullmatch(r"[6-9]\d{9}", digits) else None


@dataclass
class Checkout:
    order: PaymentOrder
    plan: Plan
    razorpay: dict | None = None


# ---- the service --------------------------------------------------------------------------------


class PaymentService:
    def __init__(
        self,
        settings: Settings,
        sessions: async_sessionmaker[AsyncSession],
        http: httpx.AsyncClient,
        apps: AppService,
        billing: BillingService,
    ):
        self.settings, self.db, self.http, self.apps, self.billing = settings, sessions, http, apps, billing

    def client(self, app: App) -> AutorevClient:
        creds = self.apps.autorev_credentials(app)
        if creds is None:
            raise PaymentsUnavailable("payments aren't set up for this app yet")
        return AutorevClient(self.http, self.settings.autorev_url, *creds, self.settings.autorev_timeout_s)

    # ---- checkout ---------------------------------------------------------------------------------
    async def checkout(
        self,
        app: App,
        user: AppUser,
        plan_id: UUID,
        *,
        method: str = "upi",
        name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
    ) -> Checkout:
        if app.payment_provider != "razorpay":
            raise PaymentsUnavailable("payments aren't available in this app yet")
        client = self.client(app)
        plan = await self.billing.plan(app.id, plan_id)
        if plan.status != "active":
            raise ValidationFailed("this plan is archived", "plan_id")
        if plan.price_minor <= 0:
            raise ValidationFailed("this plan is free; there is nothing to pay", "plan_id")

        name = (name or user.name or "").strip() or "Customer"
        email = (email or user.email or "").strip()
        if not EMAIL_RE.match(email):
            raise ValidationFailed("enter your email address (the payment gateway needs one)", "email")
        mobile = indian_mobile(phone or user.phone)
        if mobile is None:
            raise ValidationFailed("enter your 10-digit mobile number", "phone")

        async with self.db.begin() as s:
            if await s.scalar(
                select(Subscription.id).where(
                    Subscription.app_user_id == user.id,
                    Subscription.status == "active",
                    Subscription.is_trial.is_(False),
                    Subscription.cancel_at_period_end.is_(False),
                )
            ):
                raise ConflictError("you already have a subscription")
            order = PaymentOrder(
                id=uuid.uuid4(),
                app_id=app.id,
                app_user_id=user.id,
                plan_id=plan.id,
                gateway="razorpay",
                amount_minor=plan.price_minor,
                currency=plan.currency,
                status="pending",
            )
            s.add(order)

        try:
            setup = await client.razorpay_setup(
                {
                    "name": name,
                    "email": email,
                    "phone_number": mobile,
                    "amount": plan.price_minor,
                    "max_amount": plan.price_minor,
                    "amount_type": "FIXED",
                    "frequency": "YEARLY" if plan.billing_period == "year" else "MONTHLY",
                    "method": method,
                    "external_ref": f"{REF_PREFIX}{order.id}",
                }
            )
        except ServiceError as e:
            await self._set_order(order.id, status="failed", error=e.message)
            raise

        key_id = setup.get("razorpay_key_id")
        if not key_id or not setup.get("razorpay_order_id"):
            await self._set_order(order.id, status="failed", error="autorev returned no checkout details")
            raise GatewayError("the payment service returned no checkout details")
        order = await self._set_order(
            order.id,
            autorev_subscription_id=setup["subscription_id"],
            gateway_order_id=setup["razorpay_order_id"],
        )
        return Checkout(
            order=order,
            plan=plan,
            razorpay={
                "key_id": key_id,
                "order_id": setup["razorpay_order_id"],
                "customer_id": setup.get("razorpay_customer_id") or "",
                "amount": int(setup.get("amount") or plan.price_minor),
                "currency": setup.get("currency") or plan.currency,
                "name": name,
                "email": email,
                "phone": mobile,
                "method": method,
            },
        )

    async def _set_order(self, order_id: UUID, **values) -> PaymentOrder:
        async with self.db.begin() as s:
            order = await s.get(PaymentOrder, order_id, with_for_update=True)
            for k, v in values.items():
                setattr(order, k, v)
            order.updated_at = func.now()
        async with self.db() as s:
            return await s.get(PaymentOrder, order_id)

    # ---- following an order -------------------------------------------------------------------------
    async def order(self, app: App, user: AppUser, order_id: UUID) -> tuple[PaymentOrder, Plan]:
        """The order, asking autorev first while it is pending."""
        async with self.db() as s:
            order = await s.get(PaymentOrder, order_id)
        if order is None or order.app_user_id != user.id or order.app_id != app.id:
            raise NotFoundError("order not found")
        if order.status == "pending" and order.autorev_subscription_id:
            try:
                status = await self.client(app).razorpay_status(order.autorev_subscription_id)
            except ServiceError as e:
                log.info("order %s: autorev status unavailable (%s)", order.id, e.message)
            else:
                await self._apply_state(app, order.autorev_subscription_id, status)
            async with self.db() as s:
                order = await s.get(PaymentOrder, order_id)
        async with self.db() as s:
            plan = await s.get(Plan, order.plan_id)
        return order, plan

    async def orders(self, app: App, user: AppUser, limit: int = 20) -> list[tuple[PaymentOrder, Plan]]:
        async with self.db() as s:
            rows = await s.execute(
                select(PaymentOrder, Plan)
                .join(Plan, Plan.id == PaymentOrder.plan_id)
                .where(PaymentOrder.app_user_id == user.id, PaymentOrder.app_id == app.id)
                .order_by(PaymentOrder.created_at.desc())
                .limit(min(max(limit, 1), 100))
            )
            return [(o, p) for o, p in rows]

    # ---- cancelling ---------------------------------------------------------------------------------
    async def cancel(self, app: App, user: AppUser) -> Subscription:
        """Stop renewing: revoke the mandate at autorev. The subscription (and its monthly credits)
        lasts to the end of the period already paid for."""
        async with self.db() as s:
            sub = await s.scalar(
                select(Subscription).where(
                    Subscription.app_user_id == user.id,
                    Subscription.status == "active",
                    Subscription.provider == "razorpay",
                )
            )
        if sub is None:
            raise NotFoundError("you have no paid subscription to cancel")
        if not sub.cancel_at_period_end and sub.provider_ref:
            try:
                await self.client(app).razorpay_revoke(sub.provider_ref)
            except GatewayError as e:
                if "already" not in e.message:  # autorev: 409 "Subscription is already CANCELLED"
                    raise
        async with self.db.begin() as s:
            locked = await s.get(Subscription, sub.id, with_for_update=True)
            locked.cancel_at_period_end = True
            locked.updated_at = func.now()
        async with self.db() as s:
            return await s.get(Subscription, sub.id)

    # ---- autorev's webhooks -----------------------------------------------------------------------
    async def handle_webhook(self, headers: dict[str, str], body: bytes) -> str:
        """Verify, record and apply one delivery. Returns what happened, for the log."""
        try:
            envelope = json.loads(body)
        except ValueError as e:
            raise ValidationFailed("body is not JSON") from e
        app = await self.apps.by_autorev_app(str(envelope.get("app_id") or ""))
        secret = self.apps.autorev_webhook_secret(app) if app else None
        if app is None or not secret:
            raise WebhookRejected("unknown autorev app, or no webhook secret saved for it")
        if not hmac.compare_digest(sign(secret, body), headers.get("x-autorev-signature", "")):
            raise WebhookRejected("signature mismatch")
        try:
            sent_at = int(headers.get("x-autorev-timestamp", "0"))
        except ValueError:
            sent_at = 0
        if abs(time.time() - sent_at) > WEBHOOK_MAX_AGE_S:
            raise WebhookRejected("stale or missing timestamp")

        event = str(envelope.get("event") or headers.get("x-autorev-event") or "")
        delivery_id = str(envelope.get("delivery_id") or headers.get("x-autorev-delivery") or "")
        if not delivery_id:
            raise ValidationFailed("delivery id missing")
        try:
            async with self.db.begin() as s:
                s.add(
                    PaymentEvent(
                        id=uuid.uuid4(), app_id=app.id, delivery_id=delivery_id, event=event, payload=envelope
                    )
                )
        except IntegrityError:
            return "duplicate"

        data = envelope.get("data") or {}
        if event == "webhook.test" or data.get("gateway", "razorpay") != "razorpay":
            return "ignored"
        sub_id = str(data.get("subscription_id") or "")
        try:
            if event in ("subscription.activated", "subscription.halted", "subscription.revoked"):
                await self._apply_state(app, sub_id, data)
            elif event == "subscription.next_payment_updated":
                await self._renew(sub_id, data)
            elif event == "subscription.payment_failed":
                log.info("autorev: a payment attempt failed for %s", sub_id)
            return event
        except Exception as e:
            log.exception("autorev webhook %s (%s) failed", event, delivery_id)
            async with self.db.begin() as s:
                await s.execute(
                    update(PaymentEvent).where(PaymentEvent.delivery_id == delivery_id).values(error=str(e))
                )
            raise

    # ---- applying autorev's state -------------------------------------------------------------------
    async def _apply_state(self, app: App, autorev_sub_id: str, data: dict) -> None:
        """Bring Studio in line with an autorev subscription's state (from a webhook or a status poll)."""
        state = data.get("state")
        if state == "ACTIVE":
            await self._activate(autorev_sub_id, data)
        elif state in ("HALTED", "CANCELLED"):
            await self._stop_renewing(autorev_sub_id, data)
        elif state == "FAILED":
            await self._fail_order(autorev_sub_id, "the payment wasn't authorised")

    async def _activate(self, autorev_sub_id: str, data: dict) -> None:
        async with self.db.begin() as s:
            order = await s.scalar(
                select(PaymentOrder)
                .where(PaymentOrder.autorev_subscription_id == autorev_sub_id)
                .with_for_update()
            )
            if order is None:
                log.warning("autorev: activation for unknown subscription %s", autorev_sub_id)
                return
            if order.status != "pending":
                return  # already applied (webhook and poll both report it)
            user = await s.scalar(select(AppUser).where(AppUser.id == order.app_user_id).with_for_update())
            plan = await s.get(Plan, order.plan_id)
            now = datetime.now(UTC)
            # a paid plan replaces a running free trial
            await s.execute(
                update(Subscription)
                .where(
                    Subscription.app_user_id == user.id,
                    Subscription.status == "active",
                    Subscription.is_trial.is_(True),
                )
                .values(status="cancelled", next_credit_grant_at=None, updated_at=func.now())
            )
            other = await s.scalar(
                select(Subscription).where(
                    Subscription.app_user_id == user.id, Subscription.status == "active"
                )
            )
            if other is not None:
                if other.cancel_at_period_end:  # resubscribing before the old one ran out
                    other.status = "cancelled"
                    other.next_credit_grant_at = None
                    other.updated_at = func.now()
                else:
                    order.status, order.error = "failed", "the user already has an active subscription"
                    order.updated_at = func.now()
                    log.error("autorev %s activated but user %s already subscribed", autorev_sub_id, user.id)
                    return
            end = validity_end(data.get("subscription_validity_end_date"))
            sub = await start_subscription(
                s,
                user,
                plan,
                provider="razorpay",
                provider_ref=autorev_sub_id,
                now=now,
                period_end=end if end and end > now else None,
            )
            order.status, order.subscription_id, order.error = "active", sub.id, None
            order.updated_at = func.now()
        log.info("autorev %s: subscription %s started", autorev_sub_id, sub.id)

    async def _renew(self, autorev_sub_id: str, data: dict) -> None:
        end = validity_end(data.get("subscription_validity_end_date"))
        if end is None:
            return
        now = datetime.now(UTC)
        async with self.db.begin() as s:
            sub = await s.scalar(
                select(Subscription)
                .where(Subscription.provider == "razorpay", Subscription.provider_ref == autorev_sub_id)
                .order_by(Subscription.created_at.desc())
                .limit(1)
                .with_for_update()
            )
            if sub is None:
                log.warning("autorev: renewal for unknown subscription %s", autorev_sub_id)
                return
            if sub.status == "cancelled":
                return
            if end > sub.current_period_end:
                sub.current_period_end = end
            if sub.status == "expired":  # the payment landed after access had run out
                sub.status = "active"
            sub.cancel_at_period_end = False
            if sub.next_credit_grant_at is None:
                sub.next_credit_grant_at = next_grant_after_extension(sub, now)
            sub.updated_at = func.now()

    async def _stop_renewing(self, autorev_sub_id: str, data: dict) -> None:
        """Halted (collection gave up) or revoked: no more renewals; access to the paid-up date."""
        await self._fail_order(autorev_sub_id, "the payment was cancelled before it went through")
        end = validity_end(data.get("subscription_validity_end_date"))
        async with self.db.begin() as s:
            sub = await s.scalar(
                select(Subscription)
                .where(
                    Subscription.provider == "razorpay",
                    Subscription.provider_ref == autorev_sub_id,
                    Subscription.status == "active",
                )
                .with_for_update()
            )
            if sub is None:
                return
            sub.cancel_at_period_end = True
            if end is not None and end < sub.current_period_end:
                sub.current_period_end = end
                if sub.next_credit_grant_at and sub.next_credit_grant_at >= end:
                    sub.next_credit_grant_at = None
            sub.updated_at = func.now()

    async def _fail_order(self, autorev_sub_id: str, error: str) -> None:
        async with self.db.begin() as s:
            await s.execute(
                update(PaymentOrder)
                .where(
                    PaymentOrder.autorev_subscription_id == autorev_sub_id, PaymentOrder.status == "pending"
                )
                .values(status="failed", error=error, updated_at=func.now())
            )

    # ---- console ------------------------------------------------------------------------------------
    async def test_connection(self, app: App) -> tuple[bool, str, dict]:
        try:
            config = await self.client(app).config()
        except ServiceError as e:
            return False, e.message, {}
        gateways = config.get("gateways") or {}
        if app.payment_provider != "none" and app.payment_provider not in gateways:
            return (
                False,
                f"connected, but {app.payment_provider} isn't switched on for this app in autorev",
                gateways,
            )
        gw = gateways.get(app.payment_provider) or {}
        if app.payment_provider != "none" and not gw.get("ready"):
            detail = f"connected, but {app.payment_provider}'s keys aren't saved in autorev yet"
            return False, detail, gateways
        mode = gw.get("environment")
        detail = f"connected to autorev app {config.get('name')}" + (f" ({mode})" if mode else "")
        return True, detail, gateways
