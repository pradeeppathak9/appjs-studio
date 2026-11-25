"""First-run setup: create the first admin with a setup token (same flow as AppJs Studio).

While no admin exists, POST /api/auth/setup accepts AUTOREV_SETUP_TOKEN, or, when that is unset, a
token generated at startup and printed in the backend log. The generated token lives in Redis so
every uvicorn worker accepts the same one; it is deleted once the admin exists.
"""
import hmac
import logging
import secrets

import redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import settings
from app.database import SessionLocal
from app.models import User
from app.redis import redis_client

log = logging.getLogger("autorev.setup")

REDIS_KEY = "setup:token"
# pg_advisory_xact_lock id that serialises concurrent setup requests.
SETUP_LOCK_ID = 0x6175746F72657601  # "autorev" + 1


class SetupForbidden(Exception):
    """The setup token is missing or wrong."""


class AlreadySetUp(Exception):
    """An admin exists, so setup is closed."""


def setup_needed(db: Session) -> bool:
    return db.query(User.id).filter(User.is_admin.is_(True)).first() is None


def _configured_token() -> str | None:
    token = settings.setup_token.get_secret_value() if settings.setup_token else ""
    return token or None


def current_token() -> str | None:
    return _configured_token() or redis_client.get(REDIS_KEY)


def _forget_generated_token() -> None:
    try:
        redis_client.delete(REDIS_KEY)
    except redis.RedisError:
        log.warning("could not clear the generated setup token from Redis", exc_info=True)


def ensure_setup_token() -> str | None:
    """The token to show in the log while setup is needed, generating a shared one if none is set.

    Never raises on a Redis outage: startup must not depend on it (a configured token still works).
    """
    db = SessionLocal()
    try:
        if not setup_needed(db):
            _forget_generated_token()
            return None
    finally:
        db.close()
    if token := _configured_token():
        return token
    try:
        redis_client.set(REDIS_KEY, secrets.token_urlsafe(18), nx=True)
        return redis_client.get(REDIS_KEY)
    except redis.RedisError:
        log.error("First-run setup needs AUTOREV_SETUP_TOKEN: Redis is unreachable, so no token was generated")
        return None


def create_first_admin(db: Session, token: str, email: str, full_name: str, password: str) -> User:
    expected = current_token()
    if not expected or not hmac.compare_digest(token.encode(), expected.encode()):
        raise SetupForbidden("The setup token is wrong")
    db.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": SETUP_LOCK_ID})
    if not setup_needed(db):
        db.rollback()
        raise AlreadySetUp("Setup is already done")
    email = email.strip().lower()
    if db.query(User.id).filter(User.email == email).first():
        db.rollback()
        raise ValueError("A user with this email already exists")
    user = User(email=email, hashed_password=hash_password(password), full_name=full_name.strip(), is_admin=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    _forget_generated_token()
    log.info("First-run setup done: created admin %s", user.email)
    return user
