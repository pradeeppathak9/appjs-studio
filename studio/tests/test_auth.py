import asyncio
from datetime import timedelta

from sqlalchemy import update

from studio.db.tables import Session
from tests.conftest import ADMIN, SETUP_TOKEN, TESTER, client, signed_in

SETUP = {"setup_token": SETUP_TOKEN, "email": ADMIN[0], "name": ADMIN[1], "password": ADMIN[2]}


async def test_setup_creates_the_first_admin_once(anon, app):
    assert (await anon.get("/v1/auth/setup")).json() == {"needed": True}
    r = await anon.post("/v1/auth/setup", json=SETUP)
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "admin"
    assert (await anon.get("/v1/auth/me")).json()["email"] == ADMIN[0]  # signed in by setup
    assert (await anon.get("/v1/auth/setup")).json() == {"needed": False}
    again = await client(app).post("/v1/auth/setup", json={**SETUP, "email": "x@example.com"})
    assert again.status_code == 409


async def test_setup_rejects_a_wrong_token(anon):
    r = await anon.post("/v1/auth/setup", json={**SETUP, "setup_token": "nope"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "invalid_setup_token"


async def test_concurrent_setups_create_one_admin(app, state):
    results = await asyncio.gather(
        *(client(app).post("/v1/auth/setup", json={**SETUP, "email": f"a{i}@example.com"}) for i in range(5))
    )
    assert sorted(r.status_code for r in results) == [201, 409, 409, 409, 409]
    assert await state.auth.user_count() == 1


async def test_login_does_not_reveal_which_emails_exist(app, admin):
    c = client(app)
    unknown = await c.post("/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever-123"})
    wrong = await c.post("/v1/auth/login", json={"email": ADMIN[0], "password": "wrong-password-1"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


async def test_login_is_throttled_after_repeated_failures(app, admin, settings):
    c = client(app)
    for _ in range(settings.login_max_failures):
        assert (
            await c.post("/v1/auth/login", json={"email": ADMIN[0], "password": "bad-password-1"})
        ).status_code == 401
    r = await c.post("/v1/auth/login", json={"email": ADMIN[0], "password": ADMIN[2]})
    assert r.status_code == 429


async def test_signed_out_requests_get_401(anon):
    assert (await anon.get("/v1/apps")).status_code == 401
    assert (await anon.get("/v1/admin/users")).status_code == 401


async def test_logout_ends_the_session(admin):
    assert (await admin.post("/v1/auth/logout")).status_code == 204
    assert (await admin.get("/v1/auth/me")).status_code == 401


async def test_idle_session_expires(admin, state, settings):
    async with state.db.begin() as s:
        await s.execute(
            update(Session).values(
                last_seen_at=Session.last_seen_at - timedelta(hours=settings.session_idle_hours + 1)
            )
        )
    assert (await admin.get("/v1/auth/me")).status_code == 401


async def test_temporary_password_must_be_changed_first(app, admin):
    r = await admin.post("/v1/admin/users", json={"email": "new@example.com", "name": "New", "role": "user"})
    assert r.status_code == 201
    temp = r.json()["temporary_password"]
    c = client(app)
    me = await c.post("/v1/auth/login", json={"email": "new@example.com", "password": temp})
    assert me.json()["must_change_password"] is True
    blocked = await c.get("/v1/apps")
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "password_change_required"
    assert (await c.get("/v1/auth/me")).status_code == 200
    r = await c.post(
        "/v1/auth/password", json={"current_password": temp, "new_password": "brand-new-password"}
    )
    assert r.status_code == 204
    assert (await c.get("/v1/apps")).status_code == 200


async def test_password_change_ends_other_sessions(app, state, tester):
    other = client(app)
    await other.post("/v1/auth/login", json={"email": TESTER[0], "password": TESTER[2]})
    r = await tester.post(
        "/v1/auth/password", json={"current_password": TESTER[2], "new_password": "another-password-9"}
    )
    assert r.status_code == 204
    assert (await tester.get("/v1/auth/me")).status_code == 200
    assert (await other.get("/v1/auth/me")).status_code == 401


async def test_password_rules(tester):
    r = await tester.post("/v1/auth/password", json={"current_password": TESTER[2], "new_password": "short"})
    assert r.status_code == 422 and r.json()["error"]["field"] == "password"


async def test_api_tokens_act_as_their_owner_and_can_be_revoked(app, tester):
    r = await tester.post("/v1/auth/tokens", json={"name": "ci"})
    assert r.status_code == 201
    token = r.json()["token"]
    assert token.startswith("crt_")
    bearer = client(app)
    bearer.headers["Authorization"] = f"Bearer {token}"
    assert (await bearer.get("/v1/auth/me")).json()["role"] == "user"
    listed = (await tester.get("/v1/auth/tokens")).json()
    assert "token" not in listed[0] and listed[0]["prefix"] == token[:8]
    assert (await tester.delete(f"/v1/auth/tokens/{listed[0]['id']}")).status_code == 204
    assert (await bearer.get("/v1/auth/me")).status_code == 401


async def test_deactivating_a_user_ends_sessions_and_tokens(app, admin, tester):
    token = (await tester.post("/v1/auth/tokens", json={"name": "t"})).json()["token"]
    r = await admin.patch(f"/v1/admin/users/{tester.user.id}", json={"is_active": False})
    assert r.status_code == 200
    assert (await tester.get("/v1/auth/me")).status_code == 401
    bearer = client(app)
    bearer.headers["Authorization"] = f"Bearer {token}"
    assert (await bearer.get("/v1/auth/me")).status_code == 401
    login = await client(app).post("/v1/auth/login", json={"email": TESTER[0], "password": TESTER[2]})
    assert login.status_code == 401


async def test_role_change_applies_on_next_request(admin, tester):
    assert (await tester.get("/v1/admin/users")).status_code == 403
    await admin.patch(f"/v1/admin/users/{tester.user.id}", json={"role": "admin"})
    # the role change ended the user's sessions; signing in again gets the new role
    assert (await tester.get("/v1/admin/users")).status_code == 401


async def test_last_admin_cannot_be_removed(admin, app, state):
    r = await admin.patch(f"/v1/admin/users/{admin.user.id}", json={"role": "user"})
    assert r.status_code == 403
    r = await admin.patch(f"/v1/admin/users/{admin.user.id}", json={"is_active": False})
    assert r.status_code == 403
    second = await signed_in(app, state, "admin", ("second@example.com", "Second", "second-password-1"))
    r = await second.patch(f"/v1/admin/users/{admin.user.id}", json={"role": "user"})
    assert r.status_code == 200
    r = await admin.get("/v1/admin/users")
    assert r.status_code == 401  # demotion ended the first admin's session


async def test_admin_creates_users_and_admins(admin):
    r = await admin.post(
        "/v1/admin/users", json={"email": "boss@example.com", "name": "Boss", "role": "admin"}
    )
    assert r.status_code == 201 and r.json()["user"]["role"] == "admin"
    r = await admin.post("/v1/admin/users", json={"email": "x@example.com", "name": "X", "role": "creator"})
    assert r.status_code == 422
    dup = await admin.post("/v1/admin/users", json={"email": ADMIN[0].upper(), "name": "Dup", "role": "user"})
    assert dup.status_code == 409


async def test_reset_password_gives_a_new_temporary_one(app, admin, tester):
    r = await admin.post(f"/v1/admin/users/{tester.user.id}/reset-password")
    temp = r.json()["temporary_password"]
    assert (await tester.get("/v1/auth/me")).status_code == 401
    me = await client(app).post("/v1/auth/login", json={"email": TESTER[0], "password": temp})
    assert me.json()["must_change_password"] is True


async def test_cross_site_writes_are_refused(app, tester):
    r = await tester.post("/v1/auth/tokens", json={"name": "x"}, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "cross_site_request"
    ok = await tester.post("/v1/auth/tokens", json={"name": "x"}, headers={"Origin": "http://testserver"})
    assert ok.status_code == 201
    token = ok.json()["token"]
    bearer = client(app)
    r = await bearer.post(
        "/v1/auth/tokens",
        json={"name": "y"},
        headers={"Origin": "http://evil.example", "Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201


async def test_admin_deletes_a_user(app, state, admin, creator, tester):
    token = (await tester.post("/v1/auth/tokens", json={"name": "t"})).json()["token"]
    from tests.conftest import create_template, image_bytes

    await create_template(creator)
    files = {"photo": ("me.jpg", image_bytes(), "image/jpeg")}
    job = (await tester.post(tester.ws + "/templates/ghibli-fake/generations", files=files)).json()

    assert (await admin.delete(f"/v1/admin/users/{tester.user.id}")).status_code == 204
    assert (await tester.get("/v1/auth/me")).status_code == 401
    bearer = client(app)
    bearer.headers["Authorization"] = f"Bearer {token}"
    assert (await bearer.get("/v1/auth/me")).status_code == 401
    login = await client(app).post("/v1/auth/login", json={"email": TESTER[0], "password": TESTER[2]})
    assert login.status_code == 401
    assert TESTER[0] not in [u["email"] for u in (await admin.get("/v1/admin/users")).json()]
    # history keeps the name; the email can be used again
    assert (await creator.get(f"/v1/generations/{job['id']}")).json()["created_by"]["name"] == TESTER[1]
    again = await admin.post("/v1/admin/users", json={"email": TESTER[0], "name": "New Tess", "role": "user"})
    assert again.status_code == 201
    assert (await admin.delete(f"/v1/admin/users/{tester.user.id}")).status_code == 404
    assert (await admin.patch(f"/v1/admin/users/{tester.user.id}", json={"name": "x"})).status_code == 404


async def test_admin_cannot_delete_themselves_or_the_last_admin(app, state, admin):
    r = await admin.delete(f"/v1/admin/users/{admin.user.id}")
    assert r.status_code == 403
    second = await signed_in(app, state, "admin", ("second@example.com", "Second", "second-password-1"))
    assert (await second.delete(f"/v1/admin/users/{admin.user.id}")).status_code == 204
    assert (await second.delete(f"/v1/admin/users/{second.user.id}")).status_code == 403


async def test_only_admins_delete_users(creator, tester):
    assert (await creator.delete(f"/v1/admin/users/{tester.user.id}")).status_code == 403
