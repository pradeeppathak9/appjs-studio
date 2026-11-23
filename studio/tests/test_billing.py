"""Credits, plans and subscriptions of an app's end users."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from studio.endusers.billing import add_months
from studio.endusers.credits import refund_failed
from tests.conftest import (
    GHIBLI,
    app_client,
    create_template,
    image_bytes,
    member,
    run_worker_once,
    sign_in_phone,
)

EDITOR = ("ed@example.com", "Ed", "editor-password-1")


def photo():
    return {"photo": ("me.jpg", image_bytes(), "image/jpeg")}


async def setup_app(app, state, cost=2, prompt=None, **fields):
    """A Reelify-like app (login required) with one template costing `cost`, and a signed-in user."""
    c = await app_client(app, state, require_login=True, **fields)
    editor = await member(app, state, c.app_row, "editor", EDITOR)
    body = {**GHIBLI, "credit_cost": cost}
    if prompt:
        body["prompt"] = prompt
    t = await create_template(editor, body)
    await sign_in_phone(c, state)
    c.editor = editor
    c.template = t
    return c


async def credits_of(c) -> int:
    return (await c.get("/v1/app/me")).json()["credits"]


async def give(admin, c, delta, note="test"):
    r = await admin.post(
        f"/v1/admin/apps/{c.app_row.id}/users/{c.user_id}/credits", json={"delta": delta, "note": note}
    )
    assert r.status_code == 200, r.text
    return r.json()["credits"]


# ---- template cost -------------------------------------------------------------------------------------


async def test_credit_cost_is_set_by_editors_and_shown_to_the_app(app, state):
    c = await setup_app(app, state, cost=3)
    assert c.template["credit_cost"] == 3
    assert (await c.get("/v1/app/templates")).json()["templates"][0]["credit_cost"] == 3
    base = c.editor.ws + f"/manage/templates/{c.template['id']}"
    full = (await c.editor.get(base)).json()
    body = {
        k: full["current"][k]
        for k in (
            "title",
            "description",
            "media_type",
            "provider",
            "model",
            "allowed_models",
            "prompt",
            "inputs",
            "variables",
        )
    }
    r = await c.editor.put(base, json={**body, "base_version": full["current_version"], "credit_cost": 5})
    assert r.status_code == 200, r.text
    assert r.json()["template"]["credit_cost"] == 5
    r = await c.editor.put(base, json={**body, "base_version": full["current_version"] + 1})
    assert r.json()["template"]["credit_cost"] == 5  # left out = unchanged
    r = await c.editor.put(
        base, json={**body, "base_version": full["current_version"] + 2, "credit_cost": -1}
    )
    assert r.status_code == 422


# ---- charging -------------------------------------------------------------------------------------------


async def test_a_run_needs_enough_credits_and_charges_them(app, state, admin):
    c = await setup_app(app, state, cost=2)
    r = await c.post("/v1/app/templates/ghibli-fake/generations", files=photo())
    assert r.status_code == 402
    assert r.json()["error"]["code"] == "insufficient_credits"
    assert r.json()["error"]["details"] == [{"credits": 0, "required": 2}]
    async with state.engine.begin() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM jobs"))).scalar() == 0

    await give(admin, c, 5)
    r = await c.post("/v1/app/templates/ghibli-fake/generations", files=photo())
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["credits"] == 3  # the balance after the charge, for the app to show at once
    assert await credits_of(c) == 3
    history = (await c.get("/v1/app/me/credits")).json()
    assert [(e["reason"], e["delta"]) for e in history] == [("generation", -2), ("admin_adjust", 5)]
    assert history[0]["job_id"] == job["id"]

    await run_worker_once(state)
    done = (await c.get(f"/v1/app/generations/{job['id']}")).json()
    assert done["status"] == "succeeded"
    assert await credits_of(c) == 3  # success keeps the charge
    assert [j["id"] for j in (await c.get("/v1/app/generations")).json()] == [job["id"]]


async def test_jobs_belong_to_the_user_not_the_device(app, state, admin):
    c = await setup_app(app, state, cost=1)
    await give(admin, c, 1)
    job = (await c.post("/v1/app/templates/ghibli-fake/generations", files=photo())).json()
    await run_worker_once(state)
    asset = (await c.get(f"/v1/app/generations/{job['id']}")).json()["assets"][0]["url"]
    assert (await c.get(asset)).status_code == 200

    # another user on the same device sees nothing of it
    from tests.conftest import with_device

    other = with_device(c, app, "device-1")
    await sign_in_phone(other, state, "9123456789")
    assert (await other.get(f"/v1/app/generations/{job['id']}")).status_code == 404
    assert (await other.get(asset)).status_code == 404
    assert (await other.get("/v1/app/generations")).json() == []


async def test_failed_jobs_are_refunded_once(app, state, admin):
    c = await setup_app(app, state, cost=2, prompt="FAIL_POLICY {{mood}}")
    await give(admin, c, 2)
    job = (await c.post("/v1/app/templates/ghibli-fake/generations", files=photo())).json()
    assert await credits_of(c) == 0
    await run_worker_once(state)
    failed = (await c.get(f"/v1/app/generations/{job['id']}")).json()
    assert failed["status"] == "failed" and failed["error"]["code"] == "content_policy"
    assert await credits_of(c) == 2
    async with state.db.begin() as s:  # a second refund of the same job does nothing
        await refund_failed(s, [uuid.UUID(job["id"])])
    assert await credits_of(c) == 2
    reasons = [e["reason"] for e in (await c.get("/v1/app/me/credits")).json()]
    assert reasons == ["refund", "generation", "admin_adjust"]


async def test_jobs_lost_with_their_worker_are_refunded(app, state, admin):
    c = await setup_app(app, state, cost=1)
    await give(admin, c, 1)
    job = (await c.post("/v1/app/templates/ghibli-fake/generations", files=photo())).json()
    async with state.engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE jobs SET status='running', attempt=max_attempts, worker_id='gone', "
                "heartbeat_at = now() - interval '1 hour'"
            )
        )
    _, failed = await state.queue.requeue_stale(60)
    assert [str(x) for x in failed] == [job["id"]]
    assert await credits_of(c) == 1


async def test_parallel_runs_cannot_overspend(app, state, admin):
    c = await setup_app(app, state, cost=1)
    await give(admin, c, 1)
    results = await asyncio.gather(
        *[c.post("/v1/app/templates/ghibli-fake/generations", files=photo()) for _ in range(3)]
    )
    assert sorted(r.status_code for r in results) == [202, 402, 402]
    assert await credits_of(c) == 0
    async with state.engine.begin() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM jobs"))).scalar() == 1


async def test_without_require_login_only_free_templates_run_signed_out(app, state, admin):
    c = await app_client(app, state)  # no require_login, nobody signed in
    editor = await member(app, state, c.app_row, "editor", EDITOR)
    await create_template(editor, {**GHIBLI, "credit_cost": 5})
    free = await create_template(editor, {**GHIBLI, "slug": "free-fake", "credit_cost": 0})

    # the app key alone can be pulled out of the app: it must not run paid templates
    r = await c.post("/v1/app/templates/ghibli-fake/generations", files=photo())
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthenticated"
    async with state.engine.begin() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM jobs"))).scalar() == 0
    r = await c.post(f"/v1/app/templates/{free['slug']}/generations", files=photo())
    assert r.status_code == 202 and r.json()["credits"] is None

    # signed in (optional for this app), the same template is checked and charged
    await sign_in_phone(c, state)
    assert (await c.post("/v1/app/templates/ghibli-fake/generations", files=photo())).status_code == 402
    await give(admin, c, 6)
    r = await c.post("/v1/app/templates/ghibli-fake/generations", files=photo())
    assert r.status_code == 202 and r.json()["credits"] == 1
    assert await credits_of(c) == 1


async def test_console_runs_are_never_charged(app, state):
    c = await setup_app(app, state, cost=3)
    r = await c.editor.post(c.editor.ws + "/templates/ghibli-fake/generations", files=photo())
    assert r.status_code == 202, r.text


# ---- admin: credits and users -----------------------------------------------------------------------------


async def test_admin_adjusts_credits_and_finds_users(app, state, admin):
    c = await setup_app(app, state)
    assert await give(admin, c, 10, "welcome") == 10
    base = f"/v1/admin/apps/{c.app_row.id}/users"
    r = await admin.post(f"{base}/{c.user_id}/credits", json={"delta": -11, "note": "too much"})
    assert r.status_code == 422
    assert await give(admin, c, -4, "correction") == 6
    page = (await admin.get(base, params={"q": "98765"})).json()
    assert [u["id"] for u in page["items"]] == [c.user_id] and page["total"] == 1
    assert page["items"][0]["credits"] == 6
    assert (await admin.get(base, params={"q": c.user_id})).json()["total"] == 1  # by id
    assert (await admin.get(base, params={"q": "nobody"})).json() == {
        "items": [],
        "total": 0,
        "limit": 25,
        "offset": 0,
    }
    assert (await admin.get(base, params={"q": "%"})).json()["total"] == 0  # wildcards are literal
    detail = (await admin.get(f"{base}/{c.user_id}")).json()
    assert [(e["delta"], e["note"]) for e in detail["ledger"]] == [(-4, "correction"), (10, "welcome")]


async def test_admin_pages_through_users_and_their_credit_history(app, state, admin):
    c = await setup_app(app, state)
    from tests.conftest import with_device

    for i in range(4):  # 5 users in all, newest first
        other = with_device(c, app, f"device-{i}")
        await sign_in_phone(other, state, f"91234567{i:02d}")
    base = f"/v1/admin/apps/{c.app_row.id}/users"
    first = (await admin.get(base, params={"limit": 2})).json()
    second = (await admin.get(base, params={"limit": 2, "offset": 2})).json()
    last = (await admin.get(base, params={"limit": 2, "offset": 4})).json()
    assert first["total"] == second["total"] == last["total"] == 5
    ids = [u["id"] for p in (first, second, last) for u in p["items"]]
    assert len(ids) == len(set(ids)) == 5 and ids[-1] == c.user_id  # the oldest comes last
    assert (await admin.get(base, params={"limit": 201})).status_code == 422

    for n in range(3):
        await give(admin, c, n + 1, f"gift {n}")
    history = f"{base}/{c.user_id}/credits"
    p1 = (await admin.get(history, params={"limit": 2})).json()
    p2 = (await admin.get(history, params={"limit": 2, "offset": 2})).json()
    assert p1["total"] == 3 and [e["note"] for e in p1["items"] + p2["items"]] == [
        "gift 2",
        "gift 1",
        "gift 0",
    ]
    unknown = f"{base}/{uuid.uuid4()}/credits"  # not a user of this app
    assert (await admin.get(unknown)).status_code == 404


# ---- plans and subscriptions ----------------------------------------------------------------------------


MONTHLY = {
    "slug": "monthly",
    "name": "Monthly",
    "price_minor": 19900,
    "billing_period": "month",
    "credits_per_month": 40,
}
YEARLY = {
    **MONTHLY,
    "slug": "yearly",
    "name": "Yearly",
    "price_minor": 149900,
    "billing_period": "year",
    "badge": "Best value",
}


async def test_plans_are_managed_by_admins_and_listed_for_the_app(app, state, admin):
    c = await setup_app(app, state)
    base = f"/v1/admin/apps/{c.app_row.id}/plans"
    m = (await admin.post(base, json=MONTHLY)).json()
    y = (await admin.post(base, json=YEARLY)).json()
    assert (await admin.post(base, json=MONTHLY)).status_code == 409
    listed = (await c.get("/v1/app/plans")).json()
    assert [(p["slug"], p["price_minor"], p["credits_per_month"]) for p in listed] == [
        ("monthly", 19900, 40),
        ("yearly", 149900, 40),
    ]
    assert (await admin.put(f"{base}/order", json={"plan_ids": [y["id"], m["id"]]})).status_code == 204
    assert [p["slug"] for p in (await c.get("/v1/app/plans")).json()] == ["yearly", "monthly"]
    r = await admin.put(f"{base}/{m['id']}", json={**MONTHLY, "credits_per_month": 50, "status": "archived"})
    assert r.json()["credits_per_month"] == 50
    assert [p["slug"] for p in (await c.get("/v1/app/plans")).json()] == ["yearly"]
    assert (await admin.delete(f"{base}/{m['id']}")).status_code == 204  # unused: really deleted
    assert [p["slug"] for p in (await admin.get(base)).json()] == ["yearly"]


async def test_a_granted_subscription_gives_credits_now_and_monthly(app, state, admin):
    c = await setup_app(app, state)
    plan = (await admin.post(f"/v1/admin/apps/{c.app_row.id}/plans", json=MONTHLY)).json()
    users = f"/v1/admin/apps/{c.app_row.id}/users/{c.user_id}"
    r = await admin.post(f"{users}/subscriptions", json={"plan_id": plan["id"]})
    assert r.status_code == 201, r.text
    sub = r.json()
    assert sub["status"] == "active" and sub["plan"]["slug"] == "monthly"
    assert sub["next_credit_grant_at"] is None  # a monthly plan's period is one grant long
    me = (await c.get("/v1/app/me")).json()
    assert me["credits"] == 40 and me["subscription"]["id"] == sub["id"]
    r = await admin.post(f"{users}/subscriptions", json={"plan_id": plan["id"]})
    assert r.status_code == 409

    later = datetime.now(UTC) + timedelta(days=40)
    await state.billing.grant_due_credits(later)
    me = (await c.get("/v1/app/me")).json()
    assert me["credits"] == 40 and me["subscription"] is None  # expired, nothing more granted
    detail = (await admin.get(users)).json()
    assert detail["subscriptions"][0]["status"] == "expired"


async def test_a_yearly_plan_grants_every_month_for_a_year(app, state, admin):
    c = await setup_app(app, state)
    plan = (await admin.post(f"/v1/admin/apps/{c.app_row.id}/plans", json=YEARLY)).json()
    users = f"/v1/admin/apps/{c.app_row.id}/users/{c.user_id}"
    sub = (await admin.post(f"{users}/subscriptions", json={"plan_id": plan["id"]})).json()
    start = datetime.fromisoformat(sub["current_period_start"])
    assert datetime.fromisoformat(sub["next_credit_grant_at"]) == add_months(start, 1)

    assert await state.billing.grant_due_credits(add_months(start, 1)) == 1
    assert await state.billing.grant_due_credits(add_months(start, 1)) == 0  # idempotent
    assert await credits_of(c) == 80
    # a worker that was down for months catches up, and the plan ends after 12 grants
    await state.billing.grant_due_credits(add_months(start, 13))
    assert await credits_of(c) == 40 * 12
    assert (await c.get("/v1/app/me")).json()["subscription"] is None
    notes = [e["note"] for e in (await c.get("/v1/app/me/credits", params={"limit": 100})).json()]
    assert notes[0] == "Yearly: month 12" and notes[-1] == "Yearly: month 1"


async def test_cancelling_stops_future_grants(app, state, admin):
    c = await setup_app(app, state)
    plan = (await admin.post(f"/v1/admin/apps/{c.app_row.id}/plans", json=YEARLY)).json()
    users = f"/v1/admin/apps/{c.app_row.id}/users/{c.user_id}"
    sub = (await admin.post(f"{users}/subscriptions", json={"plan_id": plan["id"]})).json()
    assert (await admin.delete(f"{users}/subscriptions/{sub['id']}")).status_code == 204
    assert (await admin.delete(f"{users}/subscriptions/{sub['id']}")).status_code == 409
    await state.billing.grant_due_credits(datetime.now(UTC) + timedelta(days=100))
    assert await credits_of(c) == 40
    # a used plan is archived, not deleted
    assert (await admin.delete(f"/v1/admin/apps/{c.app_row.id}/plans/{plan['id']}")).status_code == 204
    plans = (await admin.get(f"/v1/admin/apps/{c.app_row.id}/plans")).json()
    assert [(p["slug"], p["status"]) for p in plans] == [("yearly", "archived")]


def test_add_months_clamps_to_the_month_end():
    assert add_months(datetime(2026, 1, 31, tzinfo=UTC), 1) == datetime(2026, 2, 28, tzinfo=UTC)
    assert add_months(datetime(2026, 11, 15, tzinfo=UTC), 3) == datetime(2027, 2, 15, tzinfo=UTC)
    assert add_months(datetime(2028, 1, 31, tzinfo=UTC), 1) == datetime(2028, 2, 29, tzinfo=UTC)


async def test_workers_run_the_monthly_grants(app, state, admin):
    from studio.main import make_worker

    c = await setup_app(app, state)
    plan = (await admin.post(f"/v1/admin/apps/{c.app_row.id}/plans", json=YEARLY)).json()
    users = f"/v1/admin/apps/{c.app_row.id}/users/{c.user_id}"
    await admin.post(f"{users}/subscriptions", json={"plan_id": plan["id"]})
    async with state.engine.begin() as conn:
        await conn.execute(  # a month has passed
            text(
                "UPDATE subscriptions SET current_period_start = current_period_start - interval '1 month', "
                "next_credit_grant_at = current_period_start"
            )
        )
    worker = make_worker(state)
    await worker.billing_sweep()
    assert await credits_of(c) == 80
    await worker.billing_sweep()  # throttled: nothing new even if due again
    assert await credits_of(c) == 80


async def test_admin_links_a_subscription_to_its_gateway_id(app, state, admin):
    c = await setup_app(app, state)
    plan = (await admin.post(f"/v1/admin/apps/{c.app_row.id}/plans", json=MONTHLY)).json()
    base = f"/v1/admin/apps/{c.app_row.id}/users/{c.user_id}"
    sub = (await admin.post(f"{base}/subscriptions", json={"plan_id": plan["id"]})).json()
    link = f"{base}/subscriptions/{sub['id']}/link"

    r = await admin.put(link, json={"provider": "razorpay", "provider_ref": "sub_Abc123XYZ"})
    assert r.status_code == 200, r.text
    assert (r.json()["provider"], r.json()["provider_ref"]) == ("razorpay", "sub_Abc123XYZ")
    detail = (await admin.get(base)).json()
    assert detail["subscriptions"][0]["provider_ref"] == "sub_Abc123XYZ"
    assert "provider_ref" not in (await c.get("/v1/app/me")).json()["subscription"]  # admins only

    assert (
        await admin.put(link, json={"provider": "razorpay", "provider_ref": "pay_123"})
    ).status_code == 422
    assert (await admin.put(link, json={"provider": "phonepe"})).status_code == 422
    r = await admin.put(link, json={"provider": "phonepe", "provider_ref": "MS-2026-0001"})
    assert r.json()["provider_ref"] == "MS-2026-0001"

    # one gateway subscription pays for one subscription only
    from tests.conftest import with_device

    other = with_device(c, app, "device-9")
    other_user = (await sign_in_phone(other, state, "9123456700"))["user"]["id"]
    other_base = f"/v1/admin/apps/{c.app_row.id}/users/{other_user}"
    other_sub = (await admin.post(f"{other_base}/subscriptions", json={"plan_id": plan["id"]})).json()
    r = await admin.put(
        f"{other_base}/subscriptions/{other_sub['id']}/link",
        json={"provider": "phonepe", "provider_ref": "MS-2026-0001"},
    )
    assert r.status_code == 409
    # the subscription must belong to the user in the path
    r = await admin.put(f"{other_base}/subscriptions/{sub['id']}/link", json={"provider": "manual"})
    assert r.status_code == 404

    r = await admin.put(link, json={"provider": "manual", "provider_ref": "ignored"})
    assert (r.json()["provider"], r.json()["provider_ref"]) == ("manual", None)
