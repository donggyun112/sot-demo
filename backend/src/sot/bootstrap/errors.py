from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from sot.identity.domain import AuthTokenInvalid
from sot.shared.errors import Conflict, Forbidden, InvalidInput, NotFound, SOTError


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"error": {"code": code, "message": message}}
    )


async def handle_sot_error(request: Request, error: Exception) -> JSONResponse:
    if not isinstance(error, SOTError):
        raise error
    status = 400
    if isinstance(error, AuthTokenInvalid):
        status = 401
    elif isinstance(error, Forbidden):
        status = 403
    elif isinstance(error, NotFound):
        status = 404
    elif isinstance(error, Conflict):
        status = 409
    elif isinstance(error, InvalidInput):
        status = 422
    return error_response(status, error.code, error.message)


async def handle_validation_error(request: Request, error: Exception) -> JSONResponse:
    return error_response(422, "invalid_request", "Request validation failed")


async def handle_http_error(request: Request, error: Exception) -> JSONResponse:
    if not isinstance(error, HTTPException):
        raise error
    code, message = {
        401: ("auth_token_invalid", "Authentication failed"),
        403: ("forbidden", "Access denied"),
        404: ("not_found", "Resource not found"),
        405: ("method_not_allowed", "Method not allowed"),
    }.get(error.status_code, ("request_failed", "Request failed"))
    return error_response(error.status_code, code, message)


async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    response = error_response(500, "internal_error", "An internal error occurred")
    if request.scope.get("sot_no_store"):
        response.headers["Cache-Control"] = "private, no-store"
    return response


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(SOTError, handle_sot_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(HTTPException, handle_http_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
