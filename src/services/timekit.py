"""Helper giờ giấc dùng chung cho validator và Planning Agent.

Toàn bộ là hàm thuần, không phụ thuộc LLM — lịch uống thuốc phải tính được
lặp lại y hệt giữa các lần chạy (mục 7.2: deterministic core).
"""

from __future__ import annotations

DAY_MINUTES = 24 * 60


def to_minutes(hhmm: str) -> int:
    """ "07:30" -> 450."""
    hours, _, minutes = hhmm.partition(":")
    return int(hours) * 60 + int(minutes)


def to_hhmm(minutes: int) -> str:
    """450 -> "07:30". Tự cuộn vòng trong ngày."""
    minutes %= DAY_MINUTES
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def shift(hhmm: str, delta_minutes: int) -> str:
    """Dời một mốc giờ đi delta phút (âm = sớm hơn)."""
    return to_hhmm(to_minutes(hhmm) + delta_minutes)


def min_gap_minutes(times: list[str]) -> int:
    """Khoảng cách nhỏ nhất giữa hai mốc liên tiếp trong ngày.

    Trả về DAY_MINUTES nếu chỉ có 0-1 mốc (không có ràng buộc khoảng cách).
    """
    if len(times) < 2:
        return DAY_MINUTES
    ordered = sorted(to_minutes(t) for t in times)
    return min(b - a for a, b in zip(ordered, ordered[1:], strict=False))
