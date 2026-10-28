"""Shared pagination arithmetic."""


def page_count(total: int, size: int) -> int:
    """Number of pages needed for `total` rows at `size` per page (0 when empty)."""
    if size < 1:
        raise ValueError("size must be >= 1")
    if total <= 0:
        return 0
    return (total + size - 1) // size
