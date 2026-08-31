"""classify_intent_node — Sprint 6 của "Kế hoạch build tầng 2 — Agent layer".

Chạy SAU safety_guard_node (đã lọc triệu chứng nặng trên MỌI input rồi —
xem graph.py), nên KHÔNG có nhãn "report_symptom" riêng ở đây như sketch
gốc trong kế hoạch: report_symptom đã được xử lý xong trước khi tới node
này, không cần phân loại lại.

"report_meal_shift" đi riêng tới rescheduling_node vì đây là nhánh có ràng
buộc HITL cấu trúc cứng. "ask_drug_info" đi riêng tới SafeDrugRAG để mọi
câu trả lời thông tin thuốc bắt buộc retrieval, citation và grounding. Các
nhãn còn lại mới đi qua agent_node (chat ReAct loop). Nhãn cũng được lưu để
phục vụ audit log (xem src/agents/audit.py).

LLM phân loại lỗi -> mặc định "general" (fail-open về phía an toàn nhất:
để agent_node — vốn có system prompt riêng chặn HITL — xử lý, thay vì
đoán bừa route sang rescheduling).
"""

from __future__ import annotations

import re
from typing import Literal

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from src.agents.state import AgentState
from src.modules.planning.core.llm import get_llm

_MY_MEDICATION_PHRASES = (
    "tôi đang uống thuốc",
    "tôi đang dùng thuốc",
    "thuốc tôi đang uống",
    "thuốc tôi đang dùng",
    "thuốc hiện tại của tôi",
    "danh sách thuốc hiện tại",
    "bác sĩ đang cho tôi dùng thuốc",
    "bác sĩ kê cho tôi thuốc",
    "bác sĩ kê cho tôi",
    "xem thuốc của tôi",
    "what medicines am i taking",
    "what medications am i taking",
    "my current medications",
)

_EXPLAIN_MY_MEDICATION_PHRASES = (
    "giải thích cách dùng thuốc của tôi",
    "giải thích thuốc của tôi",
    "thuốc của tôi dùng như thế nào",
    "cách dùng các thuốc của tôi",
    "explain my medications",
)

_NEXT_DOSE_PHRASES = (
    "liều tiếp theo",
    "cữ tiếp theo",
    "thuốc tiếp theo lúc",
    "next dose",
)

_TODAY_SCHEDULE_PHRASES = (
    "lịch thuốc hôm nay",
    "lịch uống thuốc hôm nay",
    "hôm nay uống thuốc gì",
    "hôm nay tôi uống thuốc gì",
    "các cữ thuốc hôm nay",
    "today's medication schedule",
    "my schedule today",
)

_DOSE_STATUS_QUESTION_MARKERS = (
    "bỏ qua thuốc", "bỏ qua cữ", "bỏ lỡ thuốc", "bỏ lỡ cữ",
    "quên uống thuốc", "quên cữ", "có quên thuốc", "đã uống chưa",
    "missed any medicine", "missed any medication", "skipped any dose",
)

_DRUG_INFO_MARKERS = (
    "tác dụng", "công dụng", "chỉ định", "chống chỉ định", "tác dụng phụ",
    "phản ứng bất lợi", "tương tác", "cách dùng", "đường dùng", "bảo quản",
    "quên liều", "mang thai", "thai kỳ", "cho con bú", "used for",
    "dùng như thế nào", "uống như thế nào", "dùng thế nào", "uống thế nào", "uống lúc nào",
    "dị ứng", "mẫn cảm", "phát ban", "nổi mẩn", "ngứa",
    "side effect", "contraindication", "interaction", "how to take", "storage",
)

_SCHEDULED_DRUG_CONTEXT_MARKERS = (
    "lúc đói", "khi đói", "trước ăn", "sau ăn", "cùng bữa", "sau bữa",
    "đau bụng", "buồn nôn", "chóng mặt", "dị ứng", "nổi mẩn", "tiêu chảy",
    "có sai không", "có đúng không", "ảnh hưởng", "do thuốc",
)

_INDIRECT_DRUG_REFERENCE_MARKERS = (
    "thuốc này", "thuốc đó", "viên này", "viên đó", "cữ vừa", "vừa uống",
    "sắp uống", "buổi sáng", "buổi trưa", "buổi tối", "trước khi ngủ",
    "trước ăn", "sau ăn", "thuốc thứ", "viên thứ",
)

_CLASSIFY_SYSTEM_PROMPT = """Bạn là bộ phân tích mục đích câu hỏi của bệnh nhân.
Không trả lời câu hỏi y tế. Phân tích NGHĨA của cả câu, không chọn intent chỉ
vì nhìn thấy một từ như "cữ", "giờ", "thuốc" hay "đau".

Trả về cấu trúc gồm intent, topics, reference_type, drug_name, schedule_time,
date_reference, symptoms, requested_action, needs_clarification và confidence.

Các intent:

- "report_meal_shift": bệnh nhân báo một bữa ăn hôm nay bị lệch giờ (ăn sớm/muộn hơn thường lệ)
- "ask_schedule": mục tiêu chính là xem toàn bộ lịch/các cữ hoặc trạng thái đã uống
- "ask_my_medications": hỏi danh sách thuốc bản thân đang được kê/đang sử dụng
- "explain_my_medications": yêu cầu giải thích cách dùng các thuốc của bản thân
- "ask_next_dose": hỏi cữ/liều tiếp theo của bản thân
- "ask_drug_info": hỏi thông tin về một thuốc được nêu tên trực tiếp
- "ask_scheduled_drug_info": dùng giờ/cữ để XÁC ĐỊNH THUỐC, còn mục tiêu chính
  là hỏi công dụng, cách dùng, liên quan bữa ăn, tác dụng phụ hoặc triệu chứng
- "general": mọi trường hợp khác

Quy tắc phân biệt bắt buộc:
1. Hỏi "lịch/các cữ hôm nay" -> ask_schedule.
2. Hỏi "cữ tiếp theo" -> ask_next_dose.
3. Nếu giờ/cữ chỉ giúp tìm thuốc, còn câu hỏi là thuốc có tác dụng gì, gây triệu
   chứng gì, uống đói/no có đúng chỉ dẫn không -> ask_scheduled_drug_info.
4. Intent phản ánh thông tin cần có trong CÂU TRẢ LỜI, không phải dữ kiện phụ.
5. Không tự suy ra tên thuốc từ giờ; để reference_type=schedule_time cho backend xác minh.
6. Nếu người dùng nêu rõ tên thuốc, kể cả tên thương mại, reference_type=drug_name và giữ
   nguyên tên đó trong drug_name. Không đổi sang tham chiếu cữ nếu câu không dùng giờ/cữ để tìm thuốc.
7. Nếu tin nhắn chỉ là tên thuốc mà chưa nói muốn biết gì, vẫn chọn ask_drug_info,
   reference_type=drug_name, needs_clarification=true; không coi là sai ngôn ngữ.

Ví dụ câu "Tôi đau bụng, chắc do uống lúc đói; thuốc cữ 7h30 dùng vậy có sai
không?" phải là ask_scheduled_drug_info, topics=[administration, adverse_effect],
reference_type=schedule_time, schedule_time=07:30, symptoms=[đau bụng]."""


class IntentClassification(BaseModel):
    intent: Literal[
        "report_meal_shift",
        "ask_schedule",
        "ask_my_medications",
        "explain_my_medications",
        "ask_next_dose",
        "ask_drug_info",
        "ask_scheduled_drug_info",
        "ask_prescribed_drug_info",
        "general",
    ] = Field(
        description="Nhãn ý định của tin nhắn — xem hướng dẫn."
    )
    topics: list[Literal[
        "schedule", "identity", "indication", "administration", "adverse_effect",
        "interaction", "contraindication", "missed_dose", "storage",
        "precaution", "regimen", "dose_status", "treatment_change", "other",
    ]] = Field(default_factory=list)
    reference_type: Literal[
        "none", "drug_name", "schedule_time", "dose_period", "next_dose",
        "recent_dose", "meal_relation", "prescription_ordinal", "recent_context",
        "current_medications"
    ] = "none"
    drug_name: str | None = None
    schedule_time: str | None = None
    dose_period: Literal["morning", "noon", "evening", "bedtime"] | None = None
    meal_relation: Literal["BEFORE_MEAL", "AFTER_MEAL", "WITH_MEAL"] | None = None
    prescription_ordinal: int | None = Field(default=None, ge=1)
    date_reference: str | None = None
    symptoms: list[str] = Field(default_factory=list)
    requested_action: Literal[
        "view_schedule", "identify_drug", "explain", "check_instructions",
        "report_event", "change_treatment", "other",
    ] = "other"
    needs_clarification: bool = False
    confidence: float = Field(default=0.5, ge=0, le=1)


_INDIRECT_REFERENCE_PROMPT = """

Quy tắc cho câu hỏi thuốc gián tiếp:
- Phân tích độc lập (1) người dùng đang chỉ thuốc nào và (2) họ hỏi những topic nào.
- Chọn intent=ask_prescribed_drug_info khi thuốc thuộc đơn/lịch cá nhân nhưng được nhắc
  qua giờ/cữ, buổi, cữ vừa uống/sắp uống, quan hệ bữa ăn, thứ tự trong đơn hoặc ngữ cảnh trước.
- reference_type tương ứng là schedule_time, dose_period, recent_dose, next_dose,
  meal_relation, prescription_ordinal hoặc recent_context.
- Có thể trả nhiều topics: identity, indication, administration, adverse_effect,
  interaction, contraindication, missed_dose, storage, precaution, regimen, dose_status.
- Không nhận dạng thuốc chỉ bằng màu, hình dạng hay bệnh được mô tả. Khi tham chiếu yếu,
  đặt reference_type=none và needs_clarification=true; tuyệt đối không đoán tên thuốc.
"""

# Clean UTF-8 classifier instructions. Keep this separate from the legacy
# constants above, which contain historical mojibake and are used only by the
# deterministic fallback compatibility layer.
_CLEAN_CLASSIFY_PROMPT = """
Bạn là bộ phân tích mục đích cho chatbot RemindRx. Chỉ phân tích tin nhắn cuối
dựa trên tối đa 6 lượt hội thoại gần nhất; không trả lời nội dung y tế.

Chọn đúng một intent:
- ask_schedule: xem lịch/cữ/trạng thái đã uống, chưa uống, bỏ qua; có thể kèm ngày,
  buổi hoặc giờ. Nếu người dùng hỏi 'giờ X có thuốc gì/cần uống gì không' thì luôn là ask_schedule.
- ask_next_dose: hỏi liều hoặc cữ kế tiếp.
- ask_my_medications: hỏi danh sách thuốc hiện đang được kê/đang dùng.
- explain_my_medications: giải thích cách dùng các thuốc trong đơn của chính người dùng.
- ask_drug_info: hỏi thông tin của thuốc/hoạt chất được nêu trực tiếp (công dụng,
  tác dụng phụ, tương tác, chống chỉ định, bảo quản).
- ask_prescribed_drug_info: hỏi thông tin một thuốc trong đơn nhưng chỉ tham chiếu
  bằng giờ, buổi, cữ, thứ tự hoặc ngữ cảnh gần đây; không được đoán tên thuốc.
- report_meal_shift: báo bữa ăn hôm nay lệch giờ.
- general: chào hỏi hoặc ngoài phạm vi.

Ưu tiên ngữ nghĩa của toàn câu, không chọn intent chỉ vì thấy từ 'thuốc', 'giờ'
hoặc 'cữ'. Nếu câu vừa hỏi lịch vừa hỏi thông tin thuốc, chọn intent phản ánh
mục tiêu chính và ghi đủ topics. Nếu thiếu tên thuốc/giờ cần thiết, đặt
needs_clarification=true. Câu không dấu hoặc sai chính tả vẫn phải hiểu theo ngữ cảnh.
Giữ nguyên drug_name nếu người dùng nêu; không tự bịa tên thuốc.
"""

def _repair_prompt_encoding(value: str) -> str:
    """Decode legacy UTF-8-as-Latin-1 text embedded in old prompt constants."""
    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def _validated_intent(analysis: IntentClassification) -> str:
    """Reject a schedule route when time is only a reference to a drug."""
    # A dose-status request is itself a schedule query. A period such as
    # ``morning`` filters the schedule; it does not turn the question into a
    # request for formulary information about a prescribed drug.
    if analysis.intent == "ask_schedule" and "dose_status" in analysis.topics:
        return "ask_schedule"
    medication_topics = {
        "indication", "administration", "adverse_effect", "interaction", "contraindication"
    }
    indirect_references = {
        "schedule_time", "dose_period", "next_dose", "recent_dose",
        "meal_relation", "prescription_ordinal", "recent_context",
    }
    if analysis.reference_type in indirect_references and (
        medication_topics.intersection(analysis.topics)
        or {"identity", "missed_dose", "regimen", "dose_status"}.intersection(analysis.topics)
    ):
        return "ask_prescribed_drug_info"
    return analysis.intent


def _semantic_consistency_override(text: str, analysis: IntentClassification) -> str:
    """Correct only unambiguous schedule-vs-drug contradictions from the LLM."""
    folded = " ".join(text.casefold().split())
    asks_what_to_take = bool(re.search(r"(?:có|can|cần|phải)\s+thuốc|uống thuốc nào|thuốc nào.*(?:chưa uống|cần uống)", folded))
    has_time_or_day = bool(re.search(r"\b\d{1,2}\s*(?:giờ|h)(?:\s*(?:sáng|trưa|chiều|tối))?|hôm nay|ngày mai|sáng nay|chiều nay|tối nay", folded))
    asks_drug_properties = any(term in folded for term in ("tác dụng", "công dụng", "tác dụng phụ", "cách dùng", "tương tác", "chống chỉ định"))
    if asks_what_to_take and has_time_or_day and not asks_drug_properties:
        return "ask_schedule"
    return _validated_intent(analysis)


def _fallback_scheduled_drug_intent(normalized: str) -> bool:
    """Fallback only when LLM semantic parsing is unavailable."""
    has_reference = bool(
        re.search(r"\b(?:cữ|liều|thuốc)\b.{0,30}\b\d{1,2}(?::|h)\d{0,2}\b", normalized)
        or re.search(r"\b\d{1,2}(?::|h)\d{0,2}\b.{0,30}\b(?:cữ|liều|thuốc)\b", normalized)
    )
    return has_reference and any(
        marker in normalized for marker in (*_DRUG_INFO_MARKERS, *_SCHEDULED_DRUG_CONTEXT_MARKERS)
    )


def _last_human_text(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def _recent_conversation(state: AgentState, limit: int = 6) -> str:
    lines = []
    for message in list(state.get("messages") or [])[-limit:]:
        role = "Người dùng" if isinstance(message, HumanMessage) else "Trợ lý"
        lines.append(f"{role}: {message.content}")
    return "\n".join(lines)


def _fallback_indirect_reference(normalized: str) -> dict | None:
    """Fail closed to a resolvable reference; never infer a drug identity."""
    if any(marker in normalized for marker in ("thuốc này", "thuốc đó", "viên này", "viên đó")):
        return {"reference_type": "recent_context"}
    if any(marker in normalized for marker in ("vừa uống", "cữ vừa")):
        return {"reference_type": "recent_dose"}
    if any(marker in normalized for marker in ("sắp uống", "cữ tiếp", "liều tiếp")):
        return {"reference_type": "next_dose"}
    for marker, period in (("buổi sáng", "morning"), ("buổi trưa", "noon"), ("buổi tối", "evening"), ("trước khi ngủ", "bedtime")):
        if marker in normalized:
            return {"reference_type": "dose_period", "dose_period": period}
    return None


def _deterministic_topics(normalized: str) -> list[str]:
    topics: list[str] = []
    groups = (
        ("identity", ("thuốc gì", "tên gì", "là thuốc gì")),
        ("indication", ("tác dụng", "công dụng", "dùng để", "chữa bệnh gì")),
        ("administration", ("cách dùng", "uống lúc", "trước hay sau ăn", "lúc đói", "dùng cùng")),
        ("adverse_effect", ("tác dụng phụ", "phản ứng bất lợi", "dị ứng", "mẫn cảm", "phát ban", "nổi mẩn", "ngứa", "chóng mặt", "buồn nôn", "do thuốc")),
        ("interaction", ("tương tác", "dùng cùng", "uống cùng")),
        ("contraindication", ("chống chỉ định", "không được dùng")),
        ("missed_dose", ("quên uống", "quên liều", "uống bù", "quá giờ")),
        ("storage", ("bảo quản", "cất thuốc")),
    )
    for topic, markers in groups:
        if any(marker in normalized for marker in markers):
            topics.append(topic)
    return topics


def _deterministic_indirect_analysis(normalized: str) -> dict | None:
    topics = _deterministic_topics(normalized)
    symptoms = [marker for marker in ("đau bụng", "buồn nôn", "chóng mặt", "tiêu chảy", "nổi mẩn") if marker in normalized]
    time_match = re.search(r"\b([01]?\d|2[0-3])\s*(?::|h|giờ)\s*([0-5]\d)?\b", normalized)
    reference = _fallback_indirect_reference(normalized)
    if time_match and topics:
        reference = {"reference_type": "schedule_time", "schedule_time": f"{int(time_match.group(1)):02d}:{int(time_match.group(2) or 0):02d}"}
    if ("sau ăn" in normalized or "sau bữa" in normalized) and "trước hay sau" not in normalized:
        reference = {"reference_type": "meal_relation", "meal_relation": "AFTER_MEAL"}
    elif "trước ăn" in normalized or "trước bữa" in normalized:
        reference = {"reference_type": "meal_relation", "meal_relation": "BEFORE_MEAL"}
    ordinal = re.search(r"(?:thuốc|viên)\s+thứ\s+(\d+|hai|ba)", normalized)
    if ordinal:
        raw = ordinal.group(1)
        reference = {"reference_type": "prescription_ordinal", "prescription_ordinal": {"hai": 2, "ba": 3}.get(raw, int(raw) if raw.isdigit() else 1)}
    if reference and topics:
        return {"intent": "ask_prescribed_drug_info", "topics": topics, **reference, "symptoms": symptoms, "confidence": 1.0, "parser": "deterministic"}
    if topics and any(marker in normalized for marker in ("viên màu", "thuốc màu", "viên tròn", "viên dài")):
        return {"intent": "ask_prescribed_drug_info", "topics": topics, "reference_type": "none", "needs_clarification": True, "confidence": 1.0, "parser": "deterministic"}
    return None


async def classify_intent_node(state: AgentState) -> dict:
    text = _last_human_text(state)
    normalized = " ".join(text.casefold().split())
    # This module historically contains UTF-8 text that was accidentally
    # persisted as Latin-1 mojibake (e.g. ``lịch`` -> ``lÃ¬ch``).  Keep the
    # semantic parser on the real user text, but normalize the deterministic
    # compatibility layer to the same representation as its legacy markers.
    try:
        normalized = normalized.encode("utf-8").decode("latin-1")
    except UnicodeError:
        pass

    # Primary path: let the semantic LLM classify the complete message and
    # nearby conversation context. Keyword rules below are compatibility
    # fallbacks only and must never override a successful LLM parse.
    try:
        llm = get_llm(temperature=0).with_structured_output(IntentClassification)
        result = await llm.ainvoke(
            [
                {"role": "system", "content": _CLEAN_CLASSIFY_PROMPT},
                {"role": "user", "content": (
                    "Phân tích mục đích của TIN NHẮN CUỐI dựa trên ngữ cảnh gần nhất. "
                    "Không trả lời nội dung.\n" + _recent_conversation(state)
                )},
            ]
        )
        intent = _semantic_consistency_override(text, result)
        return {"intent": intent, "intent_analysis": result.model_dump()}
    except Exception:
        # Continue to the deterministic compatibility fallback below.
        pass
    requires_semantic_analysis = _fallback_scheduled_drug_intent(normalized) or any(
        marker in normalized for marker in _INDIRECT_DRUG_REFERENCE_MARKERS
    ) or any(marker in normalized for marker in ("thuốc của tôi", "đang uống", "đang dùng"))
    has_drug_information_topic = any(marker in normalized for marker in _DRUG_INFO_MARKERS)
    deterministic_indirect = _deterministic_indirect_analysis(normalized)
    # Status questions ask which scheduled doses were taken/missed, not which
    # medicines exist in the prescription. Keep this ahead of all medication
    # list and indirect-drug branches so wording such as "bỏ qua thuốc nào"
    # cannot be mistaken for ask_my_medications.
    if any(marker in normalized for marker in _DOSE_STATUS_QUESTION_MARKERS):
        period = None
        if "sáng" in normalized:
            period = "morning"
        elif "trưa" in normalized:
            period = "noon"
        elif "chiều" in normalized or "tối" in normalized:
            period = "evening"
        return {"intent": "ask_schedule", "intent_analysis": {
            "intent": "ask_schedule", "reference_type": "dose_period" if period else "current_medications",
            "dose_period": period, "topics": ["dose_status"],
            "date_reference": "today" if "hôm nay" in normalized or "nay" in normalized else None,
            "requested_action": "view_schedule", "confidence": 1.0,
            "parser": "deterministic_status_question",
        }}
    if deterministic_indirect:
        return {"intent": "ask_prescribed_drug_info", "intent_analysis": deterministic_indirect}
    asks_to_explain_prescription = (
        any(marker in normalized for marker in ("giải thích", "cách dùng", "dùng như thế nào"))
        and any(marker in normalized for marker in ("thuốc của tôi", "các thuốc", "thuốc trong đơn", "đơn thuốc"))
    )
    if asks_to_explain_prescription:
        return {"intent": "explain_my_medications", "intent_analysis": {
            "intent": "explain_my_medications", "reference_type": "current_medications",
            "topics": ["administration"], "confidence": 1.0, "parser": "deterministic",
        }}
    if any(phrase in normalized for phrase in _EXPLAIN_MY_MEDICATION_PHRASES) and not has_drug_information_topic:
        return {"intent": "explain_my_medications", "intent_analysis": {"intent": "explain_my_medications", "reference_type": "current_medications", "topics": ["administration"]}}
    if any(phrase in normalized for phrase in _NEXT_DOSE_PHRASES) and not has_drug_information_topic:
        return {"intent": "ask_next_dose", "intent_analysis": {"intent": "ask_next_dose", "reference_type": "next_dose", "topics": ["schedule"]}}
    if any(phrase in normalized for phrase in _TODAY_SCHEDULE_PHRASES):
        return {"intent": "ask_schedule", "intent_analysis": {"intent": "ask_schedule", "reference_type": "current_medications", "topics": ["schedule"]}}
    if "ăn" in normalized and any(marker in normalized for marker in ("muộn hơn", "sớm hơn", "trễ hơn")):
        return {"intent": "report_meal_shift", "intent_analysis": {"intent": "report_meal_shift", "reference_type": "none", "topics": ["schedule"]}}
    asks_about_own_current_medicines = (
        "thuốc" in normalized
        and "tôi" in normalized
        and any(
            marker in normalized
            for marker in (
                "đang uống", "đang dùng", "hiện tại", "danh sách", "bác sĩ",
                "thuốc của tôi",
            )
        )
    )
    if (asks_about_own_current_medicines or any(
        phrase in normalized for phrase in _MY_MEDICATION_PHRASES
    )) and not has_drug_information_topic:
        return {"intent": "ask_my_medications"}
    # Route formulary-shaped questions to SafeDrugRAG without depending on an
    # LLM classifier. Its input guard resolves the exact drug name or asks the
    # user to provide one; it never performs an unscoped retrieval.
    if not requires_semantic_analysis and any(marker in normalized for marker in _DRUG_INFO_MARKERS):
        topics = _deterministic_topics(normalized)
        drug_name = normalized
        for marker in sorted(_DRUG_INFO_MARKERS, key=len, reverse=True):
            drug_name = drug_name.replace(marker, " ")
        drug_name = re.sub(r"\b(?:thuốc|tôi|đang|dùng|bị|thì|phải|làm|sao|không|ko)\b", " ", drug_name)
        drug_name = " ".join(drug_name.split()).strip(" ?.,").title() or None
        return {"intent": "ask_drug_info", "intent_analysis": {
            "intent": "ask_drug_info", "reference_type": "drug_name",
            "drug_name": drug_name, "topics": topics,
        }}
    try:
        llm = get_llm(temperature=0).with_structured_output(IntentClassification)
        result = await llm.ainvoke(
            [
                {"role": "system", "content": _CLEAN_CLASSIFY_PROMPT},
                {"role": "user", "content": (
                    "Phân tích mục đích của TIN NHẮN CUỐI dựa trên ngữ cảnh gần nhất. "
                    "Không trả lời nội dung.\n" + _recent_conversation(state)
                )},
            ]
        )
        intent = _semantic_consistency_override(text, result)
        return {"intent": intent, "intent_analysis": result.model_dump()}
    except Exception:  # noqa: BLE001 — lỗi phân loại -> "general", để agent_node xử lý an toàn
        if _fallback_scheduled_drug_intent(normalized):
            return {
                "intent": "ask_scheduled_drug_info",
                "intent_analysis": {
                    "intent": "ask_scheduled_drug_info",
                    "reference_type": "schedule_time",
                    "confidence": 0.0,
                    "parser": "deterministic_fallback",
                },
            }
        fallback_reference = _fallback_indirect_reference(normalized)
        if fallback_reference:
            return {
                "intent": "ask_prescribed_drug_info",
                "intent_analysis": {
                    "intent": "ask_prescribed_drug_info", "topics": ["identity"],
                    **fallback_reference, "confidence": 0.0,
                    "parser": "deterministic_fallback",
                },
            }
        return {"intent": "general", "intent_analysis": {"parser": "failed"}}
