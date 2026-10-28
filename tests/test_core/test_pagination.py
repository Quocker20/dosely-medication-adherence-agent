import pytest

from src.common.pagination import page_count


@pytest.mark.parametrize(
    ("total", "size", "expected"),
    [(0, 10, 0), (1, 10, 1), (10, 10, 1), (11, 10, 2), (95, 10, 10), (5, 1, 5)],
)
def test_page_count(total, size, expected):
    assert page_count(total, size) == expected


def test_page_count_negative_total_is_zero():
    assert page_count(-3, 10) == 0


def test_page_count_rejects_non_positive_size():
    with pytest.raises(ValueError):
        page_count(10, 0)
