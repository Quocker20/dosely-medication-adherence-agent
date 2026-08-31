"""Answer multi-topic questions after resolving an exact prescribed drug."""
from __future__ import annotations

import asyncio

from langchain_core.messages import AIMessage, HumanMessage

from src.agents.nodes.scheduled_drug_info_node import (
    _lookup_exact_drug,
    lookup_prescribed_drug_information,
)
from src.agents.prescribed_drug_resolver import ResolutionStatus, resolve_prescribed_drug
from src.agents.state import AgentState


def _question(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def _name(item: dict) -> str:
    return str(item.get("medication_name") or item.get("display_name") or "").strip()


def _clarification(items: list[dict]) -> str:
    names = list(dict.fromkeys(_name(item) or "thuốc chưa rõ tên" for item in items))
    return "Mình tìm thấy nhiều thuốc phù hợp: " + ", ".join(names) + ". Bạn muốn hỏi thuốc nào?"


async def prescribed_drug_info_node(state: AgentState) -> dict:
    result = await resolve_prescribed_drug(state)
    if result.status == ResolutionStatus.BACKEND_UNAVAILABLE:
        text = "Mình chưa thể kết nối dữ liệu đơn/lịch thuốc nên không thể xác định đúng thuốc. Vui lòng kiểm tra trên App hoặc thử lại sau."
        return {"messages": [AIMessage(content=text)]}
    if result.status == ResolutionStatus.INACTIVE_PRESCRIPTION:
        return {"messages": [AIMessage(content="Bạn không có đơn thuốc đã duyệt còn hiệu lực; mình sẽ không đoán thuốc.")]}
    if result.status == ResolutionStatus.CONTEXT_EXPIRED:
        return {"messages": [AIMessage(content="Mình chưa xác định được ‘thuốc này’ là thuốc nào. Bạn hãy cho biết tên, giờ hoặc cữ thuốc hiển thị trên App.")]}
    if result.status == ResolutionStatus.INSUFFICIENT_REFERENCE:
        return {"messages": [AIMessage(content="Mình chưa đủ dữ kiện để xác định thuốc. Bạn hãy cho biết tên, giờ/cữ, buổi uống hoặc vị trí thuốc trong đơn.")]}
    if result.status == ResolutionStatus.NOT_FOUND:
        return {"messages": [AIMessage(content="Không tìm thấy thuốc khớp với mô tả trong đơn/lịch của bạn. Mình sẽ không tra cứu rộng hoặc đoán tên thuốc.")]}
    if result.status == ResolutionStatus.RESOLVED_MULTIPLE:
        if result.reference_type == "recent_context":
            medication_name = _name(result.medications[0]) if result.medications else "thuốc này"
            times = [
                str(item.get("current_scheduled_at") or item.get("scheduled_at") or "").strip()
                for item in result.medications
                if item.get("current_scheduled_at") or item.get("scheduled_at")
            ]
            if times:
                return {"messages": [AIMessage(content=(
                    f"Mình đã đối chiếu {medication_name} với lịch thuốc của bạn. "
                    "Các thời điểm cần dùng là:\n" + "\n".join(f"- {time}" for time in times)
                ))], "metadata": {"resolved_medication": {
                    "display_name": medication_name,
                    "resolved_from": "recent_context",
                }}}
        return {"messages": [AIMessage(content=_clarification(result.medications))]}

    medication = result.medications[0]
    name = _name(medication)
    if not name:
        return {"messages": [AIMessage(content="Cữ thuốc đã tìm thấy chưa có tên rõ ràng nên mình không thể tra cứu an toàn.")]}

    analysis = state.get("intent_analysis") or {}
    topics = list(analysis.get("topics") or ["identity"])
    lines = [f"## {name}", "", "**Thông tin xác định từ đơn/lịch của bạn**"]
    if medication.get("current_scheduled_at"):
        lines.append(f"- Thời điểm trong lịch: {medication['current_scheduled_at']}")
    if medication.get("status"):
        lines.append(f"- Trạng thái: {medication['status']}")
    if medication.get("instructions"):
        lines.append(f"- Dặn dò của bác sĩ: {medication['instructions']}")

    try:
        information, grounded = await asyncio.to_thread(_lookup_exact_drug, name, _question(state))
        if not grounded and medication.get("medication_id"):
            information, grounded = await lookup_prescribed_drug_information(medication, _question(state))
    except Exception:
        information, grounded = "Hiện không thể kết nối tới Dược Thư.", False
    lines.extend(["", "**Thông tin thuốc theo nội dung bạn hỏi**", information])

    if "missed_dose" in topics:
        lines.extend([
            "", "**Nếu đã quên hoặc quá giờ**",
            "Mình không thể kết luận bạn nên uống bù chỉ dựa vào thời gian đã trôi qua. Không uống gấp đôi, không tự bỏ hoặc đổi cữ; hãy làm theo hướng dẫn quên liều đã được xác minh cho đúng thuốc hoặc liên hệ bác sĩ/dược sĩ.",
        ])
    if analysis.get("symptoms"):
        lines.extend([
            "", "**Về triệu chứng bạn mô tả**",
            "Không thể khẳng định triệu chứng do thuốc chỉ qua chat. Nếu triệu chứng nặng, tăng nhanh, khó thở, choáng hoặc sưng môi/lưỡi, hãy liên hệ cấp cứu ngay.",
        ])

    metadata = {"resolved_medication": {
        "display_name": name,
        "medication_id": str(medication.get("medication_id") or ""),
        "resolved_from": result.reference_type,
        "resolved_value": result.reference_value,
    }}
    return {
        "messages": [AIMessage(content="\n".join(lines))],
        "grounding_valid": grounded,
        "grounding_errors": [] if grounded else ["drug_information_unavailable"],
        "metadata": metadata,
    }
