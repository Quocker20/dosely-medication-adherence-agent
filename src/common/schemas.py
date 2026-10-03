from typing import Generic, List, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class PageResponse(BaseModel, Generic[T]):
    """Standard pagination wrapper schema."""

    content: List[T]
    page_no: int
    page_size: int
    total_elements: int
    total_pages: int
    last: bool


# Backward compatibility alias
PageResponseDto = PageResponse
