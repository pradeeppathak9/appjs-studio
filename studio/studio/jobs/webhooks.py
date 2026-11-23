from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from studio.config import Settings
from studio.jobs.repository import JobRepository

log = logging.getLogger(__name__)
BACKOFF_S = (1, 4, 16)


class WebhookRejected(Exception):
    pass


async def check_public_host(url: str) -> None:
    """Refuse URLs whose host resolves to a private, loopback or link-local address."""
    host = urlsplit(url).hostname
    if not host:
        raise WebhookRejected("webhook URL has no host")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as e:
        raise WebhookRejected(f"cannot resolve {host}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise WebhookRejected(f"{host} resolves to a non-public address")


class WebhookSender:
    def __init__(
        self,
        settings: Settings,
        http: httpx.AsyncClient,
        repo: JobRepository,
        payload_for: Callable[[UUID], Awaitable[dict | None]],
    ):
        self.settings = settings
        self.http = http
        self.repo = repo
        self.payload_for = payload_for

    def sign(self, body: bytes) -> str | None:
        if not self.settings.webhook_secret:
            return None
        key = self.settings.webhook_secret.get_secret_value().encode()
        return "sha256=" + hmac.new(key, body, hashlib.sha256).hexdigest()

    async def send(self, job_id: UUID, url: str) -> bool:
        payload = await self.payload_for(job_id)
        if payload is None:
            return False
        body = json.dumps(payload, default=str).encode()
        headers = {
            "Content-Type": "application/json",
            "X-Studio-Event": f"generation.{payload['status']}",
            "X-Studio-Job-Id": str(job_id),
        }
        if sig := self.sign(body):
            headers["X-Studio-Signature"] = sig
        attempts = 0
        for attempt in range(self.settings.webhook_max_attempts):
            attempts = attempt + 1
            try:
                if not self.settings.allow_private_webhooks:
                    await check_public_host(url)  # at send time too: DNS can change after submit
                resp = await self.http.post(
                    url,
                    content=body,
                    headers=headers,
                    timeout=self.settings.webhook_timeout_s,
                    follow_redirects=False,
                )
                if resp.status_code < 300:
                    await self.repo.set_webhook(job_id, "delivered", attempts)
                    return True
                if 400 <= resp.status_code < 500 and resp.status_code not in (408, 429):
                    break
            except WebhookRejected as e:
                log.warning("webhook for job %s rejected: %s", job_id, e)
                break
            except httpx.HTTPError as e:
                log.info("webhook for job %s attempt %d failed: %s", job_id, attempts, e)
            if attempt + 1 < self.settings.webhook_max_attempts:
                await asyncio.sleep(BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)])
        await self.repo.set_webhook(job_id, "failed", attempts)
        return False
