import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from studio.errors import ServiceError

log = logging.getLogger(__name__)


def error_response(status: int, code: str, message: str, field=None, details=None) -> JSONResponse:
    body = {"code": code, "message": message}
    if field:
        body["field"] = field
    if details:
        body["details"] = details
    return JSONResponse({"error": body}, status_code=status)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ServiceError)
    async def _service(_: Request, e: ServiceError):
        return error_response(e.status, e.code, e.message, e.field, e.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, e: RequestValidationError):
        details = [
            {
                "field": ".".join(str(x) for x in err["loc"] if x not in ("body", "query", "path")),
                "message": err["msg"],
            }
            for err in e.errors()
        ]
        return error_response(422, "validation_error", "the request is invalid", details=details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, e: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(e.status_code, "http_error")
        return error_response(e.status_code, code, str(e.detail))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, e: Exception):
        log.exception("unhandled error")
        return error_response(500, "internal_error", "something went wrong")
