"""Helpers for user-supplied LIKE/ILIKE search terms (SEC-24)."""

LIKE_ESCAPE_CHAR = "\\"


def escape_like(term: str) -> str:
    r"""Escape backslash, ``%`` and ``_`` so they match literally in LIKE/ILIKE.

    Pair with ``.ilike(pattern, escape=LIKE_ESCAPE_CHAR)``.
    """
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def contains_pattern(term: str) -> str:
    """``%term%`` pattern for a case-insensitive "contains" search on a stripped term."""
    return f"%{escape_like(term.strip())}%"
