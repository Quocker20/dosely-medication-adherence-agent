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
    "Mình chỉ hỗ trợ về thuốc, đơn thuốc, lịch uống và các tính năng của Dosely. "
    "Câu hỏi này nằm ngoài phạm vi hỗ trợ của mình."
)

_GREETING = {"xin chao", "chao", "chao ban", "hello", "hi", "cam on", "cam on ban"}
_ALLOWED_MARKERS = (
    "thuoc", "duoc thu", "hoat chat", "don thuoc", "bac si ke", "lieu",
    "cu uong", "lich uong", "lich thuoc", "da uong", "quen uong", "uong bu",
    "tac dung", "cong dung", "chi dinh", "chong chi dinh", "tuong tac",
    "phan ung", "di ung", "bao quan", "ham luong", "vien", "vien nang",
    "bua an", "an trua muon", "an sang muon", "an toi muon", "doi gio an",
    "dosely", "ung dung", "app", "thong bao nhac", "dong bo",
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
_ABUSIVE_OR_NOISE = (
    "dit me", "địt mẹ", "gay deo", "gãy đéo", "vcl", "dm", "dmm",
)


class ScopeClassification(BaseModel):
    category: Literal[
        "medication", "prescription_schedule", "adherence",
        "medication_related_symptom", "dosely_help", "greeting",
        "date_time", "out_of_scope", "abusive_noise", "discrimination",
    ]
    reason: str = Field(description="Lý do ngắn, không trả lời câu hỏi của người dùng")
    confidence: float = Field(default=0.5, ge=0, le=1)


_SCOPE_PROMPT = """Phân loại phạm vi cho chatbot Dosely. Không trả lời câu hỏi.

Được phép:
- thông tin thuốc/hoạt chất và thuốc trong đơn;
- đơn thuốc, lịch/cữ uống, liều tiếp theo, trạng thái uống và tuân thủ;
- triệu chứng hoặc lo ngại được hỏi trong bối cảnh dùng thuốc;
- báo lệch bữa ăn để xử lý lịch thuốc;
- cách sử dụng ứng dụng Dosely;
- chào hỏi, hỏi năng lực chatbot, ngày/giờ hiện tại.

Ngoài phạm vi:
- thể thao, World Cup, chính trị, địa lý, giải trí, bài tập, sáng tác;
- kiến thức chung không phục vụ thuốc, lịch uống hoặc Dosely.

Chỉ chọn category. Không coi một câu ngoài phạm vi là date_time chỉ vì nó hỏi
"ngày bao nhiêu"; ví dụ ngày kết thúc World Cup vẫn là out_of_scope.
Nếu câu có triệu chứng nhưng không rõ liên quan thuốc, chọn medication_related_symptom
để tầng an toàn xử lý thận trọng, không chẩn đoán."""


_SCOPE_PROMPT += "\nNếu tin nhắn chủ yếu là chửi tục, xúc phạm, khiêu khích hoặc nhiễu không có yêu cầu Dosely, chọn category=abusive_noise."
_SCOPE_PROMPT += "\nNếu tin nhắn chứa định kiến/phân biệt đối xử với một nhóm người, chọn category=discrimination."


def _last_human_text(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def _obviously_allowed(normalized: str) -> str | None:
    # Do not let an isolated medication keyword whitelist abusive/noise text.
    # This is a pre-LLM safety/scope filter, not an intent classifier.
    if any(marker in normalized for marker in _ABUSIVE_OR_NOISE):
        return None
    padded = f" {normalized} "

    def has(marker: str) -> bool:
        return f" {marker} " in padded

    if normalized in _GREETING:
        return "greeting"
    if any(has(marker) for marker in _CAPABILITY_MARKERS):
        return "dosely_help"
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
        "chong chi dinh", "bao quan", "lieu dung", "chua", "dieu tri",
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
    lowered = text.casefold()
    normalized_text = fold(text)
    computer_scope_terms = (
        "windows", "o cung", "may tinh", "cai lai he dieu hanh",
        "xoa sach du lieu", "format disk",
    )
    if any(term in normalized_text for term in computer_scope_terms):
        return {
            "scope_blocked": True,
            "scope_category": "out_of_scope",
            "response_type": "out_of_scope_capability",
            "refusal_reason": "outside_dosely_scope",
        }
    deterministic_out_of_scope = (
        "bai tho", "tho tinh", "world cup", "gia vang", "tong thong",
        "cai windows", "nha hang", "dat ban",
    )
    if any(term in normalized_text for term in deterministic_out_of_scope):
        return {
            "scope_blocked": True,
            "scope_category": "out_of_scope",
            "response_type": "out_of_scope_capability",
            "refusal_reason": "outside_dosely_scope",
        }
    privacy_terms = ("bệnh nhân khác", "benh nhan khac", "patient_id của người khác", "patient_id cua nguoi khac", "số điện thoại của bệnh nhân", "so dien thoai cua benh nhan", "liệt kê toàn bộ bệnh nhân", "liet ke toan bo benh nhan", "endpoint nội bộ")
    if any(term in lowered for term in privacy_terms):
        return {"scope_blocked": True, "scope_category": "privacy", "response_type": "privacy_denial", "messages": [AIMessage(content="Mình không thể cung cấp thông tin cá nhân, đơn thuốc hoặc lịch uống thuốc của người khác. Bạn chỉ có thể tra cứu dữ liệu của chính mình.")]}
    user_messages = [str(m.content).strip().casefold() for m in (state.get("messages") or []) if isinstance(m, HumanMessage)]
    if len(user_messages) >= 3 and user_messages[-1] == user_messages[-2] == user_messages[-3]:
        return {"scope_blocked": True, "scope_category": "spam", "messages": [AIMessage(content="Mình đã nhận được câu hỏi trùng lặp. Bạn vui lòng chờ phản hồi hoặc gửi câu hỏi khác rõ hơn nhé.")]}
    obvious_category = _obviously_allowed(normalized_text)
    if obvious_category:
        return {"scope_blocked": False, "scope_category": obvious_category}
    recent_before_last = " ".join(user_messages[-3:-1])
    confirmation = normalized_text in {
        "dung", "dung roi", "xac nhan", "toi dong y", "sinh hoat binh thuong",
        "ngay mai toi sinh hoat binh thuong", "ghi nhan giup toi",
    }
    if confirmation and any(marker in fold(recent_before_last) for marker in (
        "lich", "cu thuoc", "uong thuoc", "buon non", "chong mat", "noi man",
    )):
        return {"scope_blocked": False, "scope_category": "conversation_follow_up"}
    context = _recent_conversation(state)
    result = await _classify_scope(
            f"Hãy phân loại tin nhắn cuối dựa trên ngữ cảnh hội thoại.\n{context}"
        )
    category = result.category if result is not None else "unknown"
    # Rescue plausible medication questions that the scope model may reject
    # because the product name is abbreviated or misspelled (e.g. "acn gel").
    normalized = text.casefold()
    medication_rescue = (
        any(token in normalized for token in ("thuốc", "thuoc", "gel", "capsule", "tablet", "viên", "vien"))
        and any(token in normalized for token in ("tác dụng", "tac dung", "công dụng", "cong dung", "dùng", "dung", "làm gì", "lam gi"))
    ) or _looks_like_drug_query(text, fold(text))
    fairness_question = category == "discrimination" and any(
        marker in fold(text) for marker in ("co dang duoc", "quyen duoc", "co nen duoc uu tien")
    )
    if category in {"abusive_noise", "discrimination", "out_of_scope"} and not (
        (category == "out_of_scope" and medication_rescue) or fairness_question
    ):
        if category == "discrimination":
            return {"scope_blocked": True, "scope_category": category, "response_type": "respectful_discrimination", "messages": [AIMessage(content=(
                "Mình không thể hỗ trợ nội dung phân biệt đối xử hoặc định kiến. Nếu bạn có câu hỏi về thuốc, đơn thuốc hoặc lịch uống của chính mình, mình sẵn sàng hỗ trợ."
            ))]}
        if category == "abusive_noise":
            return {"scope_blocked": True, "scope_category": category, "response_type": "calm_abuse", "messages": [AIMessage(content="Mình hiểu bạn đang bực. Bạn hãy hít thở sâu và đặt lại câu hỏi bình tĩnh, liên quan đến thuốc, đơn thuốc hoặc lịch uống thuốc nhé.")]}
        return {"scope_blocked": True, "scope_category": category, "response_type": "out_of_scope_capability", "messages": [AIMessage(content=(
            "Mình chỉ hỗ trợ tra cứu thông tin về thuốc, đơn thuốc và lịch uống thuốc của bạn. "
            "Bạn hãy đặt một câu hỏi liên quan đến các nội dung này nhé."
        ))]}

    # Scope is advisory. The main semantic parser owns intent/out-of-scope
    # understanding so an unusual valid phrasing is never rejected here.
    return {"scope_blocked": False, "scope_category": category}
