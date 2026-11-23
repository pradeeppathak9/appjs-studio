"""Verifying Firebase Auth ID tokens for phone sign-in.

The app verifies the number with Firebase (Firebase sends the SMS and checks the code), then sends us
the signed-in Firebase user's ID token. We check it as Firebase documents for third-party backends:
RS256 signature against the securetoken certs, `aud` = the app's Firebase project id,
`iss` = https://securetoken.google.com/<project id>, expiry, a non-empty `sub`, `auth_time` not in the
future, and that the sign-in was by phone, with a phone number."""

from __future__ import annotations

import time

from google.auth import exceptions as google_exceptions
from google.auth import jwt as google_jwt

from creative.endusers.google import GoogleVerifier, _header_kid, _short
from creative.errors import ServiceError

SKEW_S = 30


class InvalidFirebaseToken(ServiceError):
    status, code = 401, "invalid_token"


class FirebaseVerifier(GoogleVerifier):
    """Same certificate cache as Google sign-in, pointed at Firebase's securetoken certs."""

    async def verify_phone(self, token: str, project_id: str | None) -> dict:
        """The token's claims (with `phone_number`), or InvalidFirebaseToken."""
        if not project_id:
            raise InvalidFirebaseToken("Firebase phone sign-in isn't set up for this app")
        certs = await self._fetch_certs()
        kid = _header_kid(token)
        if kid and kid not in certs:
            certs = await self._fetch_certs(force=True)  # Firebase rotated its keys
        try:
            claims = google_jwt.decode(token, certs=certs, audience=project_id, clock_skew_in_seconds=SKEW_S)
        except (ValueError, google_exceptions.GoogleAuthError) as e:
            raise InvalidFirebaseToken(f"the Firebase sign-in token is not valid ({_short(e)})") from e
        if claims.get("iss") != f"https://securetoken.google.com/{project_id}":
            raise InvalidFirebaseToken("the Firebase sign-in token has the wrong issuer")
        if not claims.get("sub"):
            raise InvalidFirebaseToken("the Firebase sign-in token has no subject")
        auth_time = claims.get("auth_time")
        if not isinstance(auth_time, int | float) or auth_time > time.time() + SKEW_S:
            raise InvalidFirebaseToken("the Firebase sign-in token has a bad auth_time")
        if (claims.get("firebase") or {}).get("sign_in_provider") != "phone" or not claims.get(
            "phone_number"
        ):
            raise InvalidFirebaseToken("the Firebase sign-in wasn't by phone number")
        return claims
