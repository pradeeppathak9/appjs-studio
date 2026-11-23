import time
import logging
from functools import wraps
from typing import Any, Dict, Optional

import threading

import httpx

from app.redis import redis_client

logger = logging.getLogger("autorev")

PHONEPE_URLS = {
    "UAT": {
        "base": "https://api-preprod.phonepe.com/apis/pg-sandbox",
        "identity": "https://api-preprod.phonepe.com/apis/pg-sandbox/v1/oauth/token",
    },
    "PROD": {
        "base": "https://api.phonepe.com/apis/pg",
        "identity": "https://api.phonepe.com/apis/identity-manager/v1/oauth/token",
    },
}

TOKEN_KEY_PREFIX = "phonepe_token_"

# A single pooled client per process, instead of one per request.
#
# Every call used to open `with httpx.Client(...)`, which meant a fresh TCP
# connection and TLS handshake each time: measured against api.phonepe.com that
# was 119ms per request versus 59ms on a kept-alive connection — half of every
# call was handshake. httpx.Client is thread-safe, so the worker's parallel
# status sweep shares this pool too.
_CLIENT: Optional[httpx.Client] = None
_CLIENT_LOCK = threading.Lock()


def _http_client() -> httpx.Client:
    global _CLIENT
    if _CLIENT is None:
        with _CLIENT_LOCK:
            if _CLIENT is None:
                _CLIENT = httpx.Client(
                    timeout=30,
                    limits=httpx.Limits(
                        max_connections=64,
                        max_keepalive_connections=32,
                        keepalive_expiry=60.0,
                    ),
                )
    return _CLIENT


def _fetch_token(client_id: str, client_secret: str, identity_url: str) -> dict:
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "client_version": "1",
        "grant_type": "client_credentials",
    }
    response = httpx.post(identity_url, data=data, timeout=10)
    response.raise_for_status()
    return response.json()


def with_token_refresh(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        cache_key = f"{TOKEN_KEY_PREFIX}{self.app_id}"

        if not self.access_token:
            cached = redis_client.get(cache_key)
            if cached:
                import json
                token_data = json.loads(cached)
                self.access_token = token_data.get("access_token")
                self.expires_at = token_data.get("expires_at")

        if not self.access_token or (self.expires_at and time.time() >= self.expires_at):
            logger.info(f"Refreshing PhonePe token for app {self.app_id}")
            token_data = _fetch_token(self.client_id, self.client_secret, self.identity_url)
            self.access_token = token_data["access_token"]
            self.expires_at = token_data.get("expires_at")
            import json
            redis_client.setex(cache_key, 3500, json.dumps(token_data))

        return func(self, *args, **kwargs)

    return wrapper


class PhonePeException(Exception):
    def __init__(self, message, code=None, status_code=None, response_body=None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.response_body = response_body


class DuplicateRequestError(PhonePeException):
    pass


class InvalidSubscriptionStateError(PhonePeException):
    """Raised when PhonePe rejects a call because its view of the subscription
    (paused/revoked/cancelled) no longer matches our local ACTIVE state."""
    pass


INVALID_SUBSCRIPTION_STATE_CODES = {"INVALID_SUBSCRIPTION_STATE"}


class PhonePeAPIHandler:
    def __init__(self, app_id: str, client_id: str, client_secret: str, environment: str = "UAT", custom: bool = True):
        self.app_id = app_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.environment = environment
        self.custom = custom
        self.base_url = PHONEPE_URLS[environment]["base"]
        self.identity_url = PHONEPE_URLS[environment]["identity"]
        self.access_token: Optional[str] = None
        self.expires_at: Optional[float] = None

    @property
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"O-Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _do_request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        kwargs["headers"] = self._headers
        response = _http_client().request(method, url, **kwargs)
        try:
            data = response.json()
        except Exception:
            data = {}
        if not response.is_success:
            code = data.get("code")
            msg = data.get("message", "Unknown Error")
            if code == "DUPLICATE_REQUEST_ID":
                raise DuplicateRequestError(msg, code=code, status_code=response.status_code, response_body=data)
            if code in INVALID_SUBSCRIPTION_STATE_CODES or (msg and "invalid subscription state" in msg.lower()):
                raise InvalidSubscriptionStateError(msg, code=code, status_code=response.status_code, response_body=data)
            raise PhonePeException(msg, code=code, status_code=response.status_code, response_body=data)
        return data

    @with_token_refresh
    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        import json as _json
        url = f"{self.base_url}{endpoint}"
        logger.info(f"PhonePe {method} {url}")
        try:
            return self._do_request(method, url, **kwargs)
        except PhonePeException as e:
            if e.status_code != 401:
                raise
            # Stale cached token — force refresh and retry once
            logger.warning(f"PhonePe 401 for app {self.app_id}, refreshing token and retrying")
            cache_key = f"{TOKEN_KEY_PREFIX}{self.app_id}"
            redis_client.delete(cache_key)
            token_data = _fetch_token(self.client_id, self.client_secret, self.identity_url)
            self.access_token = token_data["access_token"]
            self.expires_at = token_data.get("expires_at")
            redis_client.setex(cache_key, 3500, _json.dumps(token_data))
            return self._do_request(method, url, **kwargs)

    def force_refresh_token(self) -> dict:
        import json
        token_data = _fetch_token(self.client_id, self.client_secret, self.identity_url)
        self.access_token = token_data["access_token"]
        self.expires_at = token_data.get("expires_at")
        redis_client.setex(f"{TOKEN_KEY_PREFIX}{self.app_id}", 3500, json.dumps(token_data))
        return token_data

    # ── Subscription APIs ──────────────────────────────────────────────────────

    def subscription_setup(self, payload: dict) -> dict:
        if self.custom:
            return self._request("POST", "/subscriptions/v2/setup", json=payload)
        return self._request("POST", "/checkout/v2/pay", json=payload)

    def subscription_status(self, merchant_subscription_id: str) -> dict:
        if self.custom:
            return self._request("GET", f"/subscriptions/v2/{merchant_subscription_id}/status", params={"details": "true"})
        return self._request("GET", f"/checkout/v2/subscriptions/{merchant_subscription_id}/status")

    def subscription_order_status(self, merchant_order_id: str) -> dict:
        if self.custom:
            return self._request("GET", f"/subscriptions/v2/order/{merchant_order_id}/status", params={"details": "true"})
        return self._request("GET", f"/checkout/v2/order/{merchant_order_id}/status")

    def cancel_subscription(self, merchant_subscription_id: str) -> dict:
        if self.custom:
            return self._request("POST", f"/subscriptions/v2/{merchant_subscription_id}/cancel")
        return self._request("POST", f"/checkout/v2/subscriptions/{merchant_subscription_id}/cancel")

    def notify_redemption(self, payload: dict) -> dict:
        if self.custom:
            return self._request("POST", "/subscriptions/v2/notify", json=payload)
        return self._request("POST", "/checkout/v2/subscriptions/notify", json=payload)

    def redemption_execute(self, merchant_order_id: str) -> dict:
        payload = {"merchantOrderId": merchant_order_id}
        if self.custom:
            return self._request("POST", "/subscriptions/v2/redeem", json=payload)
        return self._request("POST", "/checkout/v2/subscriptions/redeem", json=payload)

    def redemption_order_status(self, merchant_order_id: str) -> dict:
        if self.custom:
            return self._request("GET", f"/subscriptions/v2/order/{merchant_order_id}/status", params={"details": "true"})
        return self._request("GET", f"/checkout/v2/subscriptions/order/{merchant_order_id}/status")


def get_handler(detail, custom: bool = True) -> PhonePeAPIHandler:
    """Create a PhonePeAPIHandler from a PhonePeApp DB row."""
    if not detail or not detail.phonepe_client_id or not detail.phonepe_client_secret:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="PhonePe credentials not configured for this app")
    return PhonePeAPIHandler(
        app_id=detail.app_id,
        client_id=detail.phonepe_client_id,
        client_secret=detail.phonepe_client_secret,
        environment=detail.phonepe_environment or "UAT",
        custom=custom,
    )
