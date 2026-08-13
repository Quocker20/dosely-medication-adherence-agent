import logging
from typing import Any, Optional
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.response import error_response

logger = logging.getLogger(__name__)


class AppException(Exception):
    def __init__(
        self,
        message: str = "Internal server error",
        code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        errors: Optional[Any] = None,
    ):
        self.message = message
        self.code = code
        self.errors = errors
        super().__init__(message)


class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found", errors: Optional[Any] = None):
        super().__init__(message=message, code=status.HTTP_404_NOT_FOUND, errors=errors)


class UnauthorizedException(AppException):
    def __init__(self, message: str = "Unauthorized", errors: Optional[Any] = None):
        super().__init__(message=message, code=status.HTTP_401_UNAUTHORIZED, errors=errors)


class ForbiddenException(AppException):
    def __init__(self, message: str = "Forbidden", errors: Optional[Any] = None):
        super().__init__(message=message, code=status.HTTP_403_FORBIDDEN, errors=errors)


class ValidationException(AppException):
    def __init__(self, message: str = "Validation error", errors: Optional[Any] = None):
        super().__init__(message=message, code=status.HTTP_422_UNPROCESSABLE_ENTITY, errors=errors)


class ConflictException(AppException):
    def __init__(self, message: str = "Resource conflict", errors: Optional[Any] = None):
        super().__init__(message=message, code=status.HTTP_409_CONFLICT, errors=errors)


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
        logger.warning(f"ValidationError on {request.url.path}: {exc.errors()}")
        return error_response(
            message="Request validation failed",
            code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            errors=exc.errors(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled exception on {request.url.path}")
        return error_response(
            message="Internal server error",
            code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
