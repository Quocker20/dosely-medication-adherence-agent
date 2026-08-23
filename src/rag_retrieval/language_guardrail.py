"""Language allow-list for standalone RAG input."""

from __future__ import annotations

import re

from langdetect import DetectorFactory, LangDetectException, detect_langs

DetectorFactory.seed = 0

SUPPORTED_LANGUAGES = {"vi", "en"}
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
_VIETNAMESE = re.compile(
    r"[ăđơưảãạấầẩẫậắằẳẵặẻẽẹếềểễệỉĩịỏõọốồổỗộớờởỡợủũụứừửữựỷỹỵ]",
    re.IGNORECASE,
)
_VIETNAMESE_ASCII_MARKERS = (
    "thuoc", "la gi", "co tac dung", "dung de", "duoc khong", "co nen",
    "tuong tac", "chong chi dinh", "tac dung phu", "lieu dung", "nhu the nao",
)


def detect_supported_language(text: str, *, recognized_drug: bool = False) -> str | None:
    """Return ``vi``/``en`` or ``None`` when input is unsupported.

    A bare international drug name is language-neutral and remains accepted.
    Vietnamese-specific characters are authoritative because statistical
    detectors are unreliable for short Vietnamese questions.
    """
    stripped = text.strip()
    if _VIETNAMESE.search(stripped):
        return "vi"
    words = _WORD.findall(stripped)
    if recognized_drug and len(words) <= 2:
        return "en"
    folded = " ".join(stripped.casefold().split())
    if any(marker in folded for marker in _VIETNAMESE_ASCII_MARKERS):
        return "vi"
    try:
        candidates = detect_langs(stripped)
    except LangDetectException:
        return "en" if recognized_drug else None
    for candidate in candidates:
        if candidate.lang in SUPPORTED_LANGUAGES and candidate.prob >= 0.70:
            return candidate.lang
    return None
