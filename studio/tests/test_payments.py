"""Buying plans through autorev: checkout, activation (by polling or webhook), renewals, stops,
cancelling, and the console's connection test. autorev's API is mocked with respx."""

import json
import time
import uuid
from datetime import datetime, timedelta

import httpx
import pytest
import respx

from studio.endusers.payments import IST, sign
from tests.conftest import app_client, sign_in_phone
from tests.test_billing import MONTHLY
from tests.test_provider_keys import secrets_key  # noqa: F401

pytestmark = pytest.mark.usefixtures("secrets_key")  # app secrets are stored encrypted

AUTOREV_APP = "a1b2c3d4e5f6a7b8"
HOOK_SECRET = "whsec_" + "h" * 32


@pytest.fixture
def autorev(state):
    base = f"{state.settings.autorev_url}/api/v1/{AUTOREV_APP}"
    with respx.mock(base_url=base, assert_all_called=False) as mock:
        mock.base = base
        yield mock


async def paying_app(app, state, admin, autorev, **plan):
    """An app that sells MONTHLY through autorev, and a signed-in phone user."""
    c = await app_client(app, state, require_login=True)
    url = f"/v1/admin/apps/{c.app_row.id}"
    r = await admin.patch(
        url,
        json={
            "payment_provider": "razorpay",
            "autorev_app_id": AUTOREV_APP,
            "autorev_api_key": "k" * 64,
            "autorev_webhook_secret": HOOK_SECRET,
        },
    )
    assert r.status_code == 200, r.text
    c.plan = (await admin.post(f"{url}/plans", json={**MONTHLY, **plan})).json()
    await sign_in_phone(c, state)
    return c


def setup_route(autorev, sub_id="rzsub_1"):
    return autorev.post("/razorpay/setup").mock(
        return_value=httpx.Response(
            200,
            json={
                "subscription_id": sub_id,
                "external_ref": "ignored-here",
                "razorpay_key_id": "rzp_test_Ab12Cd34Ef",
                "razorpay_customer_id": "cust_1",
                "razorpay_order_id": "order_1",
                "amount": 19900,
                "currency": "INR",
            },
        )
    )


async def checkout(c, autorev, **body):
    setup_route(autorev)
    r = await c.post(
        "/v1/app/subscriptions", json={"plan_id": c.plan["id"], "email": "jane@example.com", **body}
    )
    assert r.status_code == 201, r.text
    return r.json()


def paid_until(days=36) -> str:
    return (datetime.now(IST).date() + timedelta(days=days)).isoformat()


def status(state="ACTIVE", days=36):
    return httpx.Response(
        200,
        json={
            "subscription_id": "rzsub_1",
            "state": state,
            "subscription_validity_end_date": paid_until(days) if state != "AUTHORIZATION_PENDING" else None,
        },
    )


async def webhook(c, event, data, delivery=None, secret=HOOK_SECRET, at=None):
    body = json.dumps(
        {
            "event": event,
            "delivery_id": delivery or uuid.uuid4().hex,
            "app_id": AUTOREV_APP,
            "app_name": "Restyle",
            "data": {"gateway": "razorpay", "subscription_id": "rzsub_1", **data},
        }
    ).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Autorev-Signature": sign(secret, body),
        "X-Autorev-Timestamp": str(int(at if at is not None else time.time())),
    }
    anon = httpx.AsyncClient(transport=c._transport, base_url=str(c.base_url))
    return await anon.post("/v1/webhooks/autorev", content=body, headers=headers)


async def me(c):
    return (await c.get("/v1/app/me")).json()


# ---- checkout ------------------------------------------------------------------------------------------


async def test_checkout_asks_autorev_and_hands_back_razorpay_details(app, state, admin, autorev):
    c = await paying_app(app, state, admin, autorev)
    order = await checkout(c, autorev, method="card")
    assert order["status"] == "pending" and order["plan"]["slug"] == "monthly"
    assert order["razorpay"] == {
        "key_id": "rzp_test_Ab12Cd34Ef",
        "order_id": "order_1",
        "customer_id": "cust_1",
        "amount": 19900,
        "currency": "INR",
        "name": "Customer",
        "email": "jane@example.com",
        "phone": "9876543210",
        "method": "card",
    }
    sent = json.loads(autorev.calls.last.request.content)
    assert sent["external_ref"] == f"studio:{order['id']}"
    assert sent["notes"] == {
        "app": c.app_row.slug,
        "app_name": c.app_row.name,
        "plan": "monthly",
        "studio_order": order["id"],
        "studio_user": c.user_id,
    }
    assert (sent["amount"], sent["max_amount"], sent["frequency"], sent["amount_type"]) == (
        19900,
        19900,
        "MONTHLY",
        "FIXED",
    )
    assert autorev.calls.last.request.headers["authorization"] == "Bearer " + "k" * 64


async def test_checkout_needs_payments_set_up_and_contact_details(app, state, admin, autorev):
    c = await app_client(app, state, require_login=True)
    await sign_in_phone(c, state)
    plan = (await admin.post(f"/v1/admin/apps/{c.app_row.id}/plans", json=MONTHLY)).json()
    r = await c.post("/v1/app/subscriptions", json={"plan_id": plan["id"], "email": "a@b.co"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "payments_unavailable"

    await admin.patch(
        f"/v1/admin/apps/{c.app_row.id}",
        json={"payment_provider": "razorpay", "autorev_app_id": AUTOREV_APP, "autorev_api_key": "k" * 64},
    )
    r = await c.post("/v1/app/subscriptions", json={"plan_id": plan["id"]})  # phone user, no email
    assert r.status_code == 422 and r.json()["error"]["field"] == "email"
    r = await c.post("/v1/app/subscriptions", json={"plan_id": plan["id"], "email": "a@b.co", "phone": "123"})
    assert r.status_code == 422 and r.json()["error"]["field"] == "phone"
    assert not autorev.calls  # nothing was sent to autorev


async def test_autorev_errors_fail_the_order(app, state, admin, autorev):
    c = await paying_app(app, state, admin, autorev)
    autorev.post("/razorpay/setup").mock(
        return_value=httpx.Response(502, json={"detail": "Razorpay error: x"})
    )
    r = await c.post("/v1/app/subscriptions", json={"plan_id": c.plan["id"], "email": "a@b.co"})
    assert r.status_code == 502 and "Razorpay error" in r.json()["error"]["message"]
    [order] = (await c.get("/v1/app/subscriptions/orders")).json()
    assert order["status"] == "failed"


# ---- activation ----------------------------------------------------------------------------------------


async def test_polling_activates_and_grants_the_first_month(app, state, admin, autorev):
    c = await paying_app(app, state, admin, autorev)
    order = await checkout(c, autorev)
    autorev.get("/razorpay/status/rzsub_1").mock(return_value=status("AUTHORIZATION_PENDING"))
    assert (await c.get(f"/v1/app/subscriptions/orders/{order['id']}")).json()["status"] == "pending"

    autorev.get("/razorpay/status/rzsub_1").mock(return_value=status("ACTIVE"))
    assert (await c.get(f"/v1/app/subscriptions/orders/{order['id']}")).json()["status"] == "active"
    # polled again, or the webhook arrives too: applied once
    await c.get(f"/v1/app/subscriptions/orders/{order['id']}")
    r = await webhook(
        c, "subscription.activated", {"state": "ACTIVE", "subscription_validity_end_date": paid_until()}
    )
    assert r.status_code == 200
    user = await me(c)
    assert user["credits"] == MONTHLY["credits_per_month"]
    sub = user["subscription"]
    assert (sub["provider"], sub["status"], sub["cancel_at_period_end"]) == ("razorpay", "active", False)
    assert sub["current_period_end"].startswith(paid_until())


async def test_a_paid_plan_replaces_the_free_trial(app, state, admin, autorev):
    c = await paying_app(app, state, admin, autorev, trial_enabled=True, trial_credits=5)
    assert (await c.post("/v1/app/me/trial", json={"plan_id": c.plan["id"]})).status_code == 201
    await checkout(c, autorev)
    await webhook(
        c, "subscription.activated", {"state": "ACTIVE", "subscription_validity_end_date": paid_until()}
    )
    user = await me(c)
    assert user["subscription"]["trial"] is False and user["credits"] == 5 + MONTHLY["credits_per_month"]


async def test_webhooks_are_verified_and_applied_once(app, state, admin, autorev):
    c = await paying_app(app, state, admin, autorev)
    await checkout(c, autorev)
    data = {"state": "ACTIVE", "subscription_validity_end_date": paid_until()}
    assert (await webhook(c, "subscription.activated", data, secret="wrong")).status_code == 401
    assert (await webhook(c, "subscription.activated", data, at=time.time() - 7200)).status_code == 401
    assert (await me(c))["subscription"] is None

    r = await webhook(c, "subscription.activated", data, delivery="d1")
    assert r.json()["outcome"] == "subscription.activated"
    assert (await webhook(c, "subscription.activated", data, delivery="d1")).json()["outcome"] == "duplicate"
    assert (await me(c))["credits"] == MONTHLY["credits_per_month"]


# ---- after activation ----------------------------------------------------------------------------------


async def active(c, autorev):
    await checkout(c, autorev)
    await webhook(
        c, "subscription.activated", {"state": "ACTIVE", "subscription_validity_end_date": paid_until()}
    )


async def test_renewals_extend_the_paid_period(app, state, admin, autorev):
    c = await paying_app(app, state, admin, autorev)
    await active(c, autorev)
    await webhook(
        c,
        "subscription.next_payment_updated",
        {"state": "ACTIVE", "subscription_validity_end_date": paid_until(66)},
    )
    assert (await me(c))["subscription"]["current_period_end"].startswith(paid_until(66))


async def test_halted_collection_stops_renewal_at_the_paid_date(app, state, admin, autorev):
    c = await paying_app(app, state, admin, autorev)
    await active(c, autorev)
    await webhook(
        c, "subscription.halted", {"state": "HALTED", "subscription_validity_end_date": paid_until(30)}
    )
    sub = (await me(c))["subscription"]
    assert sub["status"] == "active" and sub["cancel_at_period_end"] is True
    assert sub["current_period_end"].startswith(paid_until(30))
    # a retry that went through after all puts it back
    await webhook(
        c,
        "subscription.next_payment_updated",
        {"state": "ACTIVE", "subscription_validity_end_date": paid_until(60)},
    )
    assert (await me(c))["subscription"]["cancel_at_period_end"] is False


async def test_users_cancel_and_keep_the_paid_period(app, state, admin, autorev):
    c = await paying_app(app, state, admin, autorev)
    await active(c, autorev)
    revoke = autorev.post("/razorpay/revoke/rzsub_1").mock(
        return_value=httpx.Response(200, json={"subscription_id": "rzsub_1", "state": "CANCELLED"})
    )
    r = await c.post("/v1/app/subscriptions/current/cancel")
    assert r.status_code == 200, r.text
    assert revoke.called
    sub = r.json()["subscription"]
    assert sub["status"] == "active" and sub["cancel_at_period_end"] is True
    # autorev's revoked event changes nothing more
    await webhook(
        c, "subscription.revoked", {"state": "CANCELLED", "subscription_validity_end_date": paid_until(30)}
    )
    assert (await me(c))["subscription"]["status"] == "active"
    # and the user can subscribe again (a new autorev subscription)
    setup_route(autorev, "rzsub_2")
    r = await c.post("/v1/app/subscriptions", json={"plan_id": c.plan["id"], "email": "a@b.co"})
    assert r.status_code == 201 and r.json()["status"] == "pending"


async def test_no_second_subscription(app, state, admin, autorev):
    c = await paying_app(app, state, admin, autorev)
    await active(c, autorev)
    r = await c.post("/v1/app/subscriptions", json={"plan_id": c.plan["id"], "email": "a@b.co"})
    assert r.status_code == 409


# ---- console -------------------------------------------------------------------------------------------


async def test_admins_test_the_connection(app, state, admin, autorev):
    c = await paying_app(app, state, admin, autorev)
    route = autorev.get("/config")
    route.mock(
        return_value=httpx.Response(
            200,
            json={
                "app_id": AUTOREV_APP,
                "name": "Restyle",
                "gateways": {"razorpay": {"key_id": "rzp_test_x", "environment": "TEST", "ready": True}},
            },
        )
    )
    r = await admin.post(f"/v1/admin/apps/{c.app_row.id}/payments/test")
    assert r.json()["ok"] is True and "TEST" in r.json()["detail"]
    route.mock(return_value=httpx.Response(401, json={"detail": "Invalid API key"}))
    r = await admin.post(f"/v1/admin/apps/{c.app_row.id}/payments/test")
    assert r.json()["ok"] is False


def test_dates_follow_autorev():
    from studio.endusers.payments import indian_mobile, validity_end

    assert validity_end("2026-12-31") == datetime(2027, 1, 1, tzinfo=IST)
    assert validity_end(None) is None and validity_end("nope") is None
    assert [indian_mobile(x) for x in ("+91 98765 43210", "919876543210", "9876543210", "12345")] == [
        "9876543210",
        "9876543210",
        "9876543210",
        None,
    ]
