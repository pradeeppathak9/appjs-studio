import httpx

from studio.providers.base import (
    ProviderContentPolicyError,
    ProviderError,
    ProviderInvalidRequestError,
    ProviderUnavailableError,
)

POLICY_WORDS = ("safety", "policy", "moderation", "blocked", "prohibited", "nsfw")


def status_of(exc: BaseException) -> int | None:
    for attr in ("status_code", "code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)


def translate(exc: BaseException, provider: str) -> ProviderError:
    """Map an SDK/HTTP exception onto the service's error classes."""
    if isinstance(exc, ProviderError):
        return exc
    message = f"{provider}: {exc}"[:1000]
    if isinstance(exc, httpx.TransportError | ConnectionError | TimeoutError):
        return ProviderUnavailableError(message)
    status = status_of(exc)
    text = str(exc).lower()
    if status == 429 or (status is not None and status >= 500):
        return ProviderUnavailableError(message)
    if any(w in text for w in POLICY_WORDS):
        return ProviderContentPolicyError(message)
    if status in (401, 403):
        return ProviderError(message, code="provider_auth")
    if status is not None and 400 <= status < 500:
        return ProviderInvalidRequestError(message)
    return ProviderError(message)
