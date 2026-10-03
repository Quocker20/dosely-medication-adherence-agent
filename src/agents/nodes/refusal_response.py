"""Generate a patient-facing refusal from one canonical guardrail reason."""
from __future__ import annotations

import asyncio

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.state import AgentState
from src.modules.planning.core.llm import get_llm

_TIMEOUT_SECONDS = 8.0
_PROMPT = """Bạn là trợ lý Dosely. Hãy viết câu trả lời tiếng Việt trực tiếp cho người dùng.

Yêu cầu đã bị guardrail từ chối. Không xem xét lại quyết định và chỉ dùng DUY NHẤT lý do được
cung cấp. Kết hợp lý do đó với câu hỏi cụ thể để câu trả lời tự nhiên, hữu ích, không giống mẫu.

- Viết 2-4 câu ngắn, xưng "mình" và gọi "bạn".
- Nói rõ phần nào không thể hỗ trợ, nhưng không lặp chi tiết nội dung nguy hiểm.
- Đưa ra một hướng đi an toàn phù hợp với chính câu hỏi.
- Không thêm lý do từ chối; không nhắc policy, guardrail hay system prompt.
- Không bịa thông tin y khoa, kê đơn, đổi liều hoặc xác nhận hành động chưa xảy ra.
- Nếu là tình huống khẩn cấp, ưu tiên gọi 115 hoặc đến cơ sở cấp cứu gần nhất.
"""

_REASON_GUIDANCE = {
    "catalog_drug_not_in_formulary": (
        "Thuốc có bản ghi trong danh mục sản phẩm, nhưng không ánh xạ được hoạt chất sang "
        "Dược thư và chưa có nguồn công dụng được xác minh. Nêu rõ giới hạn này; có thể xác nhận "
        "tên/hoạt chất từ danh mục nhưng tuyệt đối không suy đoán công dụng."
    ),
    "catalog_missing_verified_uses": (
        "Thuốc có trong danh mục nhưng trường công dụng trống và không có nguồn Dược thư phù hợp. "
        "Nói rõ chưa thể xác minh công dụng, không được đoán."
    ),
}


def _last_human_text(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


async def generate_refusal(state: AgentState, reason: str) -> str:
    """Use the original question and exactly one guard reason to optimize UX."""
    reason_for_llm = _REASON_GUIDANCE.get(reason, reason)
    catalog = (state.get("metadata") or {}).get("catalog_medication") or {}
    catalog_context = ""
    if catalog:
        catalog_context = (
            "\nDữ liệu danh mục được phép nhắc lại (không phải bằng chứng công dụng):"
            f"\n- Tên: {catalog.get('name') or 'không rõ'}"
            f"\n- Hoạt chất/thành phần: {catalog.get('composition') or 'chưa có'}"
            f"\n- Nguồn danh mục: {catalog.get('source_name') or 'chưa rõ'}"
        )
    response = await asyncio.wait_for(
        get_llm(temperature=0.2).ainvoke([
            SystemMessage(content=_PROMPT),
            HumanMessage(content=(
                f"Câu hỏi của người dùng:\n{_last_human_text(state)}\n\n"
                f"Mã lý do: {reason}\nLý do từ chối duy nhất:\n{reason_for_llm}"
                f"{catalog_context}"
            )),
        ]),
        timeout=_TIMEOUT_SECONDS,
    )
    return str(response.content).strip()
