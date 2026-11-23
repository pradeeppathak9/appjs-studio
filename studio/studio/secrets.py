"""Encrypting credentials that apps' admins enter in the console (e.g. an app's MSG91 auth key).

Values are encrypted with Fernet under a key derived from `SECRETS_KEY`. They are write-only over
the API: the console learns whether one is set, never the value. Losing or changing SECRETS_KEY
makes stored values unreadable, so they have to be entered again."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from studio.errors import ServiceError, UnavailableError


class SecretsKeyMissing(ServiceError):
    status, code = 503, "secrets_key_missing"


class SecretBox:
    def __init__(self, key: SecretStr | str | None):
        raw = key.get_secret_value() if isinstance(key, SecretStr) else key
        # Any long random string works: it is stretched to a Fernet key, so admins don't have to
        # produce Fernet's exact base64 format.
        self._fernet = (
            Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())) if raw else None
        )

    @property
    def available(self) -> bool:
        return self._fernet is not None

    def encrypt(self, value: str) -> str:
        if self._fernet is None:
            raise SecretsKeyMissing("set SECRETS_KEY on the server before saving credentials")
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, token: str) -> str:
        if self._fernet is None:
            raise UnavailableError("SECRETS_KEY is not set: saved credentials can't be read")
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken as e:
            raise UnavailableError(
                "saved credentials can't be read (SECRETS_KEY changed?); enter them again"
            ) from e
