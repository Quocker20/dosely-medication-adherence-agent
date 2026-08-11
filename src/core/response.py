from typing import Any, Generic, Optional, TypeVar
from pydantic import BaseModel
from fastapi.responses import JSONResponse

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    success: bool
    code: int
    message: str
    data: Optional[T] = None
    errors: Optional[Any] = None


def success_response(
    data: Optional[Any] = None,
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
    errors: Optional[Any] = None,
) -> JSONResponse:
    payload = APIResponse(
        success=False,
        code=code,
        message=message,
        data=None,
        errors=errors,
    ).model_dump(mode="json")
    return JSONResponse(status_code=code, content=payload)
