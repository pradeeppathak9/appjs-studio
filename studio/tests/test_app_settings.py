"""App settings: sign-in methods and the payment gateway, set by admins, seen by the app."""

import pytest

from tests.conftest import app_client
from tests.test_provider_keys import secrets_key  # noqa: F401


async def test_new_apps_have_no_payment_gateway(app, state):
    c = await app_client(app, state)
    assert (await c.get("/v1/app")).json()["payments"] == {"provider": "none"}


@pytest.mark.usefixtures("secrets_key")
async def test_payments_go_through_autorev(app, state, admin):
    c = await app_client(app, state, require_login=True)
    url = f"/v1/admin/apps/{c.app_row.id}"
    # the gateway alone isn't enough: the app takes payments once it is connected to autorev
    r = await admin.patch(url, json={"payment_provider": "razorpay"})
    assert r.status_code == 200, r.text
    assert (await c.get("/v1/app")).json()["payments"] == {"provider": "none"}

    r = await admin.patch(
        url,
        json={
            "autorev_app_id": "3f9c2a7be1d84c55",
            "autorev_api_key": "k" * 64,
            "autorev_webhook_secret": "whsec_" + "s" * 32,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["autorev_app_id"] == "3f9c2a7be1d84c55"
    assert body["autorev_api_key_set"] is True and body["autorev_webhook_secret_set"] is True
    assert "autorev_api_key" not in body and "autorev_webhook_secret" not in body  # write-only
    # a partial update leaves the sign-in settings alone
    assert body["require_login"] is True and body["auth_phone_enabled"] is True
    assert (await c.get("/v1/app")).json()["payments"] == {"provider": "razorpay"}

    # null removes the key, and payments are off again
    r = await admin.patch(url, json={"autorev_api_key": None})
    assert r.json()["autorev_api_key_set"] is False
    assert (await c.get("/v1/app")).json()["payments"] == {"provider": "none"}


@pytest.mark.usefixtures("secrets_key")
async def test_payment_settings_are_validated(app, state, admin):
    c = await app_client(app, state)
    url = f"/v1/admin/apps/{c.app_row.id}"
    bad = [
        {"payment_provider": "stripe"},
        {"autorev_app_id": "has spaces in it"},
        {"autorev_api_key": "short"},
        {"autorev_webhook_secret": "with a space " * 3},
    ]
    for body in bad:
        r = await admin.patch(url, json=body)
        assert r.status_code == 422, body
    # blank values are cleared, not rejected
    r = await admin.patch(url, json={"autorev_app_id": "  "})
    assert r.status_code == 200 and r.json()["autorev_app_id"] is None
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
