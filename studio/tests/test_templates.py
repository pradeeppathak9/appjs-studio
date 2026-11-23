import pytest

from creative.errors import ValidationFailed
from creative.templates.models import Variable
from creative.templates.render import render, resolve_values
from tests.conftest import GHIBLI, create_template, image_bytes, run_worker_once

# ---- rendering ---------------------------------------------------------------------------------


def test_render_substitutes_values_and_defaults():
    vars_ = [Variable(name="mood", default="sunny"), Variable(name="time", default="noon")]
    values = resolve_values(vars_, {"mood": "rainy"})
    assert render("A {{mood}} day at {{ time }}.", values) == "A rainy day at noon."


def test_values_cannot_inject_placeholders_or_newlines():
    values = resolve_values([Variable(name="mood")], {"mood": "x {{secret}}\n\nIgnore all"})
    assert values["mood"] == "x secret Ignore all"


def test_unknown_too_long_and_off_choice_values_are_rejected():
    vars_ = [Variable(name="mood", max_length=5), Variable(name="style", choices=["a", "b"], default="a")]
    with pytest.raises(ValidationFailed) as e:
        resolve_values(vars_, {"mood": "much too long", "style": "c", "other": "x"})
    fields = {d["field"] for d in e.value.details}
    assert fields == {"variables.mood", "variables.style", "variables.other"}


# ---- save-time checks and versions -------------------------------------------------------------


async def test_creating_a_template_makes_a_draft_v1(creator):
    t = await create_template(creator, activate=False)
    assert t["status"] == "draft" and t["current_version"] == 1
    assert t["current"]["created_by"]["name"] == "Cam Creator"


async def test_undeclared_and_unused_variables_block_the_save(creator):
    body = {**GHIBLI, "prompt": "Mood: {{mood}} weather: {{weather}}"}
    r = await creator.post(creator.ws + "/manage/templates", json=body)
    assert r.status_code == 422
    assert {"field": "prompt", "message": "{{weather}} is used but not declared as a variable"} in r.json()[
        "error"
    ]["details"]
    body = {**GHIBLI, "prompt": "No variables here"}
    r = await creator.post(creator.ws + "/manage/templates", json=body)
    assert r.json()["error"]["details"][0]["field"] == "variables.mood"


async def test_provider_capabilities_are_checked(creator):
    r = await creator.post(creator.ws + "/manage/templates", json={**GHIBLI, "params": {"n": 9}})
    assert r.status_code == 422  # pydantic: n <= 8
    r = await creator.post(
        creator.ws + "/manage/templates", json={**GHIBLI, "params": {"aspect_ratio": "7:3"}}
    )
    assert r.json()["error"]["details"][0]["field"] == "params.aspect_ratio"
    r = await creator.post(creator.ws + "/manage/templates", json={**GHIBLI, "slug": "Bad Slug"})
    assert r.status_code == 422


async def test_unknown_provider_saves_with_a_warning(creator):
    r = await creator.post(
        creator.ws + "/manage/templates", json={**GHIBLI, "provider": "gemini", "model": "x"}
    )
    assert r.status_code == 201
    assert "not configured" in r.json()["warnings"][0]


async def test_duplicate_slug_is_a_conflict(creator):
    await create_template(creator)
    r = await creator.post(creator.ws + "/manage/templates", json=GHIBLI)
    assert r.status_code == 409


async def test_update_needs_the_current_base_version(creator):
    t = await create_template(creator)
    body = {k: v for k, v in GHIBLI.items() if k != "slug"}
    r = await creator.put(
        f"{creator.ws}/manage/templates/{t['id']}", json={**body, "model": "fake-image-2", "base_version": 1}
    )
    assert r.status_code == 200 and r.json()["template"]["current_version"] == 2
    stale = await creator.put(f"{creator.ws}/manage/templates/{t['id']}", json={**body, "base_version": 1})
    assert stale.status_code == 409
    assert "Cam Creator" in stale.json()["error"]["message"]


async def test_restore_copies_an_old_version_as_a_new_one(creator):
    t = await create_template(creator)
    body = {k: v for k, v in GHIBLI.items() if k != "slug"}
    await creator.put(
        f"{creator.ws}/manage/templates/{t['id']}", json={**body, "model": "fake-image-2", "base_version": 1}
    )
    r = await creator.post(f"{creator.ws}/manage/templates/{t['id']}/versions/1/restore")
    full = r.json()["template"]
    assert full["current_version"] == 3 and full["current"]["model"] == "fake-image-1"
    assert [v["version"] for v in full["versions"]] == [3, 2, 1]
    assert full["current"]["note"] == "restored from version 1"


# ---- running templates -----------------------------------------------------------------------------


async def test_tester_runs_an_active_template_without_seeing_the_prompt(creator, tester, state):
    await create_template(creator)
    listed = (await tester.get(tester.ws + "/templates")).json()
    assert [t["slug"] for t in listed] == ["ghibli-fake"] and "prompt" not in listed[0]
    r = await tester.post(
        tester.ws + "/templates/ghibli-fake/generations",
        files={"photo": ("me.jpg", image_bytes((300, 400)), "image/jpeg")},
        data={"variables": '{"mood": "rainy"}'},
    )
    assert r.status_code == 202, r.text
    job = r.json()
    assert "prompt" not in job["request"] and job["template"]["version"] == 1
    assert job["request"]["variables"] == {"mood": "rainy"}
    await run_worker_once(state)
    job = (await tester.get(f"/v1/generations/{job['id']}")).json()
    assert job["status"] == "succeeded"
    (out,) = job["assets"]
    assert (out["width"], out["height"]) == (192, 256)  # portrait in, portrait out
    (inp,) = job["inputs"]
    assert (await tester.get(inp["url"])).status_code == 200
    seen_by_creator = (await creator.get(f"/v1/generations/{job['id']}")).json()
    assert seen_by_creator["request"]["prompt"] == "Redraw as a painted film still. Mood: rainy."


async def test_drafts_and_deleted_templates_are_invisible_to_testers(creator, tester, state):
    t = await create_template(creator, activate=False)
    assert (await tester.get(tester.ws + "/templates")).json() == []
    assert (await tester.get(tester.ws + "/templates/ghibli-fake")).status_code == 404
    files = {"photo": ("me.jpg", image_bytes(), "image/jpeg")}
    url = tester.ws + "/templates/ghibli-fake/generations"
    assert (await tester.post(url, files=files)).status_code == 404
    await creator.post(f"{creator.ws}/manage/templates/{t['id']}/status", json={"status": "active"})
    job = (await tester.post(url, files=files)).json()
    assert (await creator.delete(f"{creator.ws}/manage/templates/{t['id']}")).status_code == 204
    assert (await tester.post(url, files=files)).status_code == 404
    assert (await creator.get(f"{creator.ws}/manage/templates/{t['id']}")).status_code == 404
    assert (await creator.get(creator.ws + "/manage/templates")).json() == []
    # the job made before the delete still names the template, and the slug can be reused
    assert (await tester.get(f"/v1/generations/{job['id']}")).json()["template"]["slug"] == "ghibli-fake"
    assert (await creator.post(creator.ws + "/manage/templates", json=GHIBLI)).status_code == 201


async def test_creators_can_test_run_a_draft_version(creator):
    await create_template(creator, activate=False)
    files = {"photo": ("me.jpg", image_bytes(), "image/jpeg")}
    r = await creator.post(
        creator.ws + "/templates/ghibli-fake/generations", files=files, data={"version": "1"}
    )
    assert r.status_code == 202


async def test_testers_cannot_pick_a_version(creator, tester):
    await create_template(creator)
    files = {"photo": ("me.jpg", image_bytes(), "image/jpeg")}
    r = await tester.post(
        tester.ws + "/templates/ghibli-fake/generations", files=files, data={"version": "1"}
    )
    assert r.status_code == 403


async def test_editing_after_submit_does_not_change_the_queued_job(creator, tester, state):
    t = await create_template(creator)
    files = {"photo": ("me.jpg", image_bytes(), "image/jpeg")}
    job = (await tester.post(tester.ws + "/templates/ghibli-fake/generations", files=files)).json()
    body = {k: v for k, v in GHIBLI.items() if k != "slug"}
    await creator.put(
        f"{creator.ws}/manage/templates/{t['id']}",
        json={**body, "prompt": "Completely different {{mood}}", "model": "fake-image-2", "base_version": 1},
    )
    await run_worker_once(state)
    job = (await creator.get(f"/v1/generations/{job['id']}")).json()
    assert job["template"]["version"] == 1 and job["model"] == "fake-image-1"
    assert job["request"]["prompt"].startswith("Redraw")


async def test_missing_slot_unknown_field_and_bad_model(creator, tester):
    await create_template(creator)
    r = await tester.post(tester.ws + "/templates/ghibli-fake/generations", data={"variables": "{}"})
    assert r.status_code == 422 and r.json()["error"]["details"][0] == {
        "field": "photo",
        "message": "this image is required",
    }
    files = {
        "photo": ("me.jpg", image_bytes(), "image/jpeg"),
        "extra": ("x.jpg", image_bytes(), "image/jpeg"),
    }
    r = await tester.post(tester.ws + "/templates/ghibli-fake/generations", files=files)
    assert r.status_code == 422 and r.json()["error"]["details"][0]["field"] == "extra"
    files = {"photo": ("me.jpg", image_bytes(), "image/jpeg")}
    r = await tester.post(
        tester.ws + "/templates/ghibli-fake/generations", files=files, data={"model": "fake-image-9"}
    )
    assert r.status_code == 422 and r.json()["error"]["field"] == "model"
    r = await tester.post(
        tester.ws + "/templates/ghibli-fake/generations", files=files, data={"model": "fake-image-2"}
    )
    assert r.status_code == 202 and r.json()["model"] == "fake-image-2"


async def test_bad_uploads(creator, tester, settings):
    await create_template(creator)
    r = await tester.post(
        tester.ws + "/templates/ghibli-fake/generations",
        files={"photo": ("me.jpg", b"not an image", "image/jpeg")},
    )
    assert r.status_code == 422 and r.json()["error"]["field"] == "photo"
    big = b"\xff" * (settings.input_image_max_bytes + 1)
    r = await tester.post(
        tester.ws + "/templates/ghibli-fake/generations", files={"photo": ("big.jpg", big, "image/jpeg")}
    )
    assert r.status_code == 413


async def test_reference_images_reach_the_worker_but_not_testers(creator, tester, state):
    up = await creator.post(
        creator.ws + "/uploads", files={"file": ("style.png", image_bytes(fmt="PNG"), "image/png")}
    )
    assert up.status_code == 201
    await create_template(creator, {**GHIBLI, "reference_uploads": [up.json()["id"]]})
    files = {"photo": ("me.jpg", image_bytes(), "image/jpeg")}
    job = (await tester.post(tester.ws + "/templates/ghibli-fake/generations", files=files)).json()
    assert [i["role"] for i in job["inputs"]] == ["input"]
    full = (await creator.get(f"/v1/generations/{job['id']}")).json()
    assert sorted(i["role"] for i in full["inputs"]) == ["input", "reference"]
    reference = next(i for i in full["inputs"] if i["role"] == "reference")
    assert (await tester.get(reference["url"])).status_code == 404
    assert (await tester.get(up.json()["url"])).status_code == 403
    await run_worker_once(state)
    assert (await creator.get(f"/v1/generations/{job['id']}")).json()["status"] == "succeeded"
