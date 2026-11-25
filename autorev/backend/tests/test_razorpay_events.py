"""Razorpay subscriptions announce themselves to the integration (outbound webhooks), carry the
integration's external_ref, and the server can run with Razorpay as its only gateway."""
from datetime import timedelta

import pytest

from app import webhooks
from app.api_handler.razorpay import RazorpayException
from app.config import settings
from app.models import App, RazorpaySubscription, RazorpayTransaction
from app.models.webhook import WebhookDelivery
from tests.conftest import APP_ID, AUTH, BASE, send_webhook
from tests.test_razorpay import NOW, TODAY, active_sub, charge_routes, collect, set_up

HOOK_SECRET = "whsec_out"


@pytest.fixture
def hooks(db, monkeypatch):
    """Subscribe the app to every event and record what would be sent (no broker)."""
    app = db.get(App, APP_ID)
    app.webhook_url, app.webhook_secret, app.webhook_enabled = "https://studio.example.com/hook", HOOK_SECRET, True
    db.commit()
    sent: list[str] = []
    monkeypatch.setattr(webhooks, "enqueue", lambda ids: sent.extend(ids))
    return sent


def deliveries(db, event=None):
    q = db.query(WebhookDelivery)
    if event:
        q = q.filter(WebhookDelivery.event == event)
    return q.all()


def activate_via_status(client, rzp, sub_id):
    rzp.routes["GET /orders/order_auth"] = {"id": "order_auth", "status": "paid"}
    rzp.routes["GET /orders/order_auth/payments"] = {"items": [{"id": "pay_a", "status": "captured", "token_id": "token_new"}]}
    return client.get(f"{BASE}/status/{sub_id}", headers=AUTH)


# ── external_ref ──────────────────────────────────────────────────────────────

def test_external_ref_and_key_id_round_trip(db, client, rzp):
    rzp.routes["POST /customers"] = {"id": "cust_1"}
    rzp.routes["POST /orders"] = {"id": "order_auth", "amount": 9900, "currency": "INR"}
    r = client.post(f"{BASE}/setup", json={
        "name": "Jane Doe", "email": "jane@example.com", "phone_number": "9876543210",
        "amount": 9900, "max_amount": 9900, "frequency": "MONTHLY", "external_ref": "studio:order-1",
    }, headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["external_ref"] == "studio:order-1"
    assert body["razorpay_key_id"] == "rzp_test_x"
    assert activate_via_status(client, rzp, body["subscription_id"]).json()["external_ref"] == "studio:order-1"


# ── state events ──────────────────────────────────────────────────────────────

def test_activation_is_announced_once_with_the_external_ref(db, client, rzp, hooks):
    sub_id = set_up(client, rzp, external_ref="studio:order-2")
    assert activate_via_status(client, rzp, sub_id).json()["state"] == "ACTIVE"
    activate_via_status(client, rzp, sub_id)  # polled again: nothing new
    [d] = deliveries(db, "subscription.activated")
    assert d.object_id == sub_id and hooks == [d.id]
    data = d.payload["data"]
    assert data["gateway"] == "razorpay" and data["external_ref"] == "studio:order-2"
    assert data["state"] == "ACTIVE" and data["subscription_validity_end_date"]


def test_webhook_activation_is_announced(db, client, rzp, hooks):
    sub_id = set_up(client, rzp)
    send_webhook(client, {"event": "order.paid", "payload": {
        "payment": {"entity": {"id": "pay_1", "order_id": "order_auth", "token_id": "token_new"}},
    }})
    assert [d.object_id for d in deliveries(db, "subscription.activated")] == [sub_id]


def test_revoke_is_announced(db, client, rzp, hooks):
    sub_id = active_sub(db, client, rzp, due=TODAY + timedelta(days=10))
    rzp.routes["POST /customers/cust_1/tokens/token_new/cancel"] = {"status": "cancelled"}
    assert client.post(f"{BASE}/revoke/{sub_id}", headers=AUTH).json()["state"] == "CANCELLED"
    [d] = deliveries(db, "subscription.revoked")
    assert d.payload["data"]["state"] == "CANCELLED"


def test_customer_cancelling_the_token_is_announced(db, client, rzp, hooks):
    sub_id = active_sub(db, client, rzp, due=TODAY + timedelta(days=10))
    send_webhook(client, {"event": "token.cancelled",
                          "payload": {"token": {"entity": {"id": "token_new", "customer_id": "cust_1"}}}})
    assert [d.object_id for d in deliveries(db, "subscription.revoked")] == [sub_id]


# ── collection events ─────────────────────────────────────────────────────────

def test_a_captured_collection_announces_the_next_date(db, client, rzp, hooks):
    sub_id = active_sub(db, client, rzp, due=TODAY)
    charge_routes(rzp)
    collect(db)
    captured = {"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_charge", "order_id": "order_charge"}}}}
    send_webhook(client, captured)
    send_webhook(client, captured)  # Razorpay redelivers
    [d] = deliveries(db, "subscription.next_payment_updated")
    data = d.payload["data"]
    assert data["previous_payment_date"] == TODAY.isoformat()
    assert data["next_payment_date"] > data["previous_payment_date"]
    assert d.object_id.startswith(f"{sub_id}:")


def test_failed_attempts_and_the_halt_are_announced(db, client, rzp, hooks):
    sub_id = active_sub(db, client, rzp, due=TODAY)
    rzp.routes["POST /orders"] = {"id": "order_charge"}
    rzp.routes["POST /payments/create/recurring"] = RazorpayException("declined")

    for _ in range(3):
        collect(db)
        for t in db.query(RazorpayTransaction).all():  # make the next attempt due
            t.created_at = NOW - timedelta(days=2)
        db.commit()
    assert len(deliveries(db, "subscription.payment_failed")) == 3
    collect(db)
    assert db.get(RazorpaySubscription, sub_id).state == "HALTED"
    [d] = deliveries(db, "subscription.halted")
    assert d.payload["data"]["last_payment_status"] == "FAILED"


def test_nothing_is_claimed_without_a_webhook_configured(db, client, rzp, monkeypatch):
    monkeypatch.setattr(webhooks, "enqueue", lambda ids: None)
    sub_id = set_up(client, rzp)
    activate_via_status(client, rzp, sub_id)
    assert deliveries(db) == []


# ── integration config and the gateway switch ─────────────────────────────────

def test_app_config_for_integrations(db, client):
    r = client.get(f"/api/v1/{APP_ID}/config", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["gateways"] == {"razorpay": {"key_id": "rzp_test_x", "environment": "TEST", "ready": True}}
    assert client.get(f"/api/v1/{APP_ID}/config", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_razorpay_only_server(db, client, monkeypatch):
    monkeypatch.setattr(settings, "gateways", "razorpay")
    assert client.get("/api/config").json() == {"gateways": ["razorpay"]}

    from app.router import admin as admin_router

    with pytest.raises(Exception) as e:
        admin_router._check_gateways_offered(phonepe=True, razorpay=False)
    assert "PhonePe is not offered" in str(e.value.detail)
    admin_router._check_gateways_offered(phonepe=False, razorpay=True)


def test_razorpay_only_beat_schedule(monkeypatch):
    import importlib
    import os
    import sys

    workers_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../workers"))
    monkeypatch.setenv("AUTOREV_GATEWAYS", "razorpay")
    monkeypatch.syspath_prepend(workers_dir)
    sys.modules.pop("phone_worker", None)
    try:
        worker = importlib.import_module("phone_worker")
        tasks = {e["task"] for e in worker.celery_app.conf.beat_schedule.values()}
    finally:
        sys.modules.pop("phone_worker", None)
    assert {"razorpay-collect-due", "razorpay-reconcile", "autorev-webhook-maintenance"} <= tasks
    assert not any(t.startswith("phonepe-") for t in tasks)


def test_webhook_payload_samples_follow_the_apps_gateway():
    sample = webhooks.sample_payload("subscription.activated", "a1", "Restyle", "razorpay")
    assert sample["data"]["gateway"] == "razorpay" and "external_ref" in sample["data"]
    assert webhooks.sample_payload("subscription.halted", "a1", "Restyle")["data"]["state"] == "HALTED"
    assert webhooks.sample_payload("subscription.activated", "a1", "M")["data"]["gateway"] == "phonepe"

