"""Tests run against a throwaway Postgres database (default: ../infra's Postgres on localhost).
If Postgres is unreachable they fail with a hint rather than skip."""

from __future__ import annotations

import asyncio
import io
import os
import uuid
from pathlib import Path

import asyncpg
import httpx
import pytest
from PIL import Image
from sqlalchemy import text

from creative.config import Settings

ADMIN = ("admin@example.com", "Admin", "admin-password-1")
CREATOR = ("creator@example.com", "Cam Creator", "creator-password-1")
TESTER = ("tester@example.com", "Tess Tester", "tester-password-1")
SETUP_TOKEN = "test-setup-token"
BASE = "http://testserver"


def _admin_dsn() -> str:
    # ../infra's Postgres; role `studio` may create databases in development (APP_DB_CREATEDB=true)
    return os.environ.get("TEST_DATABASE_URL", "postgresql://studio:studio@localhost:5432/postgres")


@pytest.fixture(scope="session")
async def database_url():
    name = f"creative_test_{uuid.uuid4().hex[:8]}"
    try:
        conn = await asyncpg.connect(_admin_dsn())
    except Exception as e:  # pragma: no cover
        pytest.fail(f"Postgres is not reachable ({e}). Start it with `docker compose up -d db`.")
    await conn.execute(f'CREATE DATABASE "{name}"')
    await conn.close()
    url = _admin_dsn().rsplit("/", 1)[0] + "/" + name
    from alembic import command

    from creative.db.engine import alembic_config

    await asyncio.to_thread(
        command.upgrade, alembic_config(url.replace("postgresql://", "postgresql+asyncpg://")), "head"
    )
    yield url
    conn = await asyncpg.connect(_admin_dsn())
    await conn.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
    await conn.close()


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("data")


@pytest.fixture(scope="session")
def settings(database_url, data_dir) -> Settings:
    return Settings(
        _env_file=None,
        database_url=database_url,
        data_dir=data_dir,
        enable_fake_provider=True,
        worker_enabled=False,
        setup_token=SETUP_TOKEN,
        retry_backoff_base_s=0,
        stale_job_after_s=120,
        login_max_failures=10,
        allow_private_webhooks=True,
    )


@pytest.fixture(scope="session")
async def app(settings):
    from creative.main import create_app

    app = create_app(settings)
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture(scope="session")
def state(app):
    return app.state.creative


@pytest.fixture(autouse=True)
async def clean(state):
    yield
    async with state.engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE jobs, assets, job_inputs, workers, users, sessions, api_tokens, login_attempts, "
                "templates, template_versions, template_events, uploads, apps, app_members, app_keys, "
                "app_users, app_user_sessions, otp_challenges, plans, subscriptions, credit_ledger "
                "CASCADE"
            )
        )
    state.auth.setup_token = SETUP_TOKEN


def client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE)


@pytest.fixture
def anon(app):
    return client(app)


async def make_user(state, role: str, email: str, name: str, password: str):
    from creative.auth.passwords import hash_password
    from creative.db.tables import User

    user = User(id=uuid.uuid4(), email=email, name=name, role=role, password_hash=hash_password(password))
    async with state.db.begin() as s:
        s.add(user)
    return user


async def signed_in(app, state, role: str, creds) -> httpx.AsyncClient:
    email, name, password = creds
    user = await make_user(state, role, email, name, password)
    c = client(app)
    r = await c.post("/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    c.user = user
    return c


async def make_app(state, slug="workspace", name="Workspace", **fields):
    from creative.db.tables import App

    owner = await make_user(
        state, "admin", f"owner-{uuid.uuid4().hex[:6]}@example.com", "Owner", "owner-password-1"
    )
    a = App(id=uuid.uuid4(), slug=slug, name=name, created_by=owner.id, **fields)
    async with state.db.begin() as s:
        s.add(a)
    return a


async def join(state, app_id, user, role: str) -> None:
    from creative.db.tables import AppMember

    async with state.db.begin() as s:
        s.add(AppMember(app_id=app_id, user_id=user.id, role=role))


@pytest.fixture
async def ws(state):
    """The app most tests work in; `client.ws` is its base path /v1/apps/<id>."""
    return await make_app(state)


@pytest.fixture
async def admin(app, state, ws):
    c = await signed_in(app, state, "admin", ADMIN)
    c.ws = f"/v1/apps/{ws.id}"
    return c


async def member(app, state, app_row, role: str, creds) -> httpx.AsyncClient:
    c = await signed_in(app, state, "user", creds)
    await join(state, app_row.id, c.user, role)
    c.ws = f"/v1/apps/{app_row.id}"
    c.app_id = app_row.id
    return c


@pytest.fixture
async def creator(app, state, ws):
    """An editor of `ws`."""
    return await member(app, state, ws, "editor", CREATOR)


@pytest.fixture
async def tester(app, state, ws):
    """A tester of `ws`."""
    return await member(app, state, ws, "tester", TESTER)


def image_bytes(
    size=(300, 400), fmt="JPEG", color=(200, 60, 40), exif_orientation: int | None = None
) -> bytes:
    img = Image.new("RGB", size, color)
    out = io.BytesIO()
    kwargs = {}
    if exif_orientation:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        exif[0x8825] = {2: (1.0, 2.0, 3.0)}  # a GPS block, to check it's stripped
        kwargs["exif"] = exif
    img.save(out, fmt, **kwargs)
    return out.getvalue()


GHIBLI = {
    "slug": "ghibli-fake",
    "title": "Ghibli (fake)",
    "provider": "fake",
    "model": "fake-image-1",
    "allowed_models": ["fake-image-2"],
    "prompt": "Redraw as a painted film still. Mood: {{mood}}.",
    "inputs": [{"name": "photo", "label": "Your photo", "required": True}],
    "variables": [{"name": "mood", "label": "Mood", "default": "sunny", "max_length": 40}],
}


async def create_template(editor_client, body=None, activate=True) -> dict:
    base = editor_client.ws + "/manage/templates"
    r = await editor_client.post(base, json=body or GHIBLI)
    assert r.status_code == 201, r.text
    t = r.json()["template"]
    if activate:
        r = await editor_client.post(f"{base}/{t['id']}/status", json={"status": "active"})
        assert r.status_code == 200, r.text
        t = r.json()
    return t


async def run_worker_once(state) -> bool:
    from creative.main import make_worker

    return await make_worker(state).run_once()


# ---- end users of an app (sign-in, credits) ----------------------------------------------------------

GOOGLE_CLIENT_ID = "1234-test.apps.googleusercontent.com"
_google_key = None


async def app_client(app, state, slug="reelify", device="device-1", **fields) -> httpx.AsyncClient:
    """A client of a new app, calling /v1/app/* with its key. `c.app_row` is the app.
    Defaults: phone and Google sign-in on."""
    from types import SimpleNamespace

    fields = {
        "auth_phone_enabled": True,
        "auth_google_enabled": True,
        "google_client_ids": [GOOGLE_CLIENT_ID],
        **fields,
    }
    a = await make_app(state, slug=slug, name=slug.title(), **fields)
    _, raw = await state.apps.create_key(SimpleNamespace(id=a.created_by), a.id, "android")
    c = client(app)
    c.headers.update({"X-App-Key": raw, "X-Device-Id": device})
    c.app_row = a
    c.key = raw
    return c


def with_device(c: httpx.AsyncClient, app, device: str) -> httpx.AsyncClient:
    """Another install of the same app (same key, new device, no session)."""
    other = client(app)
    other.headers.update({"X-App-Key": c.key, "X-Device-Id": device})
    other.app_row = c.app_row
    other.key = c.key
    return other


async def sign_in_phone(c: httpx.AsyncClient, state, phone="9876543210") -> dict:
    """Phone sign-in with the code captured by the log SMS sender; sets the bearer on `c`."""
    r = await c.post("/v1/app/auth/otp/send", json={"phone": phone})
    assert r.status_code == 200, r.text
    sent = r.json()
    code = state.endusers.sms.sent[sent["phone"]]
    r = await c.post("/v1/app/auth/otp/verify", json={"challenge_id": sent["challenge_id"], "code": code})
    assert r.status_code == 200, r.text
    body = r.json()
    c.headers["Authorization"] = f"Bearer {body['token']}"
    c.user_id = body["user"]["id"]
    return body


def google_token(state, sub="g-123", aud=GOOGLE_CLIENT_ID, **claims) -> str:
    """A Google-style ID token signed with a test key that the app's verifier trusts."""
    import time

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from google.auth import crypt
    from google.auth import jwt as gjwt

    global _google_key
    if _google_key is None:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
        import datetime as dt

        now = dt.datetime.now(dt.UTC)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(1)
            .not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=30))
            .sign(key, hashes.SHA256())
        )
        _google_key = (
            key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            ).decode(),
            cert.public_bytes(serialization.Encoding.PEM).decode(),
        )
    private_pem, cert_pem = _google_key
    verifier = state.endusers.google
    verifier.certs = {"test-kid": cert_pem}
    verifier.certs_expire_at = float("inf")
    now = int(time.time())
    payload = {
        "iss": "https://accounts.google.com",
        "aud": aud,
        "sub": sub,
        "email": f"{sub}@gmail.com",
        "email_verified": True,
        "name": "Gia Google",
        "picture": "https://example.com/p.png",
        "iat": now,
        "exp": now + 3600,
        **claims,
    }
    signer = crypt.RSASigner.from_string(private_pem, key_id="test-kid")
    return gjwt.encode(signer, payload).decode()
