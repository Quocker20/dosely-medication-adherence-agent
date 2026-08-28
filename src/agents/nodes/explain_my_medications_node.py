"""Hybrid patient-prescription + strictly drug-scoped Dược Thư explanation."""

from __future__ import annotations

import asyncio
import re
from collections import OrderedDict
from functools import lru_cache
from typing import Any

from langchain_core.messages import AIMessage

from src.agents.state import AgentState
from src.modules.planning.core.backend_client import BackendAPIError, get
from src.rag_retrieval import SafeDrugRAG

_CITATION = re.compile(r"\s*\[Nguồn\s+\d+\]")


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
        value = item.get(field)
        if value is not None and float(value) > 0:
            doses.append(f"{label}: {value} {item.get('dose_unit', '')}".strip())
    parts = [", ".join(doses) if doses else "Chưa có liều theo buổi"]
    if item.get("meal_relation"):
        parts.append(f"Liên quan bữa ăn: {item['meal_relation']}")
    if item.get("instructions"):
        parts.append(f"Dặn dò: {item['instructions']}")
    return "; ".join(parts)


def _without_citations(answer: str) -> str:
    lines = []
    for raw_line in answer.splitlines():
        cleaned = _CITATION.sub("", raw_line).strip()
        cleaned = re.sub(r"^[-•]\s*", "", cleaned)
        if cleaned:
            lines.append(cleaned)
    return " ".join(lines)


def _explain_one(display_name: str) -> tuple[str, str]:
    """Resolve the exact drug first; never perform an unfiltered RAG search."""
    rag = _get_rag_service()
    normalized, canonical_name = rag.rag.infer_drug(display_name)
    if not normalized or not canonical_name:
        return (
            "NO_DATA",
            "Không tìm thấy chuyên luận Dược Thư khớp chính xác với tên thuốc này.",
        )
    result = rag.query(
        f"{canonical_name} có cách dùng và lưu ý khi sử dụng như thế nào?",
        context_drug=(normalized, canonical_name),
    )
    if result.status != "answered" or not result.grounding_valid:
        return (
            "NO_DATA",
            "Không tìm thấy thông tin Dược Thư phù hợp cho thuốc này.",
        )
    explanation = _without_citations(result.answer)
    if not explanation:
        return "NO_DATA", "Không tìm thấy thông tin Dược Thư phù hợp cho thuốc này."
    return "ANSWERED", explanation


async def explain_my_medications_node(state: AgentState) -> dict:
    """Explain only medicines belonging to the authenticated caller's active prescriptions."""
    try:
        result = await get("/patients/me/medications/current")
    except BackendAPIError:
        return {
            "messages": [
                AIMessage(
                    content=(
                        "Mình chưa thể kết nối tới dữ liệu đơn thuốc của bạn lúc này. "
                        "Vui lòng thử lại sau."
                    )
                )
            ]
        }

    medications = (result or {}).get("medications", [])
    if not medications:
        as_of = (result or {}).get("as_of", "hôm nay")
        return {
            "messages": [
                AIMessage(
                    content=f"Bạn không có đơn thuốc đã duyệt còn hiệu lực vào {as_of}."
                )
            ]
        }

    grouped: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for item in medications:
        key = str(item.get("medication_id") or item.get("display_name") or "unknown")
        grouped.setdefault(key, []).append(item)

    sections = ["Các thuốc trong đơn đang còn hiệu lực của bạn:"]
    for index, items in enumerate(grouped.values(), start=1):
        display_name = str(items[0].get("display_name") or "Thuốc chưa rõ tên")
        try:
            rag_status, explanation = await asyncio.to_thread(_explain_one, display_name)
        except Exception:  # external embedding/model service unavailable
            rag_status = "UNAVAILABLE"
            explanation = "Hiện không thể kết nối tới Dược Thư để tra cứu thuốc này."

        block = [f"{index}. {display_name}"]
        for regimen_index, item in enumerate(items, start=1):
            label = "Theo đơn của bạn" if len(items) == 1 else f"Theo đơn của bạn #{regimen_index}"
            block.append(f"   {label}: {_regimen(item)}")
        if rag_status == "ANSWERED":
            block.append(f"   Thông tin tham khảo: {explanation}")
        else:
            block.append(f"   Thông tin Dược Thư: {explanation}")
        sections.append("\n".join(block))

    sections.append("Không tự thay đổi liều hoặc ngừng thuốc nếu chưa trao đổi với bác sĩ/dược sĩ.")
    return {"messages": [AIMessage(content="\n\n".join(sections))]}
