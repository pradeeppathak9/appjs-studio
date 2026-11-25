"""Buying a plan (app clients), autorev's webhooks, and the console's connection test.
See studio/endusers/payments.py."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from studio.api.client_auth import me_out
from studio.api.schemas import (
    AppUserOut,
    CheckoutIn,
    PaymentOrderOut,
    PaymentTestOut,
    PlanRef,
    RazorpayCheckout,
)
from studio.apps.service import AppPrincipal
from studio.deps import AppState, admin, get_state, public, signed_in_app_user

app_router = APIRouter(prefix="/v1/app", tags=["app clients: payments"])
hooks = APIRouter(tags=["payments: autorev webhooks"], dependencies=[Depends(public())])
admin_router = APIRouter(prefix="/v1/admin", tags=["admin"], dependencies=[Depends(admin)])


def order_out(order, plan, razorpay: dict | None = None) -> PaymentOrderOut:
    return PaymentOrderOut(
        id=order.id,
        status=order.status,
        gateway=order.gateway,
        plan=PlanRef(id=plan.id, slug=plan.slug, name=plan.name),
        amount_minor=order.amount_minor,
        currency=order.currency,
        error=order.error,
        razorpay=RazorpayCheckout(**razorpay) if razorpay else None,
        created_at=order.created_at,
    )


@app_router.post("/subscriptions", response_model=PaymentOrderOut, status_code=201)
async def checkout(
    body: CheckoutIn, a: AppPrincipal = Depends(signed_in_app_user), state: AppState = Depends(get_state)
):
    """Start buying a plan. With `razorpay` in the answer, open Razorpay Checkout with `key_id`,
    `order_id`, `customer_id` and `recurring: "1"`; when it closes, poll
    `GET /subscriptions/orders/{id}` until `status` is no longer `pending`. 409 `payments_unavailable` if
    the app takes no payments yet, 409 `conflict` if the user already has a subscription, 422 if the
    gateway needs an email or mobile number the account doesn't have (send `email` / `phone`)."""
    c = await state.payments.checkout(
        a.app, a.user, body.plan_id, method=body.method, name=body.name, email=body.email, phone=body.phone
    )
    return order_out(c.order, c.plan, c.razorpay)


@app_router.get("/subscriptions/orders/{order_id}", response_model=PaymentOrderOut)
async def checkout_status(
    order_id: UUID, a: AppPrincipal = Depends(signed_in_app_user), state: AppState = Depends(get_state)
):
    """A checkout's status. `active`: the subscription started and its first credits are granted (see
    `GET /me`); `failed`: nothing was charged, `error` says why."""
    order, plan = await state.payments.order(a.app, a.user, order_id)
    return order_out(order, plan)


@app_router.get("/subscriptions/orders", response_model=list[PaymentOrderOut])
async def checkouts(
    limit: int = 20, a: AppPrincipal = Depends(signed_in_app_user), state: AppState = Depends(get_state)
):
    """The user's checkouts, newest first."""
    return [order_out(o, p) for o, p in await state.payments.orders(a.app, a.user, limit)]


@app_router.post("/subscriptions/current/cancel", response_model=AppUserOut)
async def cancel_subscription(
    a: AppPrincipal = Depends(signed_in_app_user), state: AppState = Depends(get_state)
):
    """Stop the paid subscription from renewing. It stays active, with its monthly credits, until
    `current_period_end` (`cancel_at_period_end` turns true). 404 if there is no paid subscription."""
    await state.payments.cancel(a.app, a.user)
    return await me_out(state, await state.endusers.get(a.app.id, a.user.id))


@hooks.post("/v1/webhooks/autorev", status_code=200)
async def autorev_webhook(request: Request, state: AppState = Depends(get_state)):
    """autorev's events for an app (set this URL and its signing secret in autorev → Settings →
    Webhooks, and the secret in Studio's Payments settings). Signed with `X-Autorev-Signature`."""
    body = await request.body()
    outcome = await state.payments.handle_webhook({k.lower(): v for k, v in request.headers.items()}, body)
    return {"status": "ok", "outcome": outcome}


@admin_router.post("/apps/{app_id}/payments/test", response_model=PaymentTestOut)
async def test_payments(app_id: UUID, state: AppState = Depends(get_state)):
    """Check the app's autorev connection: the API key works, the gateway is switched on there and
    its keys are saved."""
    app = await state.apps.get(app_id)
    ok, detail, gateways = await state.payments.test_connection(app)
    return PaymentTestOut(ok=ok, detail=detail, gateways=gateways)
