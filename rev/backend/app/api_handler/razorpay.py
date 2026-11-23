import hashlib
import hmac
import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("autorev")

RAZORPAY_BASE = "https://api.razorpay.com/v1"


class RazorpayException(Exception):
    def __init__(self, message, code=None, status_code=None, response_body=None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.response_body = response_body


class RazorpayAPIHandler:
    def __init__(self, key_id: str, key_secret: str):
        self.key_id = key_id
        self.key_secret = key_secret

    def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        url = f"{RAZORPAY_BASE}{path}"
        logger.info(f"Razorpay {method} {url}")

        with httpx.Client(timeout=30, auth=(self.key_id, self.key_secret)) as client:
            response = client.request(method, url, **kwargs)

        try:
            data = response.json()
        except Exception:
            data = {}

        if not response.is_success:
            error = data.get("error", {})
            msg = error.get("description", "Unknown Razorpay error")
            code = error.get("code")
            raise RazorpayException(msg, code=code, status_code=response.status_code, response_body=data)

        return data

    # ── Customers ──────────────────────────────────────────────────────────────

    def create_customer(
        self, name: str, contact: str, email: Optional[str] = None, notes: Optional[dict] = None
    ) -> dict:
        payload = {"name": name, "contact": contact, "fail_existing": "0"}
        if email:
            payload["email"] = email
        if notes:
            payload["notes"] = notes
        return self._request("POST", "/customers", json=payload)

    def fetch_token(self, customer_id: str, token_id: str) -> dict:
        return self._request("GET", f"/customers/{customer_id}/tokens/{token_id}")

    def list_tokens(self, customer_id: str) -> dict:
        return self._request("GET", f"/customers/{customer_id}/tokens")

    def cancel_token(self, customer_id: str, token_id: str) -> dict:
        return self._request("POST", f"/customers/{customer_id}/tokens/{token_id}/cancel")

    # ── Orders / authorization ────────────────────────────────────────────────

    def create_authorization_order(
        self,
        customer_id: str,
        amount: int,
        method: str,
        token_params: dict,
        currency: str = "INR",
        notes: Optional[dict] = None,
    ) -> dict:
        """Registration order carrying a `token` block — the customer authorizes this
        once (UPI intent/collect, e-mandate, or card) and Razorpay returns a token_id
        usable for all future charges."""
        payload = {
            "amount": amount,
            "currency": currency,
            "customer_id": customer_id,
            "method": method,
            "token": token_params,
        }
        if notes:
            payload["notes"] = notes
        return self._request("POST", "/orders", json=payload)

    def create_recurring_charge_order(
        self, customer_id: str, amount: int, currency: str = "INR", notes: Optional[dict] = None
    ) -> dict:
        """Plain order for a single subsequent charge against an already-registered token.

        payment_capture is mandatory on subsequent-payment orders; true captures the
        payment automatically, so payment.captured follows without a capture call.
        """
        payload = {"amount": amount, "currency": currency, "customer_id": customer_id, "payment_capture": True}
        if notes:
            payload["notes"] = notes
        return self._request("POST", "/orders", json=payload)

    def fetch_order(self, order_id: str) -> dict:
        return self._request("GET", f"/orders/{order_id}")

    def fetch_order_payments(self, order_id: str) -> dict:
        """Payments made against an order. A recurring authorisation payment carries the
        token_id it created, which is the only reliable link from an order to its token."""
        return self._request("GET", f"/orders/{order_id}/payments")

    def fetch_payment(self, payment_id: str) -> dict:
        return self._request("GET", f"/payments/{payment_id}")

    # ── Charging a saved token ─────────────────────────────────────────────────

    def charge_token(
        self,
        customer_id: str,
        order_id: str,
        token_id: str,
        amount: int,
        email: str,
        contact: str,
        currency: str = "INR",
        notes: Optional[dict] = None,
    ) -> dict:
        """POST /payments/create/recurring. email and contact are mandatory there."""
        payload = {
            "email": email,
            "contact": contact,
            "customer_id": customer_id,
            "order_id": order_id,
            "token": token_id,
            "amount": amount,
            "currency": currency,
            "recurring": "1",
        }
        if notes:
            payload["notes"] = notes
        return self._request("POST", "/payments/create/recurring", json=payload)

    # ── Webhooks ───────────────────────────────────────────────────────────────

    @staticmethod
    def verify_webhook_signature(body: bytes, signature: str, secret: str) -> bool:
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature or "")


def get_handler(detail) -> RazorpayAPIHandler:
    """Create a RazorpayAPIHandler from a RazorpayApp DB row."""
    if not detail or not detail.razorpay_key_id or not detail.razorpay_key_secret:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Razorpay credentials not configured for this app")
    return RazorpayAPIHandler(key_id=detail.razorpay_key_id, key_secret=detail.razorpay_key_secret)
