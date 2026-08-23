"""Dependency-free deterministic policy for patient-specific medication decisions."""

from __future__ import annotations

import re
import unicodedata

DECISION_MARKERS = (
    "duoc khong", "co nen", "co the", "an toan khong", "giup toi", "cho toi",
)
PERSONAL_MARKERS = ("toi", "minh", "chau", "ban", "me toi", "bo toi", "con toi")
MEDICATION_RULES = (
    ("DOSE_CHANGE", ("tang lieu", "giam lieu", "doi lieu", "gap doi lieu", "bot lieu", "them lieu", "tang gap", "uong them", "uong gap doi")),
    ("STOP_MEDICATION", ("ngung thuoc", "bo thuoc", "nghi thuoc")),
    ("PRESCRIBE_MEDICATION", ("ke thuoc", "mua thuoc gi", "dung thuoc gi", "uong thuoc gi", "cho toi thuoc")),
    ("COADMINISTRATION_DECISION", ("uong cung", "dung cung", "phoi hop", "uong chung", "dung chung")),
)

_RECOMMENDATION_REQUEST = re.compile(
    r"\b(?:co|goi y|tu van|chon)\s+(?:mot\s+)?thuoc\s+(?:nao|gi)\b|"
    r"\bthuoc\s+(?:nao|gi)\s+(?:ho tro|giup|tri|dieu tri|chua|dung cho)\b"
)


def fold(value: str) -> str:
    value = unicodedata.normalize("NFD", value.casefold().replace("đ", "d"))
    value = "".join(character for character in value if unicodedata.category(character) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def match_medication_decision(text: str) -> str | None:
    """Return a policy code for patient-specific treatment decisions."""
    normalized = fold(text)
    raw = unicodedata.normalize("NFC", text.casefold())
    has_decision = any(marker in normalized for marker in DECISION_MARKERS)
    tokens = normalized.split()
    has_personal = (
        any(marker in tokens for marker in PERSONAL_MARKERS[:4])
        or any(marker in normalized for marker in PERSONAL_MARKERS[4:])
        # "em" is a personal pronoun only in direct address, not in "trẻ em".
        or normalized == "em"
        or normalized.startswith("em ")
        or " cho em" in f" {normalized}"
        or " cua em" in f" {normalized}"
    )
    # Keep tones: folding makes "dừng" (stop) and "dùng" (use) identical.
    if "dừng thuốc" in raw and (has_decision or has_personal):
        return "STOP_MEDICATION"
    if _RECOMMENDATION_REQUEST.search(normalized):
        return "PRESCRIBE_MEDICATION"
    for code, actions in MEDICATION_RULES:
        if any(action in normalized for action in actions) and (
            code == "PRESCRIBE_MEDICATION" or has_decision or has_personal
        ):
            return code
    # Catch patient-specific take/use decisions after the more specific rules,
    # so phrases such as "uong chung" remain coadministration decisions.
    if has_decision and has_personal and re.search(
        r"\b(?:uong|dung|tiem|boi|dat)\b", normalized
    ):
        return "TAKE_MEDICATION_DECISION"
    return None
