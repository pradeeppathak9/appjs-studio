import secrets
import string

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()  # argon2id with the library's current defaults
_DUMMY_HASH = _hasher.hash("not-a-real-password-" + secrets.token_hex(8))


class PasswordRuleError(ValueError):
    pass


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Constant-ish work whether or not the user exists: unknown users verify against a dummy hash."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def check_rules(password: str, *, email: str, min_length: int) -> None:
    if len(password) < min_length:
        raise PasswordRuleError(f"password must be at least {min_length} characters")
    if len(password) > 256:
        raise PasswordRuleError("password must be at most 256 characters")
    if password.strip().lower() == email.strip().lower():
        raise PasswordRuleError("password must not be the email address")


def temporary_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(length // 4))
