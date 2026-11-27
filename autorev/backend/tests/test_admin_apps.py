"""Admin app creation: Studio-style slug + name, 16-char ids."""
import pytest

from app.auth import create_access_token, hash_password
from app.models import AppUser, User


@pytest.fixture
def admin(db):
    user = User(email="admin@example.com", hashed_password=hash_password("x" * 12), is_admin=True)
    db.add(user)
    db.commit()
    return user, {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


def _create(client, auth, user_id, **body):
    return client.post("/api/admin/apps", json={"user_id": user_id, "razorpay_enabled": True,
                                                "phonepe_enabled": False, **body}, headers=auth)


def test_create_returns_slug_name_and_short_id(client, db, admin):
    user, auth = admin
    r = _create(client, auth, user.id, slug="marktmakrs-web", name="MarktMakrs Web")
    assert r.status_code == 201, r.text
    app = r.json()
    assert app["slug"] == "marktmakrs-web" and app["name"] == "MarktMakrs Web"
    assert len(app["id"]) == 16 and int(app["id"], 16) >= 0
    assert db.query(AppUser).filter(AppUser.app_id == app["id"]).count() == 1

    listed = client.get("/api/apps", headers=auth).json()
    assert [(a["id"], a["slug"]) for a in listed] == [(app["id"], "marktmakrs-web")]


def test_duplicate_slug_is_a_conflict(client, admin):
    user, auth = admin
    assert _create(client, auth, user.id, slug="marktmakrs", name="Another").status_code == 409


@pytest.mark.parametrize("slug", ["ab", "Upper", "-dash", "dash-", "has space", "a" * 65])
def test_bad_slug_is_refused(client, admin, slug):
    user, auth = admin
    assert _create(client, auth, user.id, slug=slug, name="X").status_code == 422


def test_slug_cannot_be_changed(client, admin):
    user, auth = admin
    app = _create(client, auth, user.id, slug="fixed-slug", name="Fixed").json()
    r = client.patch(f"/api/admin/apps/{app['id']}", json={"slug": "other", "name": "Renamed"}, headers=auth)
    assert r.status_code == 200
    assert (r.json()["slug"], r.json()["name"]) == ("fixed-slug", "Renamed")
