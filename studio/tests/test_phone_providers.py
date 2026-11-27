"""Phone sign-in per app: MSG91 (our server texts the code, with the app's own MSG91 account when set)
or Firebase (the device verifies the number, we check Firebase's ID token). Credentials are set from
the console, encrypted, and never read back."""

import time

import pytest
from sqlalchemy import select

import tests.conftest as conftest
from studio.db.tables import App
from studio.endusers.sms import LogSmsSender, Msg91Sender
from studio.secrets import SecretBox
from tests.conftest import app_client, google_token, sign_in_phone

PROJECT = "restyle-ai-1a2b3"


def firebase_token(state, phone="+919876543210", project=PROJECT, provider="phone", **claims) -> str:
    """A Firebase-style ID token signed with the test key the app's Firebase verifier trusts."""
    from google.auth import crypt
    from google.auth import jwt as gjwt

    google_token(state)  # makes the shared test key
    private_pem, cert_pem = conftest._google_key
    verifier = state.endusers.firebase
    verifier.certs = {"test-kid": cert_pem}
    verifier.certs_expire_at = float("inf")
    now = int(time.time())
    payload = {
        "iss": f"https://securetoken.google.com/{project}",
        "aud": project,
        "sub": "fb-uid-1",
        "auth_time": now - 5,
        "iat": now,
        "exp": now + 3600,
        "phone_number": phone,
        "firebase": {"sign_in_provider": provider, "identities": {"phone": [phone]}},
        **claims,
    }
    signer = crypt.RSASigner.from_string(private_pem, key_id="test-kid")
    return gjwt.encode(signer, payload).decode()


@pytest.fixture
def secrets_key(state, monkeypatch):
    """The server has a SECRETS_KEY (the test settings don't)."""
    box = SecretBox("test-secrets-key-0123456789")
    monkeypatch.setattr(state.apps, "box", box)
    monkeypatch.setattr(state.endusers, "box", box)
    return box


# ---- Firebase --------------------------------------------------------------------------------------


async def test_config_tells_a_firebase_app_its_project(app, state):
    c = await app_client(app, state, phone_provider="firebase", firebase_project_id=PROJECT)
    sign_in = (await c.get("/v1/app")).json()["sign_in"]
    assert (sign_in["phone"], sign_in["phone_provider"], sign_in["firebase_project_id"]) == (
        True,
        "firebase",
        PROJECT,
    )
    off = await app_client(app, state, slug="no-phone", auth_phone_enabled=False, phone_provider="firebase")
    sign_in = (await off.get("/v1/app")).json()["sign_in"]
    assert (sign_in["phone_provider"], sign_in["firebase_project_id"]) == (None, None)


async def test_firebase_sign_in_lands_on_the_same_account_as_sms_codes(app, state):
    c = await app_client(app, state, signup_credits=2)
    first = await sign_in_phone(c, state, phone="9876543210")  # an SMS-code account first

    async with state.db.begin() as s:  # the admin moves the app to Firebase
        a = await s.get(App, c.app_row.id)
        a.phone_provider, a.firebase_project_id = "firebase", PROJECT
    del c.headers["Authorization"]

    r = await c.post("/v1/app/auth/firebase", json={"id_token": firebase_token(state)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_new"] is False
    assert body["user"]["id"] == first["user"]["id"]
    assert body["user"]["phone"] == "+919876543210" and body["user"]["credits"] == 2

    c.headers["Authorization"] = f"Bearer {body['token']}"
    assert (await c.get("/v1/app/me")).status_code == 200

    us = firebase_token(state, phone="+14155550100")
    new = await c.post("/v1/app/auth/firebase", json={"id_token": us})
    assert new.json()["is_new"] is True and new.json()["user"]["phone"] == "+14155550100"


async def test_firebase_tokens_are_checked(app, state):
    c = await app_client(app, state, phone_provider="firebase", firebase_project_id=PROJECT)
    now = int(time.time())
    bad = {
        "another project": firebase_token(state, project="someone-else-9z"),
        "wrong issuer": firebase_token(state, iss="https://securetoken.google.com/someone-else-9z"),
        "expired": firebase_token(state, iat=now - 7200, exp=now - 3600),
        "future auth_time": firebase_token(state, auth_time=now + 3600),
        "not a phone sign-in": firebase_token(state, provider="password"),
        "no phone number": firebase_token(state, phone_number=None),
        "no subject": firebase_token(state, sub=""),
        "not a token": "x" * 40,
    }
    for why, token in bad.items():
        r = await c.post("/v1/app/auth/firebase", json={"id_token": token})
        assert r.status_code == 401, why
        assert r.json()["error"]["code"] == "invalid_token", why


async def test_each_app_uses_only_its_own_phone_method(app, state):
    fb = await app_client(app, state, phone_provider="firebase", firebase_project_id=PROJECT)
    r = await fb.post("/v1/app/auth/otp/send", json={"phone": "9876543210"})
    assert (r.status_code, r.json()["error"]["code"]) == (403, "sign_in_method_disabled")

    sms = await app_client(app, state, slug="sms-app")
    r = await sms.post("/v1/app/auth/firebase", json={"id_token": firebase_token(state)})
    assert (r.status_code, r.json()["error"]["code"]) == (403, "sign_in_method_disabled")

    unset = await app_client(app, state, slug="unset-app", phone_provider="firebase")
    r = await unset.post("/v1/app/auth/firebase", json={"id_token": firebase_token(state)})
    assert r.status_code == 401

    off = await app_client(
        app,
        state,
        slug="off-app",
        auth_phone_enabled=False,
        phone_provider="firebase",
        firebase_project_id=PROJECT,
    )
    r = await off.post("/v1/app/auth/firebase", json={"id_token": firebase_token(state)})
    assert r.status_code == 403


# ---- console: provider and credentials -------------------------------------------------------------


async def test_admin_sets_msg91_credentials_which_are_write_only(app, state, admin, secrets_key):
    c = await app_client(app, state)
    url = f"/v1/admin/apps/{c.app_row.id}"
    assert (await admin.get(url)).json()["secrets_key_set"] is True

    r = await admin.patch(
        url,
        json={
            "msg91_template_id": "6650ab12cd34ef",
            "msg91_otp_var": "OTP",
            "msg91_auth_key": "412345AbCdEfGh0",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["msg91_auth_key_set"] is True
    assert (body["msg91_template_id"], body["msg91_otp_var"]) == ("6650ab12cd34ef", "OTP")
    assert "412345AbCdEfGh0" not in r.text and "msg91_auth_key" not in body

    async with state.db() as s:
        stored = await s.scalar(select(App.msg91_auth_key_enc).where(App.id == c.app_row.id))
    assert stored and "412345AbCdEfGh0" not in stored
    assert secrets_key.decrypt(stored) == "412345AbCdEfGh0"

    # this app's codes now go through its own MSG91 account
    async with state.db() as s:
        sender = state.endusers.sms_for(await s.get(App, c.app_row.id))
    assert isinstance(sender, Msg91Sender)
    assert sender.auth_key == "412345AbCdEfGh0"
    assert (sender.template_id, sender.otp_var) == ("6650ab12cd34ef", "OTP")

    # saving another section, or the template alone, keeps the key
    r = await admin.patch(url, json={"msg91_template_id": "77aa88bb99cc"})
    assert r.json()["msg91_auth_key_set"] is True

    # null removes it, and codes fall back to the server's sender
    r = await admin.patch(url, json={"msg91_auth_key": None})
    assert r.json()["msg91_auth_key_set"] is False
    async with state.db() as s:
        assert isinstance(state.endusers.sms_for(await s.get(App, c.app_row.id)), LogSmsSender)


async def test_credentials_need_a_secrets_key_on_the_server(app, state, admin):
    c = await app_client(app, state)
    url = f"/v1/admin/apps/{c.app_row.id}"
    assert (await admin.get(url)).json()["secrets_key_set"] is False
    r = await admin.patch(url, json={"msg91_auth_key": "412345AbCdEfGh0"})
    assert (r.status_code, r.json()["error"]["code"]) == (503, "secrets_key_missing")
    # settings without a secret still save
    r = await admin.patch(url, json={"phone_provider": "firebase", "firebase_project_id": PROJECT})
    assert r.status_code == 200, r.text
    assert (r.json()["phone_provider"], r.json()["firebase_project_id"]) == ("firebase", PROJECT)


async def test_phone_settings_are_validated(app, state, admin, secrets_key):
    c = await app_client(app, state)
    url = f"/v1/admin/apps/{c.app_row.id}"
    for body in (
        {"phone_provider": "twilio"},
        {"phone_provider": None},
        {"firebase_project_id": "Not A Project"},
        {"msg91_template_id": "has spaces in it"},
        {"msg91_otp_var": "##otp##"},
        {"msg91_auth_key": "short"},
    ):
        r = await admin.patch(url, json=body)
        assert r.status_code == 422, body
    # blanks clear the optional fields
    r = await admin.patch(url, json={"firebase_project_id": "  ", "msg91_template_id": ""})
    assert r.status_code == 200
    assert (r.json()["firebase_project_id"], r.json()["msg91_template_id"]) == (None, None)


async def test_a_message_from_a_changed_secrets_key_is_reported(state):
    token = SecretBox("old-key-0123456789").encrypt("412345AbCdEfGh0")
    from studio.errors import UnavailableError

    with pytest.raises(UnavailableError):
        SecretBox("new-key-0123456789").decrypt(token)
    assert SecretBox("old-key-0123456789").decrypt(token) == "412345AbCdEfGh0"


async def test_whatsapp_sender_sends_the_code_in_an_authentication_template():
    import json

    import httpx

    from studio.endusers.sms import SmsUnavailable, WhatsAppSender

    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200 if len(seen) == 1 else 400, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        sender = WhatsAppSender(http, "tok", "1234567890", "restyle_login", "en")
        await sender.send_otp("+919876543210", "482913")
        with pytest.raises(SmsUnavailable):
            await sender.send_otp("+919876543210", "482913")

    req = seen[0]
    assert str(req.url) == "https://graph.facebook.com/v25.0/1234567890/messages"
    assert req.headers["authorization"] == "Bearer tok"
    body = json.loads(req.content)
    assert body["to"] == "919876543210" and body["template"]["name"] == "restyle_login"
    body_param, button = body["template"]["components"]
    assert body_param["parameters"][0]["text"] == "482913"
    assert (button["sub_type"], button["parameters"][0]["text"]) == ("url", "482913")


def test_whatsapp_provider_needs_its_settings():
    import httpx

    from studio.config import Settings
    from studio.endusers.sms import WhatsAppSender, sms_sender

    http = httpx.AsyncClient()
    with pytest.raises(RuntimeError, match="WHATSAPP_TOKEN"):
        sms_sender(Settings(_env_file=None, sms_provider="whatsapp"), http)
    s = Settings(
        _env_file=None,
        sms_provider="whatsapp",
        whatsapp_token="t",
        whatsapp_phone_number_id="1",
        whatsapp_template="x",
    )
    assert isinstance(sms_sender(s, http), WhatsAppSender)
