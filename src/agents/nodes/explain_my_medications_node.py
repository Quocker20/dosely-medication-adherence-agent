"""Patient instructions from the prescription, supplemented by drug-scoped RAG."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from functools import lru_cache
from typing import Any

from langchain_core.messages import AIMessage

from src.agents.nodes.next_dose_node import format_dose_value
from src.agents.patient_presentation import patient_facing_text
from src.agents.prescription_consistency import validate_prescription_schedule
from src.agents.state import AgentState
from src.modules.planning.core.backend_client import BackendAPIError, get
from src.rag_retrieval import SafeDrugRAG

_MEAL_RELATION_TEXT = {
    "BEFORE_MEAL": "Trước bữa ăn",
    "AFTER_MEAL": "Sau bữa ăn",
    "WITH_MEAL": "Dùng cùng bữa ăn",
}
_ROUTE_TEXT = {
    "ORAL": "Đường uống",
    "TOPICAL": "Dùng ngoài da",
    "INHALATION": "Đường hít",
    "INJECTION": "Đường tiêm",
    "SUBLINGUAL": "Ngậm dưới lưỡi",
    "RECTAL": "Đường trực tràng",
    "VAGINAL": "Đường âm đạo",
}


@lru_cache(maxsize=1)
def _get_rag_service() -> SafeDrugRAG:
    return SafeDrugRAG()


def _regimen(item: dict[str, Any]) -> str:
    doses = []
    for label, field in (
        ("Sáng", "morning_dose"),
        ("Trưa", "noon_dose"),
        ("Tối", "evening_dose"),
        ("Trước khi ngủ", "bedtime_dose"),
    ):
        rendered = format_dose_value(item.get(field))
        try:
            positive = rendered != "" and float(rendered) > 0
        except ValueError:
            positive = False
        if positive:
            doses.append(f"{label}: {rendered} {item.get('dose_unit', '')}".strip())

    parts = [", ".join(doses) if doses else "Đơn chưa ghi liều theo buổi"]
    if item.get("route"):
        route = str(item["route"]).upper()
        parts.append(f"Đường dùng: {_ROUTE_TEXT.get(route, str(item['route']))}")
    else:
        parts.append("Đường dùng: Đơn chưa ghi")
    if item.get("meal_relation"):
        relation = str(item["meal_relation"]).upper()
        parts.append(f"Liên quan bữa ăn: {_MEAL_RELATION_TEXT.get(relation, 'Chưa xác định rõ')}")
    else:
        parts.append("Liên quan bữa ăn: Đơn chưa ghi")
    if item.get("instructions"):
        parts.append(f"Dặn dò của bác sĩ: {item['instructions']}")
    else:
        parts.append("Dặn dò bổ sung: Đơn chưa ghi")
    if item.get("minimum_interval_minutes") is not None:
        parts.append(f"Khoảng cách tối thiểu theo đơn: {item['minimum_interval_minutes']} phút")
    return "; ".join(parts)


def _without_citations(answer: str) -> str:
    """Compatibility wrapper; presentation policy lives in one shared module."""
    return " ".join(
        line.removeprefix("- ").removeprefix("• ").strip()
        for line in patient_facing_text(answer).splitlines()
        if line.strip()
    )


def _explain_one(display_name: str) -> tuple[str, str]:
    """Resolve one exact drug; RAG may add general warnings, never a personal regimen."""
    rag = _get_rag_service()
    normalized, canonical_name = rag.rag.infer_drug(display_name)
    if not normalized or not canonical_name:
        return "NO_DATA", "Không tìm thấy chuyên luận Dược Thư khớp chính xác với tên thuốc này."
    result = rag.query(
        f"{canonical_name} có những lưu ý an toàn chung nào khi sử dụng? Không đề xuất liều dùng cá nhân.",
        context_drug=(normalized, canonical_name),
    )
    if result.status != "answered" or not result.grounding_valid:
        return "NO_DATA", "Không tìm thấy thông tin Dược Thư phù hợp cho thuốc này."
    explanation = _without_citations(result.answer)
    return (
        ("ANSWERED", explanation)
        if explanation
        else ("NO_DATA", "Không tìm thấy thông tin Dược Thư phù hợp cho thuốc này.")
    )


async def explain_my_medications_node(state: AgentState) -> dict:
    address = state.get("patient_address", "bạn")
    addressed = address.capitalize()
    """Explain only the authenticated patient's date-active prescription."""
    client_date = state.get("client_date")
    try:
        if client_date:
            result = await get("/patients/me/medications/current", params={"as_of": client_date})
        else:
            result = await get("/patients/me/medications/current")
    except BackendAPIError:
        return {
            "messages": [
                AIMessage(
                    content=(
                        f"Mình chưa thể kết nối tới dữ liệu đơn thuốc của {address} lúc này. "
                        "Vui lòng kiểm tra trực tiếp đơn thuốc hoặc hỏi bác sĩ/dược sĩ."
                    )
                )
            ]
        }

    medications = (result or {}).get("medications", [])
    as_of = (result or {}).get("as_of", client_date or "hôm nay")
    if not medications:
        return {
            "messages": [
                AIMessage(
                    content=(
                        f"{addressed} không có đơn thuốc đã duyệt còn hiệu lực vào {as_of}. "
                        "Mình sẽ không suy đoán cách dùng thuốc khi không có đơn hợp lệ."
                    )
                )
            ]
        }

    patient_id = state.get("patient_id")
    if not patient_id:
        return {
            "messages": [
                AIMessage(
                    content=(
                        "Mình không xác định được tài khoản bệnh nhân nên không thể kiểm tra cách dùng thuốc an toàn."
                    )
                )
            ]
        }
    try:
        schedule = await get(f"/patients/{patient_id}/schedules", params={"date": str(as_of)})
    except BackendAPIError:
        return {
            "messages": [
                AIMessage(
                    content=(
                        "Mình đã đọc được đơn thuốc nhưng chưa thể đối chiếu với lịch uống thuốc. "
                        "Để tránh hướng dẫn sai, mình chưa hiển thị cách dùng; vui lòng kiểm tra trên nhãn thuốc "
                        "hoặc xác nhận với bác sĩ/dược sĩ."
                    )
                )
            ]
        }

    issues = validate_prescription_schedule(medications, (schedule or {}).get("doses", []))
    if issues:
        lines = [
            "Mình phát hiện dữ liệu đơn thuốc và lịch uống chưa đủ nhất quán nên chưa thể hướng dẫn cách dùng an toàn:"
        ]
        lines.extend(f"- {issue}" for issue in issues)
        lines.append("Vui lòng xác nhận lại với bác sĩ/dược sĩ trước khi dùng thuốc.")
        return {"messages": [AIMessage(content="\n".join(lines))]}

    grouped: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for item in medications:
        key = str(item.get("medication_id") or item.get("display_name") or "unknown")
        grouped.setdefault(key, []).append(item)

    sections = [f"Cách dùng cá nhân dưới đây được đọc nguyên từ đơn đã duyệt còn hiệu lực vào {as_of}:"]
    for index, items in enumerate(grouped.values(), start=1):
        display_name = str(items[0].get("display_name") or "Thuốc chưa rõ tên")
        try:
            rag_status, explanation = await asyncio.to_thread(_explain_one, display_name)
        except Exception:
            rag_status, explanation = "UNAVAILABLE", "Hiện không thể kết nối tới Dược Thư."

        block = [f"{index}. {display_name}"]
        for regimen_index, item in enumerate(items, start=1):
            suffix = "" if len(items) == 1 else f" #{regimen_index}"
            block.append(f"   Chỉ dẫn cá nhân từ đơn đã duyệt{suffix}: {_regimen(item)}")
        if rag_status == "ANSWERED":
            block.append("   Lưu ý chung từ Dược Thư, không thay thế chỉ dẫn trong đơn: " + explanation)
        else:
            block.append("   Thông tin Dược Thư: " + explanation)
        sections.append("\n".join(block))

    sections.append(
        f"Nếu tên thuốc, liều, đơn vị, thời điểm hoặc dặn dò trên đây khác nhãn thuốc {address} đang cầm, "
        "không tự chọn một trong hai; hãy xác nhận lại với bác sĩ/dược sĩ trước khi dùng."
    )
    return {"messages": [AIMessage(content="\n\n".join(sections))]}
