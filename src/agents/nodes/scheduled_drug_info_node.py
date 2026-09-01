"""Resolve a medication from the authenticated patient's schedule before RAG."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.messages import AIMessage, HumanMessage

from src.agents.medication_mapping import resolve_catalog_medication
from src.agents.patient_presentation import patient_facing_text
from src.agents.state import AgentState
from src.modules.planning.core.backend_client import BackendAPIError, get
from src.rag_retrieval import SafeDrugRAG
from src.rag_retrieval.service import DrugRAG

_TIME = re.compile(r"\b(?P<hour>[01]?\d|2[0-3])\s*(?::|h)\s*(?P<minute>[0-5]\d)?\b", re.IGNORECASE)
_MEAL = {
    "BEFORE_MEAL": "trước bữa ăn",
    "AFTER_MEAL": "sau bữa ăn",
    "WITH_MEAL": "cùng bữa ăn",
}


@lru_cache(maxsize=1)
def _rag() -> SafeDrugRAG:
    return SafeDrugRAG()


@lru_cache(maxsize=1)
def _identity_rag() -> DrugRAG:
    return DrugRAG(client=object())  # type: ignore[arg-type]


def _question(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def _requested_time(text: str) -> tuple[int, int] | None:
    match = _TIME.search(text)
    if not match:
        return None
    return int(match.group("hour")), int(match.group("minute") or 0)


def _local_hour_minute(value: object, timezone_name: str | None) -> tuple[int, int] | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if timezone_name and parsed.tzinfo is not None:
            parsed = parsed.astimezone(ZoneInfo(timezone_name))
        return parsed.hour, parsed.minute
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        return None


def _lookup_exact_drug(display_name: str, question: str) -> tuple[str, bool]:
    rag = _rag()
    normalized, canonical = rag.rag.infer_drug(display_name)
    if not normalized or not canonical:
        return "Không tìm thấy thông tin Dược Thư khớp chính xác với tên thuốc này.", False
    result = rag.query(
        f"{canonical}. {question} Trình bày công dụng, cách dùng liên quan bữa ăn và phản ứng bất lợi có liên quan; "
        "không kết luận nguyên nhân triệu chứng và không đề xuất thay đổi điều trị.",
        context_drug=(normalized, canonical),
    )
    if result.status != "answered" or not result.grounding_valid:
        return "Không tìm thấy thông tin Dược Thư phù hợp cho thuốc này.", False
    return patient_facing_text(result.answer).strip(), True


async def lookup_prescribed_drug_information(medication: dict, question: str) -> tuple[str, bool]:
    """Resolve a catalog brand to its composition before consulting the formulary."""
    display_name = str(medication.get("medication_name") or medication.get("display_name") or "").strip()
    medication_id = str(medication.get("medication_id") or "").strip()
    catalog: dict = {}
    if medication_id:
        try:
            catalog = await get(f"/medications/{medication_id}") or {}
        except BackendAPIError:
            catalog = {}
    composition = str(catalog.get("composition") or "").strip()
    lookup_name = display_name
    if composition:
        identities = resolve_catalog_medication(display_name, composition, _identity_rag())
        # A single active ingredient can safely bridge many commercial names
        # to one reviewed formulary heading. Combination products retain the
        # full composition so we do not silently answer for only one component.
        lookup_name = identities[0].formulary_name if len(identities) == 1 else composition
    information, grounded = await asyncio.to_thread(_lookup_exact_drug, lookup_name, question)
    if grounded:
        return information, True
    if catalog:
        lines = [f"Thông tin từ danh mục thuốc về {display_name}"]
        if composition:
            lines.append(f"- Hoạt chất/thành phần: {composition}")
        if catalog.get("uses"):
            lines.append(f"- Công dụng: {catalog['uses']}")
        if catalog.get("side_effects"):
            lines.append(f"- Tác dụng phụ: {catalog['side_effects']}")
        lines.append(f"- Nguồn danh mục: {catalog.get('source_name') or 'chưa rõ'}")
        lines.append("Dược thư chưa có chuyên luận khớp; không tự suy diễn thêm ngoài dữ liệu danh mục.")
        return "\n".join(lines), True
    return information, False


async def scheduled_drug_info_node(state: AgentState) -> dict:
    patient_id = state.get("patient_id")
    client_date = state.get("client_date")
    requested = _requested_time(_question(state))
    if not patient_id:
        return {"messages": [AIMessage(content="Không xác định được tài khoản bệnh nhân.")]}
    if requested is None:
        return {"messages": [AIMessage(content="Bạn vui lòng cho biết giờ của cữ thuốc cần tra cứu.")]}
    try:
        schedule = await get(
            f"/patients/{patient_id}/schedules",
            params={"date": client_date} if client_date else None,
        )
    except BackendAPIError:
        return {
            "messages": [
                AIMessage(
                    content=(
                        "Mình chưa thể kết nối tới dữ liệu lịch thuốc lúc này nên chưa xác định được đúng thuốc cần tra cứu. "
                        "Vui lòng thử lại sau hoặc kiểm tra trực tiếp trên App."
                    )
                )
            ]
        }

    timezone_name = (schedule or {}).get("timezone")
    matches = [
        dose
        for dose in (schedule or {}).get("doses", [])
        if _local_hour_minute(dose.get("current_scheduled_at"), timezone_name) == requested
    ]
    rendered_time = f"{requested[0]:02d}:{requested[1]:02d}"
    if not matches:
        return {
            "messages": [
                AIMessage(
                    content=(
                        f"Không tìm thấy cữ thuốc lúc {rendered_time} trong lịch ngày {(schedule or {}).get('date', client_date or 'hôm nay')}. "
                        "Bạn hãy kiểm tra lại giờ hiển thị trên App."
                    )
                )
            ]
        }
    if len(matches) > 1:
        names = ", ".join(dict.fromkeys(str(d.get("medication_name") or "thuốc chưa rõ tên") for d in matches))
        return {
            "messages": [
                AIMessage(
                    content=(
                        f"Lúc {rendered_time} có nhiều thuốc: {names}. Bạn muốn hỏi tác dụng hoặc cách dùng của thuốc nào?"
                    )
                )
            ]
        }

    dose = matches[0]
    name = str(dose.get("medication_name") or "").strip()
    if not name:
        return {
            "messages": [
                AIMessage(
                    content=(
                        f"Cữ {rendered_time} chưa có tên thuốc rõ ràng nên mình sẽ không tra cứu rộng hoặc đoán thuốc."
                    )
                )
            ]
        }
    relation = _MEAL.get(str(dose.get("meal_relation") or "").upper())
    prescription_line = (
        f"Chỉ dẫn trong lịch: dùng {relation}."
        if relation
        else "Chỉ dẫn trong lịch chưa ghi rõ dùng trước, sau hay cùng bữa ăn."
    )
    try:
        information, grounded = await lookup_prescribed_drug_information(dose, _question(state))
    except Exception:
        information, grounded = "Hiện không thể kết nối tới Dược Thư.", False

    answer = (
        f"Thuốc ở cữ {rendered_time}\n{name}\n\n"
        f"Thông tin từ đơn/lịch của bạn\n- {prescription_line}\n\n"
        f"Thông tin về thuốc\n{information}\n\n"
        "Đánh giá triệu chứng\n"
        "- Mình không thể khẳng định đau bụng là do thuốc chỉ từ cuộc trò chuyện này. Không tự đổi giờ, bỏ liều hoặc uống bù. "
        "Nếu đau nhiều, kéo dài, nôn liên tục, đi ngoài ra máu, khó thở hoặc choáng, hãy liên hệ cơ sở y tế ngay."
    )
    return {
        "messages": [AIMessage(content=answer)],
        "grounding_valid": grounded,
        "grounding_errors": [] if grounded else ["drug_information_unavailable"],
        "metadata": {
            "resolved_medication": {
                "display_name": name,
                "medication_id": str(dose.get("medication_id") or ""),
                "resolved_from": "schedule_time",
                "resolved_value": rendered_time,
            }
        },
    }
