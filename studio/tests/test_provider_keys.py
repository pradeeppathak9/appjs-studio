"""An app's own AI provider keys: write-only settings, and its jobs run on them."""

import dataclasses
from collections import OrderedDict

import pytest
from sqlalchemy import select

from creative.db.tables import App
from creative.providers.fake import FakeProvider
from creative.secrets import SecretBox
from tests.conftest import GHIBLI, app_client, create_template, image_bytes, member, run_worker_once

EDITOR = ("ed@example.com", "Ed", "editor-password-1")
KEY = "AIzaSy-app-own-key-0001"
NONE_SET = {"gemini": False, "openai": False, "fal": False, "openrouter": False}

# a template on a provider the test server has no key for
GEMINI_TEMPLATE = {
    **GHIBLI,
    "slug": "gemini-style",
    "provider": "gemini",
    "model": "gemini-x",
    "allowed_models": [],
    "credit_cost": 0,
}


class KeyedFake(FakeProvider):
    """Stands in for Gemini built with an app's key; records the key each generation used."""

    capabilities = dataclasses.replace(
        FakeProvider.capabilities,
        name="gemini",
        default_image_model="gemini-x",
        known_image_models=("gemini-x",),
        image_input_models=("gemini-x",),
    )
    used: list[str] = []

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def generate_image(self, req):
        KeyedFake.used.append(self.api_key)
        return await super().generate_image(req)


@pytest.fixture
def secrets_key(state, monkeypatch):
    """The server has a SECRETS_KEY (the test settings don't)."""
    box = SecretBox("test-secrets-key-0123456789")
    monkeypatch.setattr(state.apps, "box", box)
    return box


@pytest.fixture
def keyed(state, monkeypatch):
    """Providers built from an app's key are KeyedFakes; nothing calls a real provider."""
    KeyedFake.used = []
    monkeypatch.setattr(
        state.registry, "factory", lambda name, key: KeyedFake(key) if name == "gemini" else None
    )
    monkeypatch.setattr(state.registry, "_keyed", OrderedDict())
    return KeyedFake


def photo():
    return {"photo": ("me.jpg", image_bytes(), "image/jpeg")}


async def test_provider_keys_are_write_only(app, state, admin, secrets_key):
    c = await app_client(app, state)
    url = f"/v1/admin/apps/{c.app_row.id}"
    assert (await admin.get(url)).json()["provider_keys_set"] == {
        "gemini": False,
        "openai": False,
        "fal": False,
        "openrouter": False,
    }

    r = await admin.patch(url, json={"gemini_api_key": KEY, "openai_api_key": "sk-proj-0123456789abc"})
    assert r.status_code == 200, r.text
    assert r.json()["provider_keys_set"] == {
        "gemini": True,
        "openai": True,
        "fal": False,
        "openrouter": False,
    }
    assert KEY not in r.text and "sk-proj" not in r.text and "gemini_api_key" not in r.json()
    async with state.db() as s:
        stored = await s.scalar(select(App.gemini_api_key_enc).where(App.id == c.app_row.id))
    assert KEY not in stored and secrets_key.decrypt(stored) == KEY

    # leaving a key out keeps it; null removes it
    r = await admin.patch(url, json={"name": "Renamed"})
    assert r.json()["provider_keys_set"]["gemini"] is True
    r = await admin.patch(url, json={"openai_api_key": None})
    assert r.json()["provider_keys_set"] == {
        "gemini": True,
        "openai": False,
        "fal": False,
        "openrouter": False,
    }

    bad = await admin.patch(url, json={"fal_api_key": "has a space in it"})
    assert bad.status_code == 422
    assert (await admin.patch(url, json={"fal_api_key": "short"})).status_code == 422


async def test_saving_a_key_needs_secrets_key(app, state, admin):
    c = await app_client(app, state)
    r = await admin.patch(f"/v1/admin/apps/{c.app_row.id}", json={"gemini_api_key": KEY})
    assert r.status_code == 503 and r.json()["error"]["code"] == "secrets_key_missing"


async def test_an_apps_jobs_run_on_its_own_key(app, state, admin, secrets_key, keyed):
    c = await app_client(app, state)
    editor = await member(app, state, c.app_row, "editor", EDITOR)

    # no key yet: the template saves with a warning, and runs are refused
    r = await editor.post(editor.ws + "/manage/templates", json=GEMINI_TEMPLATE)
    assert r.status_code == 201 and any("no key" in w for w in r.json()["warnings"])
    await editor.delete(editor.ws + f"/manage/templates/{r.json()['template']['id']}")

    await admin.patch(f"/v1/admin/apps/{c.app_row.id}", json={"gemini_api_key": KEY})
    await create_template(editor, GEMINI_TEMPLATE)
    job = (await c.post("/v1/app/templates/gemini-style/generations", files=photo())).json()
    assert job["status"] == "queued", job
    await run_worker_once(state)
    done = (await c.get(f"/v1/app/generations/{job['id']}")).json()
    assert done["status"] == "succeeded", done
    assert keyed.used == [KEY]

    # a new key is used from the next job on
    await admin.patch(f"/v1/admin/apps/{c.app_row.id}", json={"gemini_api_key": KEY + "-rotated"})
    job = (await c.post("/v1/app/templates/gemini-style/generations", files=photo())).json()
    await run_worker_once(state)
    assert keyed.used == [KEY, KEY + "-rotated"]

    # removing it: the app is back on the server's keys, which have no Gemini here
    await admin.patch(f"/v1/admin/apps/{c.app_row.id}", json={"gemini_api_key": None})
    r = await c.post("/v1/app/templates/gemini-style/generations", files=photo())
    assert r.status_code == 503, r.text


async def test_free_prompts_and_the_provider_list_see_the_apps_keys(app, state, admin, secrets_key, keyed):
    c = await app_client(app, state)
    editor = await member(app, state, c.app_row, "editor", EDITOR)
    names = lambda r: [p["name"] for p in r.json()]  # noqa: E731

    assert "gemini" not in names(await editor.get("/v1/providers", params={"app_id": str(c.app_row.id)}))
    await admin.patch(f"/v1/admin/apps/{c.app_row.id}", json={"gemini_api_key": KEY})
    assert "gemini" in names(await editor.get("/v1/providers", params={"app_id": str(c.app_row.id)}))
    assert "gemini" not in names(await editor.get("/v1/providers"))  # the server's own list is unchanged

    other = await app_client(app, state, slug="other-app")
    r = await editor.get("/v1/providers", params={"app_id": str(other.app_row.id)})
    assert r.status_code == 404  # not a member

    r = await editor.post(editor.ws + "/generations", json={"prompt": "a cat", "provider": "gemini"})
    assert r.status_code == 202, r.text
    await run_worker_once(state)
    assert keyed.used == [KEY]


async def test_one_provider_per_key_is_built_and_reused(state, keyed):
    reg = state.registry
    a1, a2, b = (
        reg.keyed("gemini", "key-a-0123456789"),
        reg.keyed("gemini", "key-a-0123456789"),
        reg.keyed("gemini", "key-b-0123456789"),
    )
    assert a1 is a2 and a1 is not b
    assert reg.keyed("fake", "whatever-0123456") is None  # only real providers take app keys
