"""Deterministic input-domain guardrail for the standalone drug RAG."""

from __future__ import annotations

from dataclasses import dataclass

from src.rag_retrieval.service import fold


@dataclass(frozen=True)
class InputRoute:
    intent: str
    reply: str | None = None


_CAPABILITY_MARKERS = (
    "ban lam duoc gi",
    "ban co the lam gi",
    "chuc nang cua ban",
    "chuc nang chatbot",
    "chatbot lam duoc gi",
    "huong dan su dung",
    "toi co the hoi gi",
    "ho tro gi",
)
_GREETING_MARKERS = {
    "hello",
    "hi",
    "xin chao",
    "chao",
    "chao ban",
    "cam on",
    "cam on ban",
}
_DRUG_MARKERS = (
    "thuoc",
    "duoc thu",
    "duoc chat",
    "hoat chat",
    "ma atc",
    "chi dinh",
    "chong chi dinh",
    "tuong tac",
    "tac dung phu",
    "tac dung khong mong muon",
    "duoc dong hoc",
    "duoc luc hoc",
    "lieu dung",
    "ham luong",
    "bao che",
)
_AMBIGUOUS_DRUG_REFERENCES = (
    "thuoc nay",
    "thuoc do",
    "thuoc vua nay",
    "thuoc luc nay",
    "thuoc tren",
    "thuoc truoc do",
    "thuoc truoc nua",
    "loai thuoc nay",
    "loai thuoc do",
    "loai thuoc tren",
    "loai thuoc truoc do",
    "hoat chat nay",
    "hoat chat do",
    "hoat chat truoc do",
)

_CONTEXTUAL_DRUG_REFERENCES = _AMBIGUOUS_DRUG_REFERENCES + (
    "no la thuoc gi",
    "no co tac dung gi",
)

CAPABILITY_REPLY = (
    "Mình hỗ trợ tra cứu Dược thư Quốc gia về thuốc và hoạt chất, gồm chỉ định, "
    "chống chỉ định, tương tác, tác dụng không mong muốn, cảnh báo, dược động học, "
    "dạng bào chế và các mục liên quan. Câu trả lời tra cứu sẽ kèm nguồn và trang. "
    "Mình không thay bác sĩ/dược sĩ để kê đơn hoặc quyết định thay đổi điều trị."
)
GREETING_REPLY = (
    "Xin chào! Mình có thể giúp bạn tra cứu thông tin thuốc trong Dược thư Quốc gia. "
    "Bạn hãy nhập tên thuốc hoặc hoạt chất và nội dung muốn tìm, ví dụ: "
    "“Amoxicilin có chống chỉ định gì?”"
)
OUT_OF_SCOPE_REPLY = (
    "Câu hỏi này nằm ngoài phạm vi của chatbot. Mình chỉ hỗ trợ tra cứu thông tin "
    "thuốc và hoạt chất trong Dược thư Quốc gia."
)
NEEDS_DRUG_NAME_REPLY = (
    "Bạn vui lòng cung cấp tên thuốc hoặc hoạt chất cần tra cứu để mình tìm đúng "
    "thông tin trong Dược thư Quốc gia."
)


def is_contextual_drug_reference(question: str) -> bool:
    """Return whether the question explicitly refers to an earlier drug."""
    normalized = fold(question)
    return any(marker in normalized for marker in _CONTEXTUAL_DRUG_REFERENCES)


def contextual_drug_offset(question: str) -> int:
    """Return the referenced drug's offset in ordered conversation topics."""
    normalized = fold(question)
    previous_markers = (
        "thuoc truoc thuoc vua nay",
        "thuoc truoc do",
        "thuoc truoc nua",
        "loai thuoc truoc do",
        "hoat chat truoc do",
    )
    return -2 if any(marker in normalized for marker in previous_markers) else -1


def route_input(question: str, *, recognized_drug: bool = False) -> InputRoute:
    """Classify non-safety input before retrieval or answer generation."""
    normalized = fold(question)
    if any(marker in normalized for marker in _CAPABILITY_MARKERS):
        return InputRoute("capability", CAPABILITY_REPLY)
    if normalized in _GREETING_MARKERS:
        return InputRoute("greeting", GREETING_REPLY)
    if not recognized_drug and any(
        marker in normalized for marker in _AMBIGUOUS_DRUG_REFERENCES
    ):
        return InputRoute("needs_drug_name", NEEDS_DRUG_NAME_REPLY)
    if recognized_drug or any(marker in normalized for marker in _DRUG_MARKERS):
        return InputRoute("drug_query")
    return InputRoute("out_of_scope", OUT_OF_SCOPE_REPLY)
