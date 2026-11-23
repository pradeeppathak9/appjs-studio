"""App settings: sign-in methods and the payment gateway, set by admins, seen by the app."""

from tests.conftest import app_client


async def test_new_apps_have_no_payment_gateway(app, state):
    c = await app_client(app, state)
    assert (await c.get("/v1/app")).json()["payments"] == {
        "provider": "none",
        "mode": "test",
        "razorpay_key_id": None,
    }


async def test_admin_picks_razorpay_and_the_app_gets_its_key(app, state, admin):
    c = await app_client(app, state, require_login=True)
    url = f"/v1/admin/apps/{c.app_row.id}"
    r = await admin.patch(
        url,
        json={
            "payment_provider": "razorpay",
            "payment_mode": "test",
            "razorpay_key_id": "rzp_test_Ab12Cd34Ef",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["payment_provider"], body["payment_mode"], body["razorpay_key_id"]) == (
        "razorpay",
        "test",
        "rzp_test_Ab12Cd34Ef",
    )
    # a partial update leaves the sign-in settings alone
    assert body["require_login"] is True and body["auth_phone_enabled"] is True
    assert (await c.get("/v1/app")).json()["payments"] == {
        "provider": "razorpay",
        "mode": "test",
        "razorpay_key_id": "rzp_test_Ab12Cd34Ef",
    }


async def test_phonepe_keeps_its_merchant_id_off_the_device(app, state, admin):
    c = await app_client(app, state)
    r = await admin.patch(
        f"/v1/admin/apps/{c.app_row.id}",
        json={"payment_provider": "phonepe", "payment_mode": "live", "phonepe_merchant_id": "M22ABCDXYZ"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["phonepe_merchant_id"] == "M22ABCDXYZ"
    assert (await c.get("/v1/app")).json()["payments"] == {
        "provider": "phonepe",
        "mode": "live",
        "razorpay_key_id": None,
    }


async def test_payment_settings_are_validated(app, state, admin):
    c = await app_client(app, state)
    url = f"/v1/admin/apps/{c.app_row.id}"
    bad = [
        {"payment_provider": "stripe"},
        {"payment_mode": "prod"},
        {"payment_provider": "razorpay", "payment_mode": "test", "razorpay_key_id": "not-a-key"},
        {"payment_provider": "razorpay", "payment_mode": "test", "razorpay_key_id": "rzp_live_Ab12Cd34Ef"},
        {"payment_provider": "phonepe", "phonepe_merchant_id": "lower-case"},
    ]
    for body in bad:
        r = await admin.patch(url, json=body)
        assert r.status_code == 422, body
    # blank ids are cleared, not rejected
    r = await admin.patch(url, json={"payment_provider": "razorpay", "razorpay_key_id": "  "})
    assert r.status_code == 200 and r.json()["razorpay_key_id"] is None
    # the key is checked against the stored mode too
    await admin.patch(url, json={"payment_mode": "live"})
    r = await admin.patch(url, json={"razorpay_key_id": "rzp_test_Ab12Cd34Ef"})
    assert r.status_code == 422 and r.json()["error"]["field"] == "razorpay_key_id"
    assert (await admin.patch(url, json={"name": None})).status_code == 422


async def test_both_sign_in_methods_can_be_on(app, state, admin):
    c = await app_client(app, state, auth_google_enabled=False)
    r = await admin.patch(
        f"/v1/admin/apps/{c.app_row.id}",
        json={
            "auth_phone_enabled": True,
            "auth_google_enabled": True,
            "google_client_ids": ["1234-test.apps.googleusercontent.com"],
        },
    )
    assert r.status_code == 200, r.text
    sign_in = (await c.get("/v1/app")).json()["sign_in"]
    assert sign_in == {
        "google": True,
        "phone": True,
        "google_client_id": "1234-test.apps.googleusercontent.com",
        "phone_provider": "msg91",
        "firebase_project_id": None,
    }
