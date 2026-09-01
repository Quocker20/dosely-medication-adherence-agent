"""Final patient-facing text boundary for content validated with internal sources."""

from __future__ import annotations

import re

_INLINE_CITATION = re.compile(r"\s*\[(?:Nguồn|Source)\s*\d+]", re.IGNORECASE)
_SOURCE_ONLY_LINE = re.compile(
    r"^\s*(?:[-*•]\s*)?(?:Nguồn|Sources?|Tài liệu tham khảo)"
    r"(?:\s*\d+)?\s*[:：-]?(?:\s*(?:Dược thư|https?://|trang\s+\d+).*)?$",
    re.IGNORECASE,
)


def patient_facing_text(value: object) -> str:
    """Remove internal citation markers only after grounding has completed.

    Retrieval, generation and grounding continue to use source identifiers.
    This function belongs solely at the presentation boundary and must never be
    called before factual validation.
    """
    text = str(value or "")
    cleaned_lines: list[str] = []
    for raw_line in text.splitlines():
        if _SOURCE_ONLY_LINE.fullmatch(raw_line.strip()):
            continue
        cleaned = _INLINE_CITATION.sub("", raw_line)
        cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned).rstrip()
        # A citation often owns the full stop immediately after its closing
        # bracket; avoid leaving doubled punctuation when the claim already had one.
        cleaned = re.sub(r"([.!?])\1+", r"\1", cleaned)
        if cleaned.strip():
            cleaned_lines.append(cleaned)
        elif cleaned_lines and cleaned_lines[-1] != "":
            cleaned_lines.append("")
    while cleaned_lines and cleaned_lines[-1] == "":
        cleaned_lines.pop()
    return "\n".join(cleaned_lines).strip()
