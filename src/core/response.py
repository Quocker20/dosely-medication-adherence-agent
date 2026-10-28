from typing import Any, Generic, TypeVar

from fastapi.responses import JSONResponse
from pydantic import BaseModel

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    success: bool
    code: int
    message: str
    data: T | None = None
    errors: Any | None = None


def success_response(
    data: Any | None = None,
    message: str = "Success",
    code: int = 200,
) -> JSONResponse:
    payload = APIResponse(
        success=True,
        code=code,
        message=message,
        data=data,
        errors=None,
    ).model_dump(mode="json")
    return JSONResponse(status_code=code, content=payload)


def error_response(
    message: str = "Error occurred",
    code: int = 400,
    errors: Any | None = None,
) -> JSONResponse:
    payload = APIResponse(
        success=False,
        code=code,
        message=message,
        data=None,
        errors=errors,
    ).model_dump(mode="json")
    return JSONResponse(status_code=code, content=payload)
