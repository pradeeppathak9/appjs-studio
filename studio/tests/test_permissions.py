"""Every route declares who may call it, and the declared access matches this table."""

import pytest
from fastapi.routing import APIRoute

from creative.api import (
    admin,
    admin_endusers,
    assets,
    auth,
    client,
    client_auth,
    generations,
    meta,
    templates,
)
from creative.auth.service import AppRole, Role
from creative.deps import AppKeyDep, AppRoleDep, AppUserDep, RoleDep
from tests.conftest import create_template, image_bytes, join, make_app, run_worker_once, signed_in

ROUTERS = [
    meta.router,
    auth.router,
    generations.router,
    assets.router,
    templates.apps_router,
    templates.router,
    templates.manage,
    admin.router,
    admin_endusers.router,
    client_auth.router,
    client.router,
]
GUARDS = RoleDep | AppRoleDep | AppKeyDep | AppUserDep


def _guards(dependant) -> list:
    found = [d.call for d in dependant.dependencies if isinstance(d.call, GUARDS)]
    for d in dependant.dependencies:
        found += _guards(d)
    return found


def all_routes() -> list[APIRoute]:
    return [r for router in ROUTERS for r in router.routes if isinstance(r, APIRoute)]


def access(route: APIRoute) -> str:
    """'public', 'user', 'admin', 'app:tester', 'app:editor', 'app-key', 'app-key+login-if-required'
    or 'app-user' (the strictest guard)."""
    names = []
    for g in _guards(route.dependant):
        if isinstance(g, AppKeyDep):
            names.append("app-key")
        elif isinstance(g, AppUserDep):
            names.append("app-user" if g.required else "app-key+login-if-required")
        elif isinstance(g, AppRoleDep):
            names.append(f"app:{g.min_role.name}")
        elif g.min_role is None:
            names.append("public")
        else:
            names.append(g.min_role.name)
    rank = [
        "public",
        "user",
        "app:tester",
        "app:editor",
        "admin",
        "app-key",
        "app-key+login-if-required",
        "app-user",
    ]
    return max(names, key=rank.index) if names else "none"


def test_every_route_declares_access(app):
    missing = [f"{sorted(r.methods)} {r.path}" for r in all_routes() if access(r) == "none"]
    assert missing == []


def test_the_routers_listed_here_cover_the_whole_app(app):
    spec = app.openapi()["paths"]
    assert sum(len(v) for v in spec.values()) == sum(len(r.methods) for r in all_routes())


def test_every_admin_route_needs_admin():
    for r in [*admin.router.routes, *admin_endusers.router.routes]:
        assert access(r) == "admin", r.path


EXPECTED = {
    ("GET", "/healthz"): "public",
    ("POST", "/v1/auth/login"): "public",
    ("POST", "/v1/auth/setup"): "public",
    ("GET", "/v1/apps"): "user",
    ("GET", "/v1/generations/{job_id}"): "user",
    ("GET", "/v1/apps/{app_id}"): "app:tester",
    ("GET", "/v1/apps/{app_id}/templates"): "app:tester",
    ("POST", "/v1/apps/{app_id}/templates/{ref}/generations"): "app:tester",
    ("GET", "/v1/apps/{app_id}/generations"): "app:tester",
    ("POST", "/v1/apps/{app_id}/generations"): "app:editor",
    ("GET", "/v1/apps/{app_id}/catalog"): "app:editor",
    ("POST", "/v1/apps/{app_id}/uploads"): "app:editor",
    ("GET", "/v1/apps/{app_id}/manage/templates"): "app:editor",
    ("POST", "/v1/apps/{app_id}/manage/templates"): "app:editor",
    ("PUT", "/v1/apps/{app_id}/manage/templates/order"): "app:editor",
    ("PUT", "/v1/apps/{app_id}/manage/templates/{template_id}"): "app:editor",
    ("DELETE", "/v1/apps/{app_id}/manage/templates/{template_id}"): "app:editor",
    ("POST", "/v1/apps/{app_id}/manage/templates/{template_id}/copy"): "app:editor",
    ("GET", "/v1/admin/users"): "admin",
    ("DELETE", "/v1/admin/users/{user_id}"): "admin",
    ("POST", "/v1/admin/apps"): "admin",
    ("DELETE", "/v1/admin/apps/{app_id}"): "admin",
    ("PUT", "/v1/admin/apps/{app_id}/members/{user_id}"): "admin",
    ("POST", "/v1/admin/apps/{app_id}/keys"): "admin",
    ("GET", "/v1/app"): "app-key",
    ("POST", "/v1/app/auth/google"): "app-key",
    ("POST", "/v1/app/auth/otp/send"): "app-key",
    ("POST", "/v1/app/auth/otp/verify"): "app-key",
    ("GET", "/v1/app/plans"): "app-key",
    ("GET", "/v1/app/templates/{ref}/cover"): "app-key",
    ("POST", "/v1/app/auth/logout"): "app-user",
    ("GET", "/v1/app/me"): "app-user",
    ("PATCH", "/v1/app/me"): "app-user",
    ("DELETE", "/v1/app/me"): "app-user",
    ("GET", "/v1/app/me/credits"): "app-user",
    ("GET", "/v1/app/templates"): "app-key+login-if-required",
    ("GET", "/v1/app/templates/{ref}"): "app-key+login-if-required",
    ("POST", "/v1/app/templates/{ref}/generations"): "app-key+login-if-required",
    ("GET", "/v1/app/generations"): "app-key+login-if-required",
    ("GET", "/v1/app/generations/{job_id}"): "app-key+login-if-required",
    ("GET", "/v1/app/assets/{asset_id}"): "app-key+login-if-required",
    ("GET", "/v1/app/inputs/{input_id}"): "app-key+login-if-required",
    ("PATCH", "/v1/admin/apps/{app_id}"): "admin",
    ("GET", "/v1/admin/apps/{app_id}/plans"): "admin",
    ("POST", "/v1/admin/apps/{app_id}/users/{user_id}/credits"): "admin",
    ("GET", "/v1/admin/apps/{app_id}/users/{user_id}/credits"): "admin",
    ("PUT", "/v1/admin/apps/{app_id}/users/{user_id}/subscriptions/{subscription_id}/link"): "admin",
    ("POST", "/v1/admin/apps/{app_id}/users/{user_id}/subscriptions"): "admin",
}


def test_declared_access_matches_the_table():
    declared = {(m, r.path): access(r) for r in all_routes() for m in r.methods}
    for key, expected in EXPECTED.items():
        assert declared[key] == expected, key


def test_role_ranks():
    assert AppRole.tester < AppRole.editor < AppRole.admin
    assert Role.user < Role.admin


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/generations"),
        ("GET", "/manage/templates"),
        ("POST", "/manage/templates"),
        ("GET", "/catalog"),
        ("POST", "/uploads"),
    ],
)
async def test_tester_is_refused_editor_routes(tester, method, path):
    r = await tester.request(method, tester.ws + path, json={})
    assert r.status_code == 403


async def test_testers_see_only_their_own_jobs_and_files(app, state, creator, tester, ws):
    other = await signed_in(app, state, "user", ("other@example.com", "Other", "other-password-1"))
    await join(state, ws.id, other.user, "tester")
    await create_template(creator)
    files = {"photo": ("me.jpg", image_bytes(), "image/jpeg")}
    mine = (await tester.post(tester.ws + "/templates/ghibli-fake/generations", files=files)).json()
    await run_worker_once(state)
    mine = (await tester.get(f"/v1/generations/{mine['id']}")).json()
    assert (await other.get(f"/v1/generations/{mine['id']}")).status_code == 404
    assert (await other.get(mine["assets"][0]["url"])).status_code == 404
    assert (await other.get(mine["inputs"][0]["url"])).status_code == 404
    listed = await other.get(tester.ws + "/generations", params={"created_by": str(tester.user.id)})
    assert listed.json()["items"] == []
    assert len((await creator.get(creator.ws + "/generations")).json()["items"]) == 1


async def test_non_members_cannot_see_an_apps_jobs(app, state, creator, tester):
    outsider_app = await make_app(state, slug="elsewhere", name="Elsewhere")
    outsider = await signed_in(app, state, "user", ("out@example.com", "Out", "outsider-pass-1"))
    await join(state, outsider_app.id, outsider.user, "editor")
    await create_template(creator)
    files = {"photo": ("me.jpg", image_bytes(), "image/jpeg")}
    job = (await tester.post(tester.ws + "/templates/ghibli-fake/generations", files=files)).json()
    assert (await outsider.get(f"/v1/generations/{job['id']}")).status_code == 404
    assert (await outsider.get(tester.ws + "/generations")).status_code == 404


async def test_webhook_payload_hides_template_prompts(state, creator, tester):
    import uuid

    await create_template(creator)
    files = {"photo": ("me.jpg", image_bytes(), "image/jpeg")}
    job = (await tester.post(tester.ws + "/templates/ghibli-fake/generations", files=files)).json()
    payload = await state.generations.payload_for_webhook(uuid.UUID(job["id"]))
    assert "prompt" not in payload["request"]
