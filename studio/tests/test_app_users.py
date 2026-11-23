"""End users of an app: sign-in with a phone code or Google, sessions, require_login."""

import time

from sqlalchemy import text

from tests.conftest import (
    GOOGLE_CLIENT_ID,
    app_client,
    create_template,
    google_token,
    member,
    sign_in_phone,
    with_device,
)

# ---- config ---------------------------------------------------------------------------------------------


async def test_config_tells_the_app_which_sign_in_to_show(app, state):
    c = await app_client(app, state, auth_google_enabled=False, require_login=True)
    body = (await c.get("/v1/app")).json()
    assert body["app"]["slug"] == "reelify"
    assert body["sign_in"] == {
        "google": False,
        "phone": True,
        "google_client_id": None,
        "phone_provider": "msg91",
        "firebase_project_id": None,
    }
    assert body["require_login"] is True

    g = await app_client(app, state, slug="other-app")
    assert (await g.get("/v1/app")).json()["sign_in"]["google_client_id"] == GOOGLE_CLIENT_ID


# ---- phone ----------------------------------------------------------------------------------------------


async def test_phone_sign_in_creates_the_account_once_with_signup_credits(app, state):
    c = await app_client(app, state, signup_credits=3)
    first = await sign_in_phone(c, state, "98765 43210")
    assert first["is_new"] is True
    assert first["user"]["phone"] == "+919876543210"
    assert first["user"]["sign_in"] == "phone"
    assert first["user"]["credits"] == 3
    me = (await c.get("/v1/app/me")).json()
    assert me["credits"] == 3 and me["subscription"] is None
    history = (await c.get("/v1/app/me/credits")).json()
    assert [(e["reason"], e["delta"]) for e in history] == [("signup", 3)]

    # wait out the resend cooldown, sign in again: same account, no second bonus
    async with state.engine.begin() as conn:
        await conn.execute(text("UPDATE otp_challenges SET created_at = created_at - interval '1 minute'"))
    again = await sign_in_phone(with_device(c, app, "device-2"), state, "+91 98765-43210")
    assert again["is_new"] is False
    assert again["user"]["id"] == first["user"]["id"]
    assert again["user"]["credits"] == 3


async def test_wrong_codes_count_down_then_the_code_is_dead(app, state):
    c = await app_client(app, state)
    sent = (await c.post("/v1/app/auth/otp/send", json={"phone": "9876543210"})).json()
    good = state.endusers.sms.sent[sent["phone"]]
    bad = "000000" if good != "000000" else "111111"
    for left in (4, 3, 2, 1):
        r = await c.post("/v1/app/auth/otp/verify", json={"challenge_id": sent["challenge_id"], "code": bad})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "otp_invalid"
        assert r.json()["error"]["details"] == [{"attempts_left": left}]
    r = await c.post("/v1/app/auth/otp/verify", json={"challenge_id": sent["challenge_id"], "code": bad})
    assert r.json()["error"]["code"] == "otp_expired"
    r = await c.post("/v1/app/auth/otp/verify", json={"challenge_id": sent["challenge_id"], "code": good})
    assert r.status_code == 400 and r.json()["error"]["code"] == "otp_expired"


async def test_a_code_works_once_and_not_after_it_expires(app, state):
    c = await app_client(app, state)
    await sign_in_phone(c, state)
    used = (await c.get("/v1/app/me")).json()
    assert used["phone"] == "+919876543210"

    c2 = await app_client(app, state, slug="second-app")
    sent = (await c2.post("/v1/app/auth/otp/send", json={"phone": "9876543210"})).json()
    code = state.endusers.sms.sent[sent["phone"]]
    async with state.engine.begin() as conn:
        await conn.execute(text("UPDATE otp_challenges SET expires_at = now() - interval '1 second'"))
    r = await c2.post("/v1/app/auth/otp/verify", json={"challenge_id": sent["challenge_id"], "code": code})
    assert r.json()["error"]["code"] == "otp_expired"


async def test_codes_are_rate_limited(app, state):
    c = await app_client(app, state)
    assert (await c.post("/v1/app/auth/otp/send", json={"phone": "9876543210"})).status_code == 200
    r = await c.post("/v1/app/auth/otp/send", json={"phone": "9876543210"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    # past the cooldown, the hourly limit per number still applies
    for _ in range(state.settings.otp_per_phone_per_hour - 1):
        async with state.engine.begin() as conn:
            await conn.execute(
                text("UPDATE otp_challenges SET created_at = created_at - interval '40 seconds'")
            )
        assert (await c.post("/v1/app/auth/otp/send", json={"phone": "9876543210"})).status_code == 200
    async with state.engine.begin() as conn:
        await conn.execute(text("UPDATE otp_challenges SET created_at = created_at - interval '40 seconds'"))
    r = await c.post("/v1/app/auth/otp/send", json={"phone": "9876543210"})
    assert r.status_code == 429 and "this number" in r.json()["error"]["message"]


async def test_bad_numbers_and_disabled_phone_sign_in(app, state):
    c = await app_client(app, state)
    r = await c.post("/v1/app/auth/otp/send", json={"phone": "123456789"})
    assert r.status_code == 422 and r.json()["error"]["field"] == "phone"
    off = await app_client(app, state, slug="no-phone", auth_phone_enabled=False)
    r = await off.post("/v1/app/auth/otp/send", json={"phone": "9876543210"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "sign_in_method_disabled"


async def test_store_review_numbers_use_a_fixed_code_and_send_nothing(app, state):
    c = await app_client(app, state)
    state.endusers.test_numbers = {"+919999999999": "424242"}
    try:
        before = dict(state.endusers.sms.sent)
        sent = (await c.post("/v1/app/auth/otp/send", json={"phone": "9999999999"})).json()
        assert state.endusers.sms.sent == before
        r = await c.post(
            "/v1/app/auth/otp/verify", json={"challenge_id": sent["challenge_id"], "code": "424242"}
        )
        assert r.status_code == 200
    finally:
        state.endusers.test_numbers = {}


# ---- Google ---------------------------------------------------------------------------------------------


async def test_google_sign_in(app, state):
    c = await app_client(app, state, signup_credits=2)
    r = await c.post("/v1/app/auth/google", json={"id_token": google_token(state)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_new"] is True
    assert body["user"]["email"] == "g-123@gmail.com"
    assert body["user"]["name"] == "Gia Google"
    assert body["user"]["sign_in"] == "google"
    assert body["user"]["credits"] == 2
    again = (
        await c.post("/v1/app/auth/google", json={"id_token": google_token(state, name="Gia G.")})
    ).json()
    assert again["is_new"] is False and again["user"]["id"] == body["user"]["id"]
    assert again["user"]["name"] == "Gia G."  # profile follows Google


async def test_google_tokens_are_checked(app, state):
    c = await app_client(app, state)
    cases = {
        "wrong audience": google_token(state, aud="999-other.apps.googleusercontent.com"),
        "expired": google_token(state, iat=int(time.time()) - 7200, exp=int(time.time()) - 3600),
        "wrong issuer": google_token(state, iss="https://evil.example.com"),
        "unverified email": google_token(state, email_verified=False),
        "garbage": "x" * 40,
    }
    for why, token in cases.items():
        r = await c.post("/v1/app/auth/google", json={"id_token": token})
        assert r.status_code == 401, why
        assert r.json()["error"]["code"] == "invalid_token", why


async def test_accounts_are_per_app(app, state):
    a = await app_client(app, state, slug="app-a")
    b = await app_client(app, state, slug="app-b")
    ua = (await a.post("/v1/app/auth/google", json={"id_token": google_token(state)})).json()["user"]
    ub = (await b.post("/v1/app/auth/google", json={"id_token": google_token(state)})).json()["user"]
    assert ua["id"] != ub["id"]


# ---- sessions -------------------------------------------------------------------------------------------


async def test_logout_ends_the_session(app, state):
    c = await app_client(app, state)
    await sign_in_phone(c, state)
    assert (await c.get("/v1/app/me")).status_code == 200
    assert (await c.post("/v1/app/auth/logout")).status_code == 204
    r = await c.get("/v1/app/me")
    assert r.status_code == 401


async def test_a_session_only_works_with_its_own_app(app, state):
    a = await app_client(app, state, slug="app-a")
    b = await app_client(app, state, slug="app-b")
    await sign_in_phone(a, state)
    b.headers["Authorization"] = a.headers["Authorization"]
    assert (await b.get("/v1/app/me")).status_code == 401
    assert (await a.get("/v1/app/me")).status_code == 200
    a.headers["Authorization"] = "Bearer cas_made-up"
    assert (await a.get("/v1/app/me")).status_code == 401


async def test_expired_sessions_are_refused(app, state):
    c = await app_client(app, state)
    await sign_in_phone(c, state)
    async with state.engine.begin() as conn:
        await conn.execute(text("UPDATE app_user_sessions SET expires_at = now() - interval '1 second'"))
    assert (await c.get("/v1/app/me")).status_code == 401


async def test_blocked_users_are_signed_out_and_refused(app, state, admin):
    c = await app_client(app, state)
    await sign_in_phone(c, state)
    base = f"/v1/admin/apps/{c.app_row.id}/users/{c.user_id}"
    r = await admin.put(base + "/status", json={"status": "blocked"})
    assert r.status_code == 200 and r.json()["status"] == "blocked"
    assert (await c.get("/v1/app/me")).status_code == 401  # its sessions were revoked
    async with state.engine.begin() as conn:
        await conn.execute(text("UPDATE otp_challenges SET created_at = created_at - interval '1 minute'"))
    sent = (await c.post("/v1/app/auth/otp/send", json={"phone": "9876543210"})).json()
    code = state.endusers.sms.sent[sent["phone"]]
    r = await c.post("/v1/app/auth/otp/verify", json={"challenge_id": sent["challenge_id"], "code": code})
    assert r.status_code == 403 and r.json()["error"]["code"] == "account_blocked"


async def test_profile_and_account_deletion(app, state):
    c = await app_client(app, state, signup_credits=1)
    first = await sign_in_phone(c, state)
    r = await c.patch("/v1/app/me", json={"name": "  Priya  "})
    assert r.json()["name"] == "Priya"
    assert (await c.delete("/v1/app/me")).status_code == 204
    assert (await c.get("/v1/app/me")).status_code == 401
    async with state.engine.begin() as conn:
        await conn.execute(text("UPDATE otp_challenges SET created_at = created_at - interval '1 minute'"))
        row = (await conn.execute(text("SELECT phone, name, deleted_at FROM app_users"))).one()
    assert row.phone is None and row.name is None and row.deleted_at is not None
    again = await sign_in_phone(with_device(c, app, "device-9"), state)
    assert again["is_new"] is True and again["user"]["id"] != first["user"]["id"]


# ---- require_login --------------------------------------------------------------------------------------


async def test_require_login_gates_the_catalog_and_runs(app, state):
    c = await app_client(app, state, require_login=True)
    editor = await member(app, state, c.app_row, "editor", ("ed@example.com", "Ed", "editor-password-1"))
    await create_template(editor)
    r = await c.get("/v1/app/templates")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthenticated"
    await sign_in_phone(c, state)
    r = await c.get("/v1/app/templates")
    assert r.status_code == 200
    assert [t["slug"] for t in r.json()["templates"]] == ["ghibli-fake"]
    assert r.json()["templates"][0]["credit_cost"] == 1
    # the cover stays reachable with the key alone (image loaders)
    anon = with_device(c, app, "device-x")
    assert (await anon.get("/v1/app/templates/ghibli-fake")).status_code == 401
    assert (await anon.get("/v1/app/plans")).status_code == 200


async def test_without_require_login_a_token_is_optional_but_checked(app, state):
    c = await app_client(app, state)
    assert (await c.get("/v1/app/templates")).status_code == 200
    c.headers["Authorization"] = "Bearer cas_nope"
    assert (await c.get("/v1/app/templates")).status_code == 401


async def test_dev_code_works_for_any_number_only_with_the_log_sender(app, state):
    from creative.config import Settings
    from creative.endusers.service import AppUserService

    c = await app_client(app, state)
    state.endusers.dev_code = "123456"
    try:
        before = dict(state.endusers.sms.sent)
        sent = (await c.post("/v1/app/auth/otp/send", json={"phone": "9000000001"})).json()
        assert state.endusers.sms.sent == before  # nothing "sent"
        r = await c.post(
            "/v1/app/auth/otp/verify", json={"challenge_id": sent["challenge_id"], "code": "123456"}
        )
        assert r.status_code == 200 and r.json()["user"]["phone"] == "+919000000001"
    finally:
        state.endusers.dev_code = None
    prod = Settings(
        _env_file=None, sms_provider="msg91", msg91_auth_key="k", msg91_template_id="t", otp_dev_code="123456"
    )
    assert AppUserService(prod, state.db, state.http).dev_code is None
