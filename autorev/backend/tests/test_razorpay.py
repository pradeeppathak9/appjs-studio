from datetime import date, datetime, timedelta, timezone

from app import razorpay_billing as billing
from app.models import RazorpaySubscription, RazorpayTransaction
from tests.conftest import APP_ID, AUTH, BASE, send_webhook

SETUP = {
    "name": "Jane Doe", "email": "jane@example.com", "phone_number": "9876543210",
    "amount": 9900, "max_amount": 49900, "frequency": "MONTHLY", "method": "upi",
}


def ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


def set_up(client, rzp, **overrides):
    rzp.routes["POST /customers"] = {"id": "cust_1"}
    rzp.routes["POST /orders"] = {"id": "order_auth", "amount": 9900, "currency": "INR"}
    r = client.post(f"{BASE}/setup", json={**SETUP, **overrides}, headers=AUTH)
    assert r.status_code == 200, r.text
    return r.json()["subscription_id"]


def active_sub(db, client, rzp, *, due: date, token="token_new"):
    sub_id = set_up(client, rzp)
    sub = db.get(RazorpaySubscription, sub_id)
    sub.state, sub.razorpay_token_id, sub.next_payment_date = "ACTIVE", token, ms(due)
    db.commit()
    return sub_id


# ── setup ─────────────────────────────────────────────────────────────────────

def test_upi_setup_sends_token_frequency(client, rzp):
    set_up(client, rzp)
    order = rzp.sent("POST", "/orders")[0]
    assert order["method"] == "upi"
    assert order["token"]["frequency"] == "monthly"
    assert order["token"]["max_amount"] == 49900


def test_on_demand_maps_to_as_presented(client, rzp):
    set_up(client, rzp, frequency="ON_DEMAND")
    assert rzp.sent("POST", "/orders")[0]["token"]["frequency"] == "as_presented"


def test_setup_requires_email_and_amount_within_max(client, rzp):
    no_email = {k: v for k, v in SETUP.items() if k != "email"}
    assert client.post(f"{BASE}/setup", json=no_email, headers=AUTH).status_code == 422
    r = client.post(f"{BASE}/setup", json={**SETUP, "amount": 50000}, headers=AUTH)
    assert r.status_code == 400 and "max_amount" in r.json()["detail"]
    assert rzp.calls == []  # rejected before touching Razorpay


# ── activation picks this order's token ───────────────────────────────────────

def test_status_activates_with_the_authorisation_payments_token(db, client, rzp):
    sub_id = set_up(client, rzp)
    rzp.routes["GET /orders/order_auth"] = {"id": "order_auth", "status": "paid"}
    rzp.routes["GET /orders/order_auth/payments"] = {"items": [
        {"id": "pay_a", "status": "failed", "token_id": None},
        {"id": "pay_b", "status": "captured", "token_id": "token_new"},
    ]}
    r = client.get(f"{BASE}/status/{sub_id}", headers=AUTH)
    assert r.json()["state"] == "ACTIVE"
    assert r.json()["razorpay_token_id"] == "token_new"
    # the customer's token list (which may hold older tokens) was not needed
    assert rzp.sent("GET", "/customers/cust_1/tokens") == []
    assert db.get(RazorpaySubscription, sub_id).next_payment_date is not None


def test_status_falls_back_to_the_newest_token(client, rzp):
    sub_id = set_up(client, rzp)
    rzp.routes["GET /orders/order_auth"] = {"status": "paid"}
    rzp.routes["GET /orders/order_auth/payments"] = {"items": []}
    rzp.routes["GET /customers/cust_1/tokens"] = {"items": [
        {"id": "token_old", "created_at": 1_600_000_000},
        {"id": "token_new", "created_at": 1_700_000_000},
    ]}
    assert client.get(f"{BASE}/status/{sub_id}", headers=AUTH).json()["razorpay_token_id"] == "token_new"


# ── webhook ───────────────────────────────────────────────────────────────────

def test_webhook_checks_the_signature(client, db):
    assert send_webhook(client, {"event": "noop", "payload": {}}).status_code == 200
    assert send_webhook(client, {"event": "noop", "payload": {}}, secret="wrong").status_code == 401


def test_order_paid_activates_with_the_payments_token(db, client, rzp):
    sub_id = set_up(client, rzp)
    r = send_webhook(client, {"event": "order.paid", "payload": {
        "payment": {"entity": {"id": "pay_1", "order_id": "order_auth", "token_id": "token_new"}},
    }})
    assert r.status_code == 200
    sub = db.get(RazorpaySubscription, sub_id)
    db.refresh(sub)
    assert (sub.state, sub.razorpay_token_id) == ("ACTIVE", "token_new")


def test_token_events(db, client, rzp):
    sub_id = set_up(client, rzp)
    # confirmed before we knew the token: matched by customer, then activated
    send_webhook(client, {"event": "token.confirmed", "payload": {"token": {"entity": {"id": "token_new", "customer_id": "cust_1"}}}})
    sub = db.get(RazorpaySubscription, sub_id)
    db.refresh(sub)
    assert (sub.state, sub.razorpay_token_id) == ("ACTIVE", "token_new")
    send_webhook(client, {"event": "token.cancelled", "payload": {"token": {"entity": {"id": "token_new", "customer_id": "cust_1"}}}})
    db.refresh(sub)
    assert sub.state == "CANCELLED"
    assert billing.next_action(db, sub, datetime.now(timezone.utc)) == "skip"


# ── collecting (AutoRev's worker, not the caller) ─────────────────────────────

def test_caller_collection_endpoints_are_withdrawn(db, client, rzp):
    sub_id = active_sub(db, client, rzp, due=date.today())
    assert client.post(f"{BASE}/notify-redemption/{sub_id}", headers=AUTH).status_code == 410
    assert client.post(f"{BASE}/execute-redemption/x", headers=AUTH).status_code == 410


NOW = datetime(2026, 11, 5, 4, 0, tzinfo=timezone.utc)  # 09:30 IST, 5 Nov
TODAY = date(2026, 11, 5)


def handler():
    from app.api_handler.razorpay import RazorpayAPIHandler
    return RazorpayAPIHandler("k", "s")


def charge_routes(rzp, order="order_charge", pay="pay_charge"):
    rzp.routes["POST /orders"] = {"id": order}
    rzp.routes["POST /payments/create/recurring"] = {"razorpay_payment_id": pay}


def age(db, txn_id, hours):
    txn = db.get(RazorpayTransaction, txn_id)
    txn.created_at = NOW - timedelta(hours=hours)
    db.commit()


def collect(db):
    return billing.collect_due(db, handler(), APP_ID, now=NOW)


def test_collects_a_day_ahead_and_only_once(db, client, rzp):
    due_tomorrow = active_sub(db, client, rzp, due=TODAY + timedelta(days=1))
    later = active_sub(db, client, rzp, due=TODAY + timedelta(days=3))
    charge_routes(rzp)
    counts = collect(db)
    assert counts["collect"] == 1
    txn = db.query(RazorpayTransaction).filter_by(subscription_id=due_tomorrow).one()
    assert txn.state == "INITIATED" and txn.razorpay_payment_id == "pay_charge"
    assert txn.payment_due_date == ms(TODAY + timedelta(days=1))
    assert rzp.sent("POST", "/orders")[-1]["payment_capture"] is True
    charge = rzp.sent("POST", "/payments/create/recurring")[0]
    assert (charge["email"], charge["contact"], charge["token"]) == ("jane@example.com", "+919876543210", "token_new")
    assert db.query(RazorpayTransaction).filter_by(subscription_id=later).count() == 0
    # the next hourly run waits for the one in flight
    assert collect(db)["wait"] == 1
    assert len(rzp.sent("POST", "/payments/create/recurring")) == 1


def test_capture_settles_and_moves_the_cycle_from_the_due_date(db, client, rzp):
    due = TODAY + timedelta(days=1)
    sub_id = active_sub(db, client, rzp, due=due)
    charge_routes(rzp)
    collect(db)
    captured = {"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_charge", "order_id": "order_charge"}}}}
    send_webhook(client, captured)
    send_webhook(client, captured)  # redelivered: applied once
    sub = db.get(RazorpaySubscription, sub_id)
    db.refresh(sub)
    assert sub.total_payments == 1 and sub.last_payment_status == "SUCCESS"
    assert sub.next_payment_date == ms(date(2026, 12, 6))  # one month after 6 Nov, not after 5 Nov
    status = client.get(f"{BASE}/9876543210/status", headers=AUTH).json()
    assert status["next_payment_date"] == "2026-12-06"
    assert status["subscription_validity_end_date"] == "2026-12-12"  # plus the 6-day grace
    # paid: nothing more to collect this cycle
    assert collect(db)["collect"] == 0


def test_retries_daily_then_halts(db, client, rzp):
    sub_id = active_sub(db, client, rzp, due=TODAY)
    rzp.routes["POST /orders"] = {"id": "order_charge"}
    rzp.routes["POST /payments/create/recurring"] = {"razorpay_payment_id": "pay_charge"}
    for attempt in range(3):
        assert collect(db)["collect"] == 1, attempt
        txn = db.query(RazorpayTransaction).filter_by(subscription_id=sub_id).order_by(RazorpayTransaction.created_at.desc()).first()
        billing.apply_failure(txn)
        db.commit()
        if attempt < 2:
            assert collect(db)["wait"] == 1  # not again within 24 hours
            age(db, txn.id, 25 + attempt)
    # the third failure ends the cycle at once: no waiting for a fourth attempt
    assert collect(db)["halt"] == 1
    sub = db.get(RazorpaySubscription, sub_id)
    db.refresh(sub)
    assert sub.state == "HALTED"
    # paid up to the due date that was never collected, without the grace
    assert billing.validity_end_date(sub) == TODAY.isoformat()


def test_charge_rejected_by_razorpay_is_a_failed_attempt(db, client, rzp):
    from app.api_handler.razorpay import RazorpayException
    sub_id = active_sub(db, client, rzp, due=TODAY)
    rzp.routes["POST /orders"] = {"id": "order_charge"}
    rzp.routes["POST /payments/create/recurring"] = RazorpayException("token not confirmed")
    collect(db)
    txn = db.query(RazorpayTransaction).filter_by(subscription_id=sub_id).one()
    assert txn.state == "FAILED" and txn.response_payload["stage"] == "charge"
    sub = db.get(RazorpaySubscription, sub_id)
    db.refresh(sub)
    assert sub.last_payment_status == "FAILED" and sub.state == "ACTIVE"  # retried tomorrow


def test_reconcile_settles_what_the_webhook_missed(db, client, rzp):
    captured_sub = active_sub(db, client, rzp, due=TODAY)
    charge_routes(rzp)
    collect(db)
    captured = db.query(RazorpayTransaction).filter_by(subscription_id=captured_sub).one()
    age(db, captured.id, 7)
    rzp.routes["GET /payments/pay_charge"] = {"id": "pay_charge", "status": "captured"}

    # a charge order the worker created but died before charging
    abandoned = RazorpayTransaction(id="abandoned", subscription_id=captured_sub, amount=9900, state="NOTIFIED",
                                    razorpay_order_id="order_lost", payment_due_date=ms(TODAY))
    db.add(abandoned)
    db.commit()
    age(db, "abandoned", 2)
    rzp.routes["GET /orders/order_lost/payments"] = {"items": []}

    counts = billing.reconcile(db, handler(), APP_ID, now=NOW)
    assert counts == {"success": 1, "failed": 1, "pending": 0}
    db.refresh(captured)
    assert captured.state == "SUCCESS"
    assert db.get(RazorpayTransaction, "abandoned").state == "FAILED"


def test_user_status_prefers_the_collecting_subscription(db, client, rzp):
    active_id = active_sub(db, client, rzp, due=TODAY + timedelta(days=10))
    set_up(client, rzp)  # a newer one, still awaiting authorisation
    status = client.get(f"{BASE}/9876543210/status", headers=AUTH).json()
    assert status["subscription_id"] == active_id and status["state"] == "ACTIVE"
    assert status["subscription_validity_end_date"] == (TODAY + timedelta(days=16)).isoformat()


# ── revoke ────────────────────────────────────────────────────────────────────

def test_revoke_cancels_the_token(db, client, rzp):
    sub_id = active_sub(db, client, rzp, due=date.today())
    rzp.routes["POST /customers/cust_1/tokens/token_new/cancel"] = {"id": "token_new", "status": "cancelled"}
    r = client.post(f"{BASE}/revoke/{sub_id}", headers=AUTH)
    assert r.json() == {"subscription_id": sub_id, "external_ref": None, "state": "CANCELLED"}
    assert client.post(f"{BASE}/revoke/{sub_id}", headers=AUTH).status_code == 409


def test_workers_skip_without_redis_or_queries_when_gateway_disabled(db, monkeypatch):
    import os
    import sys

    workers_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../workers"))
    if workers_dir not in sys.path:
        sys.path.insert(0, workers_dir)

    import phone_worker_helper as ph
    import razorpay_worker_helper as rh
    from app.models import App

    # Disable Razorpay on the seeded test app; PhonePe is already disabled.
    app = db.get(App, APP_ID)
    app.razorpay_enabled = False
    db.commit()

    # If any worker touches Redis locks or runs a subscription scan, fail immediately.
    def no_lock(key, ttl):
        raise AssertionError(f"unexpected Redis lock acquired when gateway is disabled: {key}")

    monkeypatch.setattr(ph, "_single_flight", no_lock)
    monkeypatch.setattr(rh, "_single_flight", no_lock)
    monkeypatch.setattr(ph, "_is_non_peak_hour", lambda: True)

    for fn in (
        ph._sync_subscription_state,
        ph._sync_paused_state,
        ph._notify_redemption_for_due_subscriptions,
        ph._sync_redemption_txn_state,
        ph._sync_scheduled_transactions,
        ph._revoke_duplicate_active_subscriptions,
        ph._advance_payment_dates,
        ph._ensure_scheduled_transactions,
        ph._sync_total_payments,
        ph._archive_failed_subscriptions,
        rh._collect_razorpay_due,
        rh._reconcile_razorpay,
    ):
        fn()
