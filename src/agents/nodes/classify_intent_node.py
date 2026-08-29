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

_DRUG_INFO_MARKERS = (
    "tác dụng", "công dụng", "chỉ định", "chống chỉ định", "tác dụng phụ",
    "phản ứng bất lợi", "tương tác", "cách dùng", "đường dùng", "bảo quản",
    "quên liều", "mang thai", "thai kỳ", "cho con bú", "used for",
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


def _validated_intent(analysis: IntentClassification) -> str:
    """Reject a schedule route when time is only a reference to a drug."""
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
        ("adverse_effect", ("tác dụng phụ", "phản ứng bất lợi", "chóng mặt", "buồn nôn", "do thuốc")),
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
    requires_semantic_analysis = _fallback_scheduled_drug_intent(normalized) or any(
        marker in normalized for marker in _INDIRECT_DRUG_REFERENCE_MARKERS
    ) or any(marker in normalized for marker in ("thuốc của tôi", "đang uống", "đang dùng"))
    has_drug_information_topic = any(marker in normalized for marker in _DRUG_INFO_MARKERS)
    deterministic_indirect = _deterministic_indirect_analysis(normalized)
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
        drug_name = normalized.split(" có ", 1)[0].strip().title() if " có " in normalized else None
        return {"intent": "ask_drug_info", "intent_analysis": {
            "intent": "ask_drug_info", "reference_type": "drug_name",
            "drug_name": drug_name, "topics": topics,
        }}
    try:
        llm = get_llm(temperature=0).with_structured_output(IntentClassification)
        result = await llm.ainvoke(
            [
                {"role": "system", "content": _CLASSIFY_SYSTEM_PROMPT + _INDIRECT_REFERENCE_PROMPT},
                {"role": "user", "content": text},
            ]
        )
        intent = _validated_intent(result)
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
