"""Global chatbot scope gate, executed before intent routing and answer LLMs."""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from src.agents.state import AgentState
from src.modules.planning.core.llm import get_llm
from src.rag_retrieval.service import DrugRAG, fold

_TIMEOUT_SECONDS = 3.0
_OUT_OF_SCOPE_REPLY = (
    "Mình chỉ hỗ trợ về thuốc, đơn thuốc, lịch uống và các tính năng của RemindRx. "
    "Câu hỏi này nằm ngoài phạm vi hỗ trợ của mình."
)

_GREETING = {"xin chao", "chao", "chao ban", "hello", "hi", "cam on", "cam on ban"}
_ALLOWED_MARKERS = (
    "thuoc", "duoc thu", "hoat chat", "don thuoc", "bac si ke", "lieu",
    "cu uong", "lich uong", "lich thuoc", "da uong", "quen uong", "uong bu",
    "tac dung", "cong dung", "chi dinh", "chong chi dinh", "tuong tac",
    "phan ung", "di ung", "bao quan", "ham luong", "vien", "vien nang",
    "bua an", "an trua muon", "an sang muon", "an toi muon", "doi gio an",
    "remindrx", "ung dung", "app", "thong bao nhac", "dong bo",
)
_SYMPTOM_MARKERS = (
    "dau", "buon non", "non", "chong mat", "kho tho", "tuc nguc", "choang",
    "noi man", "ngua", "tieu chay", "sot", "met", "phu",
)
_CAPABILITY_MARKERS = (
    "ban lam duoc gi", "ban co the lam gi", "chuc nang chatbot", "ho tro gi",
    "toi co the hoi gi", "huong dan su dung",
)
_DATE_TIME_MARKERS = (
    "hom nay ngay bao nhieu", "hom nay la ngay may", "bay gio la may gio",
    "may gio roi", "ngay hien tai",
)


class ScopeClassification(BaseModel):
    category: Literal[
        "medication", "prescription_schedule", "adherence",
        "medication_related_symptom", "remindrx_help", "greeting",
        "date_time", "out_of_scope",
    ]
    reason: str = Field(description="Lý do ngắn, không trả lời câu hỏi của người dùng")
    confidence: float = Field(default=0.5, ge=0, le=1)


_SCOPE_PROMPT = """Phân loại phạm vi cho chatbot RemindRx. Không trả lời câu hỏi.

Được phép:
- thông tin thuốc/hoạt chất và thuốc trong đơn;
- đơn thuốc, lịch/cữ uống, liều tiếp theo, trạng thái uống và tuân thủ;
- triệu chứng hoặc lo ngại được hỏi trong bối cảnh dùng thuốc;
- báo lệch bữa ăn để xử lý lịch thuốc;
- cách sử dụng ứng dụng RemindRx;
- chào hỏi, hỏi năng lực chatbot, ngày/giờ hiện tại.

Ngoài phạm vi:
- thể thao, World Cup, chính trị, địa lý, giải trí, bài tập, sáng tác;
- kiến thức chung không phục vụ thuốc, lịch uống hoặc RemindRx.

Chỉ chọn category. Không coi một câu ngoài phạm vi là date_time chỉ vì nó hỏi
"ngày bao nhiêu"; ví dụ ngày kết thúc World Cup vẫn là out_of_scope.
Nếu câu có triệu chứng nhưng không rõ liên quan thuốc, chọn medication_related_symptom
để tầng an toàn xử lý thận trọng, không chẩn đoán."""


def _last_human_text(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def _obviously_allowed(normalized: str) -> str | None:
    padded = f" {normalized} "
    has = lambda marker: f" {marker} " in padded
    if normalized in _GREETING:
        return "greeting"
    if any(has(marker) for marker in _CAPABILITY_MARKERS):
        return "remindrx_help"
    if normalized in _DATE_TIME_MARKERS:
        return "date_time"
    if any(has(marker) for marker in _ALLOWED_MARKERS):
        return "medication"
    if any(has(marker) for marker in _SYMPTOM_MARKERS):
        return "medication_related_symptom"
    return None


@lru_cache(maxsize=1)
def _drug_resolver() -> DrugRAG:
    # Scope resolution only reads the local formulary lexicon.  Supplying a
    # sentinel avoids requiring API credentials before we even know whether
    # the message belongs to the drug chatbot.
    return DrugRAG(client=object())  # type: ignore[arg-type]


def _looks_like_drug_query(text: str, normalized: str) -> bool:
    """Recognize a named (including lightly misspelled) formulary drug locally."""
    question_markers = (
        "dung nhu the nao", "uong nhu the nao", "dung the nao", "uong the nao",
        "tac dung", "cong dung", "chi dinh", "tac dung phu", "tuong tac",
        "chong chi dinh", "bao quan", "lieu dung",
    )
    if not any(marker in normalized for marker in question_markers):
        return False
    try:
        normalized_drug, _ = _drug_resolver().infer_drug(text)
        return bool(normalized_drug)
    except Exception:
        return False


async def _classify_scope(text: str) -> ScopeClassification | None:
    try:
        llm = get_llm(temperature=0).with_structured_output(ScopeClassification)
        return await asyncio.wait_for(
            llm.ainvoke([
                {"role": "system", "content": _SCOPE_PROMPT},
                {"role": "user", "content": text},
            ]),
            timeout=_TIMEOUT_SECONDS,
        )
    except Exception:  # fail closed for input not known to be in product scope
        return None


def _recent_conversation(state: AgentState, limit: int = 5) -> str:
    lines = []
    for message in list(state.get("messages") or [])[-limit:]:
        role = "Người dùng" if isinstance(message, HumanMessage) else "Trợ lý"
        lines.append(f"{role}: {message.content}")
    return "\n".join(lines)


async def scope_guard_node(state: AgentState) -> dict:
    text = _last_human_text(state)
    normalized = fold(text)
    category = _obviously_allowed(normalized)
    if category is None and _looks_like_drug_query(text, normalized):
        category = "medication"
    if category is None:
        context = _recent_conversation(state)
        result = await _classify_scope(
            f"Hãy phân loại tin nhắn cuối dựa trên ngữ cảnh hội thoại.\n{context}"
        )
        category = result.category if result is not None else "out_of_scope"

    if category == "out_of_scope":
        return {
            "messages": [AIMessage(content=_OUT_OF_SCOPE_REPLY)],
            "scope_blocked": True,
            "scope_category": category,
        }
    return {"scope_blocked": False, "scope_category": category}
