"""Several apps on one Razorpay account. Razorpay webhooks belong to the account, so one
registered webhook (any of those apps' URLs) must handle every app's events, and an event must
only ever touch the subscription it is about, even when apps share a Razorpay customer."""
import hashlib
import hmac
import json

import pytest

from app import webhooks
from app.models import App, RazorpayApp, RazorpaySubscription
from app.models.webhook import WebhookDelivery
from tests.conftest import APP_ID, AUTH, BASE, send_webhook
from tests.test_razorpay import SETUP

SIB_ID, SIB_KEY = "app_rzp_sibling", "s" * 32          # same Razorpay account as APP_ID
OTHER_ID, OTHER_KEY = "app_rzp_other", "o" * 32        # a different Razorpay account
SIB_SECRET = "whsec_sibling"


@pytest.fixture
def apps(db, monkeypatch):
    db.add(App(id=SIB_ID, slug="sibling", name="Sibling", api_key=SIB_KEY, razorpay_enabled=True))
    db.add(RazorpayApp(app_id=SIB_ID, razorpay_key_id="rzp_test_x", razorpay_key_secret="secret",
                       razorpay_webhook_secret=SIB_SECRET, razorpay_environment="TEST"))
    db.add(App(id=OTHER_ID, slug="other", name="Other", api_key=OTHER_KEY, razorpay_enabled=True))
    db.add(RazorpayApp(app_id=OTHER_ID, razorpay_key_id="rzp_test_other", razorpay_key_secret="secret2",
                       razorpay_environment="TEST"))
    for a in db.query(App).all():
        a.webhook_url, a.webhook_secret, a.webhook_enabled = f"https://{a.slug}.example.com/hook", "out", True
    db.commit()
    monkeypatch.setattr(webhooks, "enqueue", lambda ids: None)


def set_up(client, rzp, app_id, api_key, order, customer="cust_shared"):
    rzp.routes["POST /customers"] = {"id": customer}
    rzp.routes["POST /orders"] = {"id": order, "amount": 9900, "currency": "INR"}
    r = client.post(f"/api/v1/{app_id}/razorpay/setup", json=SETUP,
                    headers={"Authorization": f"Bearer {api_key}"})
    assert r.status_code == 200, r.text
    return r.json()["subscription_id"]


def send_to(client, app_id, secret, event):
    body = json.dumps(event).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(f"/api/v1/{app_id}/razorpay/webhook", content=body,
                       headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"})


def paid(order, token):
    return {"event": "order.paid", "payload": {"payment": {"entity": {
        "id": f"pay_{order}", "order_id": order, "token_id": token}}}}


def state(db, sub_id):
    db.expire_all()
    return db.get(RazorpaySubscription, sub_id).state


def test_one_webhook_activates_a_sibling_apps_subscription(db, client, rzp, apps):
    sib = set_up(client, rzp, SIB_ID, SIB_KEY, "order_sib")
    assert send_webhook(client, paid("order_sib", "token_sib")).status_code == 200  # APP_ID's URL
    assert state(db, sib) == "ACTIVE"
    assert db.get(RazorpaySubscription, sib).razorpay_token_id == "token_sib"
    [d] = db.query(WebhookDelivery).filter_by(event="subscription.activated").all()
    assert d.app_id == SIB_ID  # announced to the app that owns it, not the URL's app


def test_token_events_reach_a_sibling_app(db, client, rzp, apps):
    sib = set_up(client, rzp, SIB_ID, SIB_KEY, "order_sib")
    send_webhook(client, paid("order_sib", "token_sib"))
    send_webhook(client, {"event": "token.cancelled", "payload": {"token": {"entity": {
        "id": "token_sib", "customer_id": "cust_shared"}}}})
    assert state(db, sib) == "CANCELLED"


def test_another_razorpay_accounts_app_is_never_touched(db, client, rzp, apps):
    other = set_up(client, rzp, OTHER_ID, OTHER_KEY, "order_other")
    send_webhook(client, paid("order_other", "token_other"))
    assert state(db, other) in ("INITIATED", "AUTHORIZATION_PENDING")


def test_shared_customer_token_event_does_not_guess(db, client, rzp, apps):
    """Same contact in two apps → same Razorpay customer. A token event that names only the
    customer could belong to either pending signup, so it activates neither; the payment event
    (which carries the order) then activates exactly the right one."""
    mine = set_up(client, rzp, APP_ID, "k" * 32, "order_mine")
    sib = set_up(client, rzp, SIB_ID, SIB_KEY, "order_sib")
    before = (state(db, mine), state(db, sib))
    send_webhook(client, {"event": "token.confirmed", "payload": {"token": {"entity": {
        "id": "token_sib", "customer_id": "cust_shared"}}}})
    assert (state(db, mine), state(db, sib)) == before
    send_webhook(client, paid("order_sib", "token_sib"))
    assert (state(db, mine), state(db, sib)) == (before[0], "ACTIVE")


def test_same_event_on_two_registered_webhooks_is_applied_and_announced_once(db, client, rzp, apps):
    sib = set_up(client, rzp, SIB_ID, SIB_KEY, "order_sib")
    event = paid("order_sib", "token_sib")
    assert send_webhook(client, event).status_code == 200
    assert send_to(client, SIB_ID, SIB_SECRET, event).status_code == 200
    assert state(db, sib) == "ACTIVE"
    assert db.query(WebhookDelivery).filter_by(event="subscription.activated").count() == 1


def test_signature_is_checked_with_the_url_apps_secret(db, client, rzp, apps):
    set_up(client, rzp, SIB_ID, SIB_KEY, "order_sib")
    assert send_to(client, APP_ID, SIB_SECRET, paid("order_sib", "t")).status_code == 401


def test_single_app_token_fallback_still_activates(db, client, rzp, apps):
    """Unchanged: one pending signup for the customer, token event without a known token."""
    mine = set_up(client, rzp, APP_ID, "k" * 32, "order_mine", customer="cust_solo")
    send_webhook(client, {"event": "token.confirmed", "payload": {"token": {"entity": {
        "id": "token_mine", "customer_id": "cust_solo"}}}})
    assert state(db, mine) == "ACTIVE"
