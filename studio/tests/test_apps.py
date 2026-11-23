"""Apps as workspaces: members see their apps; editors manage the app's templates; testers run
them; admins manage apps, members and keys; the app's clients use an app key."""

from sqlalchemy import update

from creative.db.tables import AppMember
from tests.conftest import (
    GHIBLI,
    TESTER,
    client,
    create_template,
    image_bytes,
    join,
    make_app,
    run_worker_once,
    signed_in,
)

# Signed-out app-key calls may only run free templates (paid ones need a signed-in user).
FREE = {**GHIBLI, "credit_cost": 0}

PHOTO = {"photo": ("me.jpg", image_bytes((300, 400)), "image/jpeg")}


async def key_client(app, admin, app_id, device="device-1"):
    r = await admin.post(f"/v1/admin/apps/{app_id}/keys", json={"name": "android release"})
    assert r.status_code == 201, r.text
    key = r.json()["key"]
    assert key.startswith("cak_")
    c = client(app)
    c.headers["X-App-Key"] = key
    if device:
        c.headers["X-Device-Id"] = device
    c.key = key
    return c


def roles(resp) -> dict:
    return {a["slug"]: a["role"] for a in resp.json()}


# ---- my apps and roles ------------------------------------------------------------------------------


async def test_users_see_only_their_apps_with_their_role(app, state, admin, creator, tester, ws):
    other = await make_app(state, slug="other-app", name="Other")
    await join(state, other.id, tester.user, "editor")
    assert roles(await tester.get("/v1/apps")) == {"workspace": "tester", "other-app": "editor"}
    assert roles(await creator.get("/v1/apps")) == {"workspace": "editor"}
    assert roles(await admin.get("/v1/apps")) == {"workspace": "admin", "other-app": "admin"}
    # an app you're not in doesn't exist for you
    assert (await creator.get(f"/v1/apps/{other.id}")).status_code == 404
    assert (await creator.get(f"/v1/apps/{other.id}/templates")).status_code == 404


async def test_testers_cannot_manage_templates(creator, tester):
    await create_template(creator)
    assert (await tester.get(tester.ws + "/manage/templates")).status_code == 403
    assert (await tester.post(tester.ws + "/manage/templates", json=GHIBLI)).status_code == 403
    assert (await tester.post(tester.ws + "/generations", json={"prompt": "x"})).status_code == 403
    assert (await tester.get(tester.ws + "/catalog")).status_code == 403


async def test_templates_belong_to_one_app(app, state, creator):
    other = await make_app(state, slug="other-app", name="Other")
    await join(state, other.id, creator.user, "editor")
    a = await create_template(creator)
    other_base = f"/v1/apps/{other.id}"
    # the same slug in another app is fine; neither app sees the other's template
    r = await creator.post(other_base + "/manage/templates", json=GHIBLI)
    assert r.status_code == 201
    b = r.json()["template"]
    assert b["id"] != a["id"] and b["app_id"] == str(other.id)
    assert (await creator.get(f"{other_base}/manage/templates/{a['id']}")).status_code == 404


async def test_reorder_sets_the_order_testers_and_clients_see(app, admin, creator, tester, ws):
    one = await create_template(creator)
    two = await create_template(creator, {**GHIBLI, "slug": "second", "title": "Second"})
    order_url = creator.ws + "/manage/templates/order"
    assert (await creator.put(order_url, json={"template_ids": [two["id"], one["id"]]})).status_code == 204
    listed = (await tester.get(tester.ws + "/templates")).json()
    assert [t["slug"] for t in listed] == ["second", "ghibli-fake"]
    android = await key_client(app, admin, ws.id)
    catalog = (await android.get("/v1/app/templates")).json()["templates"]
    assert [t["slug"] for t in catalog] == ["second", "ghibli-fake"]
    bad = await creator.put(order_url, json={"template_ids": [one["id"]]})
    assert bad.status_code == 422  # must list every template


async def test_copy_to_another_app(app, state, creator):
    other = await make_app(state, slug="other-app", name="Other")
    t = await create_template(creator)
    url = f"{creator.ws}/manage/templates/{t['id']}/copy"
    body = {"target_app_id": str(other.id)}
    assert (await creator.post(url, json=body)).status_code == 404  # not a member of the target
    await join(state, other.id, creator.user, "tester")
    assert (await creator.post(url, json=body)).status_code == 403  # only a tester there
    async with state.db.begin() as s:
        await s.execute(update(AppMember).where(AppMember.app_id == other.id).values(role="editor"))
    r = await creator.post(url, json=body)
    assert r.status_code == 201
    copy = r.json()["template"]
    assert copy["app_id"] == str(other.id) and copy["status"] == "draft" and copy["current_version"] == 1
    assert copy["current"]["prompt"] == GHIBLI["prompt"]


async def test_editor_sees_all_app_jobs_tester_only_own(app, state, creator, tester, ws):
    await create_template(creator)
    other_tester = await signed_in(app, state, "user", ("t2@example.com", "Tom", "tom-password-123"))
    await join(state, ws.id, other_tester.user, "tester")
    run = tester.ws + "/templates/ghibli-fake/generations"
    mine = (await tester.post(run, files=PHOTO)).json()
    theirs = (await other_tester.post(run, files=PHOTO)).json()
    assert [j["id"] for j in (await tester.get(tester.ws + "/generations")).json()["items"]] == [mine["id"]]
    assert (await tester.get(f"/v1/generations/{theirs['id']}")).status_code == 404
    assert len((await creator.get(creator.ws + "/generations")).json()["items"]) == 2


# ---- admin -------------------------------------------------------------------------------------------


async def test_admin_manages_apps_and_members(app, state, admin, tester, ws):
    r = await admin.post("/v1/admin/apps", json={"slug": "pixel-fun", "name": "Pixel Fun"})
    assert r.status_code == 201
    new = r.json()
    assert (await admin.post("/v1/admin/apps", json={"slug": "pixel-fun", "name": "dup"})).status_code == 409
    base = f"/v1/admin/apps/{new['id']}/members"
    assert (await admin.put(f"{base}/{tester.user.id}", json={"role": "editor"})).status_code == 204
    assert roles(await tester.get("/v1/apps"))["pixel-fun"] == "editor"
    members = (await admin.get(base)).json()
    assert [(m["email"], m["role"]) for m in members] == [(TESTER[0], "editor")]
    assert (await admin.put(f"{base}/{tester.user.id}", json={"role": "tester"})).status_code == 204
    memberships = (await admin.get(f"/v1/admin/users/{tester.user.id}/apps")).json()
    assert sorted((m["app_slug"], m["role"]) for m in memberships) == [
        ("pixel-fun", "tester"),
        ("workspace", "tester"),
    ]
    assert (await admin.delete(f"{base}/{tester.user.id}")).status_code == 204
    assert "pixel-fun" not in roles(await tester.get("/v1/apps"))
    # admins aren't members: they already open every app
    assert (await admin.put(f"{base}/{admin.user.id}", json={"role": "editor"})).status_code == 422


async def test_only_admins_reach_the_admin_dashboard(creator, tester):
    for c in (creator, tester):
        assert (await c.get("/v1/admin/apps")).status_code == 403
        assert (await c.get("/v1/admin/users")).status_code == 403
        assert (await c.post("/v1/admin/apps", json={"slug": "abc", "name": "x"})).status_code == 403


async def test_deleting_an_app(app, state, admin, creator, tester, ws):
    await create_template(creator)
    android = await key_client(app, admin, ws.id)
    job = (await tester.post(tester.ws + "/templates/ghibli-fake/generations", files=PHOTO)).json()
    assert (await admin.delete(f"/v1/admin/apps/{ws.id}")).status_code == 204
    assert (await tester.get("/v1/apps")).json() == []
    assert (await creator.get(creator.ws + "/manage/templates")).status_code == 404
    assert (await android.get("/v1/app/templates")).status_code == 401
    assert "workspace" not in [a["slug"] for a in (await admin.get("/v1/admin/apps")).json()]
    # the slug is free again; old jobs keep the app's name for admins
    assert (
        await admin.post("/v1/admin/apps", json={"slug": "workspace", "name": "Again"})
    ).status_code == 201
    assert (await admin.get(f"/v1/generations/{job['id']}")).json()["app"]["name"] == "Workspace"


async def test_deleting_a_user_removes_their_memberships(admin, tester, ws):
    assert (await admin.delete(f"/v1/admin/users/{tester.user.id}")).status_code == 204
    assert (await admin.get(f"/v1/admin/apps/{ws.id}/members")).json() == []


# ---- the app's clients ------------------------------------------------------------------------------


async def test_client_lists_only_active_templates_of_its_app(app, state, admin, creator, ws):
    await create_template(creator)
    await create_template(creator, {**GHIBLI, "slug": "draft-one", "title": "Draft"}, activate=False)
    other = await make_app(state, slug="other-app", name="Other")
    await join(state, other.id, creator.user, "editor")
    r = await creator.post(f"/v1/apps/{other.id}/manage/templates", json={**GHIBLI, "slug": "elsewhere"})
    assert r.status_code == 201

    android = await key_client(app, admin, ws.id)
    catalog = (await android.get("/v1/app/templates")).json()
    assert catalog["app"]["name"] == "Workspace"
    assert [t["slug"] for t in catalog["templates"]] == ["ghibli-fake"]
    assert "prompt" not in catalog["templates"][0]
    assert (await android.get("/v1/app/templates/elsewhere")).status_code == 404
    assert (await android.get("/v1/app/templates/draft-one")).status_code == 404
    assert (await creator.get(creator.ws + "/catalog")).json() == catalog


async def test_client_runs_a_template_and_fetches_the_result(app, state, admin, creator, ws):
    await create_template(creator, FREE)  # signed-out app-key runs: free templates only
    android = await key_client(app, admin, ws.id)
    r = await android.post(
        "/v1/app/templates/ghibli-fake/generations", files=PHOTO, data={"variables": '{"mood": "rainy"}'}
    )
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["app"]["slug"] == "workspace" and job["created_by"] is None
    assert "prompt" not in job["request"] and job["app"]["device_id"] is None
    await run_worker_once(state)
    job = (await android.get(f"/v1/app/generations/{job['id']}")).json()
    assert job["status"] == "succeeded"
    url = job["assets"][0]["url"]
    assert url.startswith("/v1/app/assets/")
    got = await android.get(url)
    assert got.status_code == 200 and got.headers["content-type"] == "image/png"
    assert (await android.get(job["inputs"][0]["url"])).status_code == 200
    assert [j["id"] for j in (await android.get("/v1/app/generations")).json()] == [job["id"]]
    seen = (await creator.get(f"/v1/generations/{job['id']}")).json()
    assert seen["app"]["device_id"] == "device-1" and seen["request"]["prompt"].startswith("Redraw")
    from_clients = (await creator.get(creator.ws + "/generations", params={"source": "app"})).json()
    assert [j["id"] for j in from_clients["items"]] == [job["id"]]


async def test_client_jobs_are_private_to_their_device(app, state, admin, creator, tester, ws):
    await create_template(creator, FREE)  # signed-out app-key runs: free templates only
    one = await key_client(app, admin, ws.id, device="device-1")
    job = (await one.post("/v1/app/templates/ghibli-fake/generations", files=PHOTO)).json()
    console_job = (await tester.post(tester.ws + "/templates/ghibli-fake/generations", files=PHOTO)).json()
    await run_worker_once(state)
    await run_worker_once(state)
    other_device = await key_client(app, admin, ws.id, device="device-2")
    assert (await other_device.get(f"/v1/app/generations/{job['id']}")).status_code == 404
    asset_url = (await one.get(f"/v1/app/generations/{job['id']}")).json()["assets"][0]["url"]
    assert (await other_device.get(asset_url)).status_code == 404
    # console tests are not visible to the app's clients
    assert (await one.get(f"/v1/app/generations/{console_job['id']}")).status_code == 404


async def test_keys_disabled_apps_and_bad_keys(app, admin, creator, ws):
    await create_template(creator)
    android = await key_client(app, admin, ws.id)
    assert (await android.get("/v1/app/templates")).status_code == 200
    bad = client(app)
    bad.headers["X-App-Key"] = "cak_nope"
    assert (await bad.get("/v1/app/templates")).status_code == 401
    assert (await client(app).get("/v1/app/templates")).status_code == 401
    assert (await android.get("/v1/apps")).status_code == 401  # an app key is not a user

    body = {"name": "Workspace", "status": "disabled"}
    assert (await admin.put(f"/v1/admin/apps/{ws.id}", json=body)).status_code == 200
    r = await android.get("/v1/app/templates")
    assert r.status_code == 403 and r.json()["error"]["code"] == "app_disabled"
    await admin.put(f"/v1/admin/apps/{ws.id}", json={**body, "status": "active"})

    keys = (await admin.get(f"/v1/admin/apps/{ws.id}/keys")).json()
    assert "key" not in keys[0] and keys[0]["prefix"] == android.key[:8]
    assert (await admin.delete(f"/v1/admin/apps/{ws.id}/keys/{keys[0]['id']}")).status_code == 204
    assert (await android.get("/v1/app/templates")).status_code == 401


async def test_limits_count_client_jobs_only(app, admin, creator, ws):
    await create_template(creator, FREE)  # signed-out app-key runs: free templates only
    body = {"name": "Workspace", "device_hourly_limit": 1, "daily_job_limit": 2}
    await admin.put(f"/v1/admin/apps/{ws.id}", json=body)
    for _ in range(3):  # console tests don't use up the app's quota
        r = await creator.post(creator.ws + "/templates/ghibli-fake/generations", files=PHOTO)
        assert r.status_code == 202
    d1 = await key_client(app, admin, ws.id, device="d1")
    d2 = await key_client(app, admin, ws.id, device="d2")
    d3 = await key_client(app, admin, ws.id, device="d3")
    url = "/v1/app/templates/ghibli-fake/generations"
    assert (await d1.post(url, files=PHOTO)).status_code == 202
    r = await d1.post(url, files=PHOTO)
    assert r.status_code == 429 and "device" in r.json()["error"]["message"]
    assert (await d2.post(url, files=PHOTO)).status_code == 202
    r = await d3.post(url, files=PHOTO)
    assert r.status_code == 429 and "daily" in r.json()["error"]["message"]
    usage = (await admin.get(f"/v1/admin/apps/{ws.id}")).json()["usage"]
    assert usage == {"jobs_24h": 2, "devices_24h": 2}


async def test_clients_cannot_pick_versions_or_webhooks(app, admin, creator, ws):
    await create_template(creator)
    android = await key_client(app, admin, ws.id)
    for extra in ({"version": "1"}, {"webhook_url": "https://x.example"}):
        r = await android.post("/v1/app/templates/ghibli-fake/generations", files=PHOTO, data=extra)
        assert r.status_code == 422


async def test_bad_device_id_is_rejected(app, admin, ws):
    android = await key_client(app, admin, ws.id, device="has spaces!")
    assert (await android.get("/v1/app/templates")).status_code == 400


async def test_template_cover_image(app, admin, creator, tester, ws):
    cover = {"file": ("cover.png", image_bytes(fmt="PNG"), "image/png")}
    up = await creator.post(creator.ws + "/uploads", files=cover)
    assert up.status_code == 201
    await create_template(creator, {**GHIBLI, "cover_upload": up.json()["id"]})
    android = await key_client(app, admin, ws.id)
    cover_url = (await android.get("/v1/app/templates")).json()["templates"][0]["cover_url"]
    assert cover_url.startswith("/v1/app/templates/ghibli-fake/cover")
    assert (await android.get(cover_url)).headers["content-type"] == "image/png"
    public = (await tester.get(tester.ws + "/templates")).json()[0]["cover_url"]
    assert public.startswith(tester.ws)
    assert (await tester.get(public)).status_code == 200
    body = {**GHIBLI, "slug": "x-cover", "cover_upload": "nope"}
    assert (await creator.post(creator.ws + "/manage/templates", json=body)).status_code == 422


async def test_copy_carries_cover_and_reference_images(app, state, creator):
    other = await make_app(state, slug="other-app", name="Other")
    await join(state, other.id, creator.user, "editor")
    png = {"file": ("x.png", image_bytes(fmt="PNG"), "image/png")}
    cover = (await creator.post(creator.ws + "/uploads", files=png)).json()["id"]
    ref = (await creator.post(creator.ws + "/uploads", files=png)).json()["id"]
    t = await create_template(creator, {**GHIBLI, "cover_upload": cover, "reference_uploads": [ref]})
    r = await creator.post(
        f"{creator.ws}/manage/templates/{t['id']}/copy", json={"target_app_id": str(other.id)}
    )
    assert r.status_code == 201, r.text
    copy = r.json()["template"]
    assert copy["current"]["cover_upload"] not in (None, cover)
    assert len(copy["current"]["reference_uploads"]) == 1 and copy["current"]["reference_uploads"][0] != ref
    other_base = f"/v1/apps/{other.id}"
    got = await creator.get(f"{other_base}/uploads/{copy['current']['cover_upload']}")
    assert got.status_code == 200 and got.headers["content-type"] == "image/png"
    # the copy works: activate it and run it in the other app
    await creator.post(f"{other_base}/manage/templates/{copy['id']}/status", json={"status": "active"})
    run = await creator.post(f"{other_base}/templates/ghibli-fake/generations", files=PHOTO)
    assert run.status_code == 202
    await run_worker_once(state)
    job = (await creator.get(f"/v1/generations/{run.json()['id']}")).json()
    assert job["status"] == "succeeded" and sorted(i["role"] for i in job["inputs"]) == ["input", "reference"]
