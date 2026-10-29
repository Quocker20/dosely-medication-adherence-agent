"""SEC-24: LIKE wildcards in user search terms are matched literally."""

from src.common.search import contains_pattern, escape_like

BACKSLASH = chr(92)


def test_escape_like_escapes_wildcards_and_escape_char():
    assert escape_like("50%_off" + BACKSLASH + "x") == "50" + BACKSLASH + "%" + BACKSLASH + "_off" + BACKSLASH * 2 + "x"


def test_contains_pattern_strips_and_wraps():
    assert contains_pattern("  a%b ") == "%a" + BACKSLASH + "%b%"
