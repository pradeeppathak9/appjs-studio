"""First-run setup: the setup token creates the first admin once, and the first admin stays protected."""
import pytest
from pydantic import SecretStr

from app import setup as first_run
from app.auth import create_access_token, hash_password
from app.config import settings
from app.models import User

BODY = {"setup_token": "tok-123", "email": "Owner@Example.com", "full_name": "Owner", "password": "a-long-password"}


class FakeRedis:
    def __init__(self):
        self.data: dict[str, str] = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, nx=False):
        if nx and key in self.data:
            return None
        self.data[key] = value
        return True

    def delete(self, key):
        self.data.pop(key, None)


@pytest.fixture
def redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(first_run, "redis_client", fake)
    return fake


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setattr(settings, "setup_token", SecretStr("tok-123"))


def test_setup_needed_until_an_admin_exists(client, redis, token):
    assert client.get("/api/auth/setup").json() == {"needed": True}
    r = client.post("/api/auth/setup", json=BODY)
    assert r.status_code == 201, r.text
    assert r.json()["user"]["email"] == "owner@example.com"
    assert r.json()["user"]["is_admin"] is True
    assert client.get("/api/auth/setup").json() == {"needed": False}


def test_setup_signs_the_admin_in(client, redis, token, monkeypatch):
    monkeypatch.setattr("app.router.auth.redis_client", FakeRedis())  # /me caches in Redis
    access = client.post("/api/auth/setup", json=BODY).json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200 and me.json()["email"] == "owner@example.com"


def test_wrong_token_is_refused(client, db, redis, token):
    r = client.post("/api/auth/setup", json={**BODY, "setup_token": "nope"})
    assert r.status_code == 403
    assert db.query(User).count() == 0


def test_setup_closes_after_the_first_admin(client, redis, token):
    assert client.post("/api/auth/setup", json=BODY).status_code == 201
    r = client.post("/api/auth/setup", json={**BODY, "email": "second@example.com"})
    assert r.status_code == 409


def test_existing_admin_means_no_setup(client, db, redis, token):
    db.add(User(email="old@example.com", hashed_password=hash_password("x" * 12), is_admin=True))
    db.commit()
    assert first_run.ensure_setup_token() is None
    assert client.post("/api/auth/setup", json=BODY).status_code == 409


def test_short_password_is_refused(client, redis, token):
    assert client.post("/api/auth/setup", json={**BODY, "password": "short"}).status_code == 422


def test_generated_token_is_shared_and_cleared(client, db, redis, monkeypatch):
    monkeypatch.setattr(settings, "setup_token", None)
    generated = first_run.ensure_setup_token()
    assert generated and first_run.ensure_setup_token() == generated  # every worker gets the same one
    r = client.post("/api/auth/setup", json={**BODY, "setup_token": generated})
    assert r.status_code == 201, r.text
    assert redis.get(first_run.REDIS_KEY) is None


def test_no_token_at_all_refuses_setup(client, redis, monkeypatch):
    monkeypatch.setattr(settings, "setup_token", None)
    assert client.post("/api/auth/setup", json=BODY).status_code == 403


def test_first_admin_is_protected(client, db, redis, token):
    assert client.post("/api/auth/setup", json=BODY).status_code == 201
    other = User(email="second@example.com", hashed_password=hash_password("x" * 12), is_admin=True)
    db.add(other)
    db.commit()
    other_auth = {"Authorization": f"Bearer {create_access_token({'sub': str(other.id)})}"}
    owner = db.query(User).filter(User.email == "owner@example.com").one()

    users = {u["email"]: u for u in client.get("/api/admin/users", headers=other_auth).json()}
    assert users["owner@example.com"]["is_protected"] is True
    assert users["second@example.com"]["is_protected"] is False
    assert client.patch(f"/api/admin/users/{owner.id}", json={"is_admin": False}, headers=other_auth).status_code == 400
    assert client.delete(f"/api/admin/users/{owner.id}", headers=other_auth).status_code == 400


def test_redis_outage_does_not_break_startup_with_a_configured_token(db, monkeypatch, token):
    class Down(FakeRedis):
        def get(self, key):
            raise first_run.redis.ConnectionError("down")

        set = delete = get

    monkeypatch.setattr(first_run, "redis_client", Down())
    assert first_run.ensure_setup_token() == "tok-123"
    monkeypatch.setattr(settings, "setup_token", None)
    assert first_run.ensure_setup_token() is None
