class ServiceError(Exception):
    """An error with an HTTP status and a stable code; rendered as {"error": {...}} by the API."""

    status = 400
    code = "bad_request"

    def __init__(self, message: str, field: str | None = None, details: list[dict] | None = None):
        super().__init__(message)
        self.message = message
        self.field = field
        self.details = details


class NotFoundError(ServiceError):
    status, code = 404, "not_found"


class ValidationFailed(ServiceError):
    status, code = 422, "validation_error"


class ConflictError(ServiceError):
    status, code = 409, "conflict"


class ForbiddenError(ServiceError):
    status, code = 403, "forbidden"


class UnavailableError(ServiceError):
    status, code = 503, "provider_unavailable"


class PayloadTooLarge(ServiceError):
    status, code = 413, "payload_too_large"


class InsufficientCredits(ServiceError):
    status, code = 402, "insufficient_credits"


class SignInRequired(ServiceError):
    """An app-key call without a user session tried something only a signed-in user may do (e.g. run a
    template that costs credits). Same code as a missing session, so clients show sign-in."""

    status, code = 401, "unauthenticated"


class RateLimitedError(ServiceError):
    status, code = 429, "rate_limited"
