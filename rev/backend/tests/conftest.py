"""Tests run the real routes against a throwaway Postgres database (the models use
JSONB, so SQLite will not do) and replace Razorpay's HTTP API with a recorder.

    AUTOREV_TEST_DATABASE_URL=postgresql://rev:rev@localhost:5432/rev_test pytest
"""
import hashlib
import hmac
import json
import os

import pytest

os.environ["AUTOREV_DATABASE_URL"] = os.environ.get(
    "AUTOREV_TEST_DATABASE_URL", "postgresql://rev:rev@localhost:5432/rev_test"
)

from fastapi.testclient import TestClient  # noqa: E402

from app.api_handler.razorpay import RazorpayAPIHandler  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models import App, RazorpayApp  # noqa: E402

APP_ID = "app_rzp_test"
API_KEY = "k" * 32
WEBHOOK_SECRET = "whsec_test"


class FakeRazorpay:
    """Answers Razorpay API calls from `routes` ({"METHOD /path": response}) and records them."""

    def __init__(self):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.routes: dict[str, dict] = {}

    def __call__(self, handler, method, path, **kwargs):
        self.calls.append((method, path, kwargs.get("json")))
        key = f"{method} {path}"
        if key not in self.routes:
            raise AssertionError(f"unexpected Razorpay call: {key}")
        response = self.routes[key]
        if isinstance(response, Exception):
            raise response
        return response

    def sent(self, method, path):
        return [body for m, p, body in self.calls if m == method and p == path]


@pytest.fixture
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    s = SessionLocal()
    s.add(App(id=APP_ID, name="marktmakrs", api_key=API_KEY, razorpay_enabled=True, enabled=True))
    s.add(RazorpayApp(app_id=APP_ID, razorpay_key_id="rzp_test_x", razorpay_key_secret="secret",
                      razorpay_webhook_secret=WEBHOOK_SECRET, razorpay_environment="TEST"))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def rzp(monkeypatch):
    fake = FakeRazorpay()
    monkeypatch.setattr(RazorpayAPIHandler, "_request", lambda self, method, path, **kw: fake(self, method, path, **kw))
    return fake


@pytest.fixture
def client(db):
    return TestClient(fastapi_app)


AUTH = {"Authorization": f"Bearer {API_KEY}"}
BASE = f"/api/v1/{APP_ID}/razorpay"


def send_webhook(client, event: dict, secret: str = WEBHOOK_SECRET):
    body = json.dumps(event).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(f"{BASE}/webhook", content=body,
                       headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"})
