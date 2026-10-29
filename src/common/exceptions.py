import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.response import error_response

logger = logging.getLogger(__name__)


def describe_integrity_error(exc: Exception) -> str:
    """Log-safe summary of a DB IntegrityError: constraint/driver error type only.

    ``str(exc)`` embeds the failing statement's bound parameters, i.e. the phone
    number or other PHI being inserted.
    """
    orig = getattr(exc, "orig", None)
    constraint = getattr(orig, "constraint_name", None)
    kind = type(orig).__name__ if orig is not None else type(exc).__name__
    return f"{kind} constraint={constraint or 'unknown'}"


class AppException(Exception):
    def __init__(
        self,
        message: str = "Internal server error",
        code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        errors: Any | None = None,
    ):
        self.message = message
        self.code = code
        self.errors = errors
        super().__init__(message)


class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found", errors: Any | None = None):
        super().__init__(message=message, code=status.HTTP_404_NOT_FOUND, errors=errors)


class UnauthorizedException(AppException):
    def __init__(self, message: str = "Unauthorized", errors: Any | None = None):
        super().__init__(message=message, code=status.HTTP_401_UNAUTHORIZED, errors=errors)


class ForbiddenException(AppException):
    def __init__(self, message: str = "Forbidden", errors: Any | None = None):
        super().__init__(message=message, code=status.HTTP_403_FORBIDDEN, errors=errors)


class ValidationException(AppException):
    def __init__(self, message: str = "Validation error", errors: Any | None = None):
        super().__init__(message=message, code=status.HTTP_422_UNPROCESSABLE_ENTITY, errors=errors)


class ConflictException(AppException):
    def __init__(self, message: str = "Resource conflict", errors: Any | None = None):
        super().__init__(message=message, code=status.HTTP_409_CONFLICT, errors=errors)


class TooManyRequestsException(AppException):
    def __init__(
        self,
        message: str = "Too many requests",
        retry_after_seconds: int = 60,
    ):
        super().__init__(
            message=message,
            code=status.HTTP_429_TOO_MANY_REQUESTS,
            errors={"retry_after_seconds": retry_after_seconds},
        )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        logger.warning(f"AppException on {request.url.path}: {exc.message}")
        return error_response(message=exc.message, code=exc.code, errors=exc.errors)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        logger.warning(f"HTTPException on {request.url.path}: {exc.detail}")
        return error_response(message=str(exc.detail), code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        # Field location and error type only: errors() also echoes the submitted
        # input (phone numbers, PINs, symptom text) which must stay out of logs.
        fields = [f"{'.'.join(str(p) for p in e['loc'])}:{e['type']}" for e in exc.errors()]
        logger.warning("ValidationError on %s: %s", request.url.path, fields)
        return error_response(
            message="Request validation failed",
            code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            errors=jsonable_encoder(exc.errors()),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled exception on {request.url.path}")
        return error_response(
            message="Internal server error",
            code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
