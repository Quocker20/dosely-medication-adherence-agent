"""generate_message_node — soạn tin nhắn nhắc uống thuốc từ 1 cữ do
compute_schedule sinh ra. Xem cong_viec.md §4.2.

Nguyên tắc bắt buộc: slot dữ liệu y tế (tên thuốc, giờ, quan hệ bữa ăn) do
CODE điền 100% qua template — LLM không bao giờ chạm vào. LLM chỉ được
sinh đúng 1 câu động viên ngắn, không số, không tên thuốc. Post-check chặn
bất kỳ câu nào lọt số hoặc tên thuốc; hỏng thì rơi về câu mặc định, không
bao giờ để trống hay lỗi lan ra ngoài (giống nguyên tắc fail-open ở
safety_tools.trigger_red_alert — một tin nhắn thiếu câu động viên vẫn tốt
hơn một tin nhắn không gửi được).

Input là 1 dose dict theo đúng output shape của
`src.agents.nodes.compute_schedule.compute_schedule` — {"drug", "time",
"meal_relation", "date"}. Tầng gọi (tầng 2) lặp qua từng cữ trong lịch mà
compute_schedule trả về và gọi hàm này cho từng cữ.
"""
from __future__ import annotations

import asyncio
import re

from src.modules.planning.core.llm import get_llm

_MEAL_RELATION_TEXT = {
    "before_meal": "trước bữa ăn",
    "after_meal": "sau bữa ăn",
    "bedtime": "trước khi ngủ",
}

_DEFAULT_ENCOURAGEMENTS = (
    "Chúc bạn một ngày nhiều năng lượng!",
    "Kiên trì uống thuốc đều đặn nhé, bạn đang làm rất tốt.",
    "Sức khỏe là điều quý giá nhất, cố gắng nhé!",
    "Chăm sóc bản thân thật tốt hôm nay nhé.",
)

_ENCOURAGEMENT_PROMPT = (
    "Viết đúng 1 câu động viên ngắn (dưới 20 từ), bằng tiếng Việt, cho một "
    "người vừa được nhắc uống thuốc. TUYỆT ĐỐI KHÔNG được nhắc tên thuốc, "
    "liều lượng, con số, hay thời gian trong câu. Chỉ trả về đúng 1 câu, "
    "không thêm giải thích hay dấu ngoặc kép."
)

_LLM_TIMEOUT_SECONDS = 3.0
_HAS_DIGIT = re.compile(r"\d")


def _format_template(dose: dict) -> str:
    """Slot y tế do code điền 100% — LLM không chạm vào phần này."""
    meal_text = _MEAL_RELATION_TEXT.get(dose.get("meal_relation"))
    clause = f", {meal_text}" if meal_text else ""
    return f"Đến giờ uống {dose['drug']}{clause} lúc {dose['time']}."


def _default_encouragement(seed: str) -> str:
    # Chọn xác định (deterministic) theo tên thuốc, không random — khớp
    # tinh thần "cùng input, cùng output" đã áp dụng cho compute_schedule.
    idx = sum(ord(c) for c in seed) % len(_DEFAULT_ENCOURAGEMENTS)
    return _DEFAULT_ENCOURAGEMENTS[idx]


def _is_unsafe_encouragement(text: str, drug_name: str) -> bool:
    if not text or _HAS_DIGIT.search(text):
        return True
    lowered = text.lower()
    # Chặn cả tên đầy đủ ("Metformin 500mg") lẫn từng token riêng
    # ("Metformin") — LLM có thể chỉ lỡ nhắc tên mà bỏ phần liều.
    if drug_name.lower() in lowered:
        return True
    return any(len(token) > 2 and token.lower() in lowered for token in drug_name.split())


async def _generate_encouragement(drug_name: str) -> str:
    try:
        llm = get_llm(temperature=0.5)
        response = await asyncio.wait_for(llm.ainvoke(_ENCOURAGEMENT_PROMPT), timeout=_LLM_TIMEOUT_SECONDS)
        text = str(response.content).strip()
    except Exception:  # noqa: BLE001 — LLM lỗi/timeout không bao giờ được chặn tin nhắn
        return _default_encouragement(drug_name)

    if _is_unsafe_encouragement(text, drug_name):
        return _default_encouragement(drug_name)
    return text


async def generate_message_node(dose: dict) -> dict:
    """Sinh tin nhắn nhắc uống thuốc hoàn chỉnh cho 1 cữ.

    Args:
        dose: 1 phần tử trong output của compute_schedule() — {"drug",
            "time", "meal_relation", "date"}.

    Returns:
        {"drug", "time", "message"} — message đã ghép template + câu động
        viên, sẵn sàng gửi (việc gửi không thuộc phạm vi hàm này — xem
        docs/ai_agent_scope.md: gửi thông báo thật là việc của web-app).
    """
    template_part = _format_template(dose)
    encouragement = await _generate_encouragement(dose["drug"])
    return {
        "drug": dose["drug"],
        "time": dose["time"],
        "message": f"{template_part} {encouragement}",
    }
