"""Deterministic database branch for the authenticated patient's medicines."""

from __future__ import annotations

from langchain_core.messages import AIMessage

from src.agents.state import AgentState
from src.modules.planning.core.backend_client import BackendAPIError, get


async def current_medications_node(state: AgentState) -> dict:
    """Read current medicines from PostgreSQL through the authenticated API."""
    try:
        result = await get("/patients/me/medications/current")
    except BackendAPIError:
        reply = "Mình chưa thể lấy danh sách thuốc của bạn lúc này. Vui lòng thử lại sau."
        return {"messages": [AIMessage(content=reply)]}

    medications = (result or {}).get("medications", [])
    as_of = (result or {}).get("as_of", "hôm nay")
    if not medications:
        reply = (
            f"Mình không thấy thuốc nào trong đơn đã duyệt còn hiệu lực vào {as_of}. "
            "Nếu bạn đang tự dùng thuốc hoặc thực phẩm bổ sung, hãy cập nhật với bác sĩ/dược sĩ."
        )
        return {"messages": [AIMessage(content=reply)]}

    lines = [f"Theo đơn thuốc đã duyệt còn hiệu lực vào {as_of}, bạn đang dùng:"]
    for med in medications:
        doses = []
        for label, field in (
            ("sáng", "morning_dose"),
            ("trưa", "noon_dose"),
            ("tối", "evening_dose"),
            ("trước ngủ", "bedtime_dose"),
        ):
            value = med.get(field)
            if value is not None and float(value) > 0:
                doses.append(f"{label} {value} {med.get('dose_unit', '')}".strip())
        detail = ", ".join(doses) if doses else "chưa có liều theo buổi"
        if med.get("instructions"):
            detail += f"; {med['instructions']}"
        lines.append(f"- {med.get('display_name', 'Thuốc chưa rõ tên')}: {detail}")
    lines.append("Danh sách này không bao gồm thuốc hoặc thực phẩm bổ sung chưa được ghi trong đơn.")
    return {"messages": [AIMessage(content="\n".join(lines))]}
