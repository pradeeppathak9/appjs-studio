"""Sending one-time codes by SMS. `SMS_PROVIDER=log` (the default) only logs them: for development
and tests. `msg91` sends through MSG91's Flow API with a DLT-approved template (required in India)."""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

from creative.config import Settings
from creative.errors import UnavailableError
from creative.secrets import SecretBox

log = logging.getLogger(__name__)


class SmsSender(Protocol):
    async def send_otp(self, phone: str, code: str) -> None: ...


class SmsUnavailable(UnavailableError):
    code = "sms_unavailable"


class LogSmsSender:
    """Writes the code to the log instead of sending it. Keeps the last code per phone (tests)."""

    def __init__(self) -> None:
        self.sent: dict[str, str] = {}

    async def send_otp(self, phone: str, code: str) -> None:
        self.sent[phone] = code
        log.warning("SMS_PROVIDER=log: sign-in code for %s is %s", phone, code)


class Msg91Sender:
    URL = "https://control.msg91.com/api/v5/flow"

    def __init__(self, http: httpx.AsyncClient, auth_key: str, template_id: str, otp_var: str = "otp"):
        self.http = http
        self.auth_key = auth_key
        self.template_id = template_id
        self.otp_var = otp_var

    async def send_otp(self, phone: str, code: str) -> None:
        body = {
            "template_id": self.template_id,
            "short_url": "0",
            "recipients": [{"mobiles": phone.lstrip("+"), self.otp_var: code}],
        }
        try:
            r = await self.http.post(
                self.URL, json=body, headers={"authkey": self.auth_key, "accept": "application/json"}
            )
        except httpx.HTTPError as e:
            log.warning("msg91: %s", e)
            raise SmsUnavailable("couldn't send the code; try again in a minute") from e
        if r.status_code >= 300 or (
            r.headers.get("content-type", "").startswith("application/json")
            and r.json().get("type") == "error"
        ):
            log.warning("msg91 refused the message: %s %s", r.status_code, r.text[:300])
            raise SmsUnavailable("couldn't send the code; try again in a minute")


def app_sms_sender(app, box: SecretBox, http: httpx.AsyncClient, default: SmsSender) -> SmsSender:
    """The app's own MSG91 account when its console settings have a template and an auth key;
    otherwise the server's sender (SMS_PROVIDER)."""
    if app.msg91_template_id and app.msg91_auth_key_enc:
        return Msg91Sender(
            http, box.decrypt(app.msg91_auth_key_enc), app.msg91_template_id, app.msg91_otp_var or "otp"
        )
    return default


def sms_sender(settings: Settings, http: httpx.AsyncClient) -> SmsSender:
    if settings.sms_provider == "msg91":
        if not (settings.msg91_auth_key and settings.msg91_template_id):
            raise RuntimeError("SMS_PROVIDER=msg91 needs MSG91_AUTH_KEY and MSG91_TEMPLATE_ID")
        return Msg91Sender(
            http,
            settings.msg91_auth_key.get_secret_value(),
            settings.msg91_template_id,
            settings.msg91_otp_var,
        )
    if settings.sms_provider != "log":
        raise RuntimeError(f"unknown SMS_PROVIDER {settings.sms_provider!r} (use log or msg91)")
    return LogSmsSender()
