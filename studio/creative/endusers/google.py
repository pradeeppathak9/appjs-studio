"""Verifying Google ID tokens (from Android Credential Manager / Sign in with Google).

The token is a JWT signed by Google. We check the signature against Google's published certs
(cached for as long as Google's Cache-Control allows), the issuer, expiry, that the audience is one
of the app's OAuth *Web* client ids, and that the email is verified."""

from __future__ import annotations

import asyncio
import base64
import json
import re
import time

import httpx
from google.auth import exceptions as google_exceptions
from google.auth import jwt as google_jwt

from creative.errors import ServiceError, UnavailableError

ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
MAX_AGE_RE = re.compile(r"max-age=(\d+)")


class InvalidGoogleToken(ServiceError):
    status, code = 401, "invalid_token"


class GoogleVerifier:
    def __init__(self, http: httpx.AsyncClient, certs_url: str):
        self.http = http
        self.certs_url = certs_url
        self.certs: dict[str, str] | None = None
        self.certs_expire_at = 0.0
        self._lock = asyncio.Lock()

    async def _fetch_certs(self, force: bool = False) -> dict[str, str]:
        async with self._lock:
            if self.certs is not None and not force and time.monotonic() < self.certs_expire_at:
                return self.certs
            try:
                r = await self.http.get(self.certs_url, timeout=10)
                r.raise_for_status()
                certs = r.json()
            except (httpx.HTTPError, ValueError) as e:
                if self.certs is not None:
                    return self.certs  # stale certs beat failing every sign-in
                raise UnavailableError("couldn't reach Google to check the sign-in; try again") from e
            m = MAX_AGE_RE.search(r.headers.get("cache-control", ""))
            self.certs = certs
            self.certs_expire_at = time.monotonic() + (int(m.group(1)) if m else 3600)
            return certs

    async def verify(self, token: str, audiences: list[str]) -> dict:
        """The token's claims, or InvalidGoogleToken."""
        if not audiences:
            raise InvalidGoogleToken("Google sign-in isn't set up for this app")
        certs = await self._fetch_certs()
        kid = _header_kid(token)
        if kid and kid not in certs:
            certs = await self._fetch_certs(force=True)  # Google rotated its keys
        try:
            claims = google_jwt.decode(token, certs=certs, audience=audiences, clock_skew_in_seconds=30)
        except (ValueError, google_exceptions.GoogleAuthError) as e:
            raise InvalidGoogleToken(f"the Google sign-in token is not valid ({_short(e)})") from e
        if claims.get("iss") not in ISSUERS:
            raise InvalidGoogleToken("the Google sign-in token has the wrong issuer")
        if not claims.get("sub"):
            raise InvalidGoogleToken("the Google sign-in token has no subject")
        if claims.get("email") and claims.get("email_verified") is False:
            raise InvalidGoogleToken("this Google account's email isn't verified")
        return claims


def _header_kid(token: str) -> str | None:
    try:
        head = token.split(".", 1)[0]
        head += "=" * (-len(head) % 4)
        return json.loads(base64.urlsafe_b64decode(head)).get("kid")
    except (ValueError, IndexError):
        return None


def _short(e: Exception) -> str:
    return str(e).split("\n", 1)[0][:120]
