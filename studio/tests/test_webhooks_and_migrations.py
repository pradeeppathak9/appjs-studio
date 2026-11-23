import asyncio
import hashlib
import hmac
import os
import sys
import uuid

import asyncpg
import httpx
import pytest
import respx
from alembic import command
from pydantic import SecretStr

from studio.db.engine import alembic_config
from studio.jobs.webhooks import WebhookRejected, WebhookSender, check_public_host
from tests.conftest import _admin_dsn


class Repo:
    def __init__(self):
        self.status = None

    async def set_webhook(self, job_id, status, attempts):
        self.status = (status, attempts)


async def payload(job_id):
    return {"id": str(job_id), "status": "succeeded"}


@respx.mock
async def test_webhook_is_signed_and_retried(settings, monkeypatch):
    monkeypatch.setattr("studio.jobs.webhooks.BACKOFF_S", (0, 0, 0))
    route = respx.post("https://hooks.example/x").mock(side_effect=[httpx.Response(500), httpx.Response(200)])
    s = settings.model_copy(update={"webhook_secret": SecretStr("s3cret"), "allow_private_webhooks": True})
    repo = Repo()
    async with httpx.AsyncClient() as http:
        ok = await WebhookSender(s, http, repo, payload).send(uuid.uuid4(), "https://hooks.example/x")
    assert ok and repo.status == ("delivered", 2)
    req = route.calls.last.request
    expected = "sha256=" + hmac.new(b"s3cret", req.content, hashlib.sha256).hexdigest()
    assert req.headers["X-Studio-Signature"] == expected
    assert req.headers["X-Studio-Event"] == "generation.succeeded"


@respx.mock
async def test_webhook_gives_up_on_4xx(settings):
    respx.post("https://hooks.example/x").mock(return_value=httpx.Response(404))
    repo = Repo()
    async with httpx.AsyncClient() as http:
        ok = await WebhookSender(settings, http, repo, payload).send(uuid.uuid4(), "https://hooks.example/x")
    assert not ok and repo.status == ("failed", 1)


@pytest.mark.parametrize("url", ["http://127.0.0.1/x", "http://10.0.0.5/x", "http://localhost/x"])
async def test_private_webhook_hosts_are_rejected(url):
    with pytest.raises(WebhookRejected):
        await check_public_host(url)


async def test_migrations_downgrade_and_upgrade_and_match_the_models():
    name = f"studio_mig_{uuid.uuid4().hex[:8]}"
    conn = await asyncpg.connect(_admin_dsn())
    await conn.execute(f'CREATE DATABASE "{name}"')
    await conn.close()
    url = _admin_dsn().rsplit("/", 1)[0].replace("postgresql://", "postgresql+asyncpg://") + "/" + name
    cfg = alembic_config(url)
    try:
        # two upgrades at once, as separate processes (Alembic's context is a process global):
        # the advisory lock makes the second wait, then find nothing to do
        env = {**os.environ, "DATABASE_URL": url}
        procs = [
            await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "studio.cli",
                "db",
                "upgrade",
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            for _ in range(2)
        ]
        outputs = await asyncio.wait_for(asyncio.gather(*(p.communicate() for p in procs)), 60)
        assert [p.returncode for p in procs] == [0, 0], outputs
        await asyncio.to_thread(command.check, cfg)  # models == migrations
        await asyncio.to_thread(command.downgrade, cfg, "base")
        await asyncio.to_thread(command.upgrade, cfg, "head")
    finally:
        conn = await asyncpg.connect(_admin_dsn())
        await conn.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await conn.close()
