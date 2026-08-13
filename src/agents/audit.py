"""Audit log cho mỗi turn của agent — Sprint 6 checklist "Có agent_runs log
đầy đủ: input, tool calls, output, timestamp".

Đây CHỈ là log cục bộ qua `logging`, KHÔNG phải ghi vào bảng `agent_runs`
thật — chưa có endpoint/DB write path (xem src/agents/tools/agent_run_tools.py,
cùng khoảng trống đã biết ở cong_viec.md §3 câu hỏi 1). Khi có endpoint
thật, hàm log_turn() dưới đây là chỗ duy nhất cần sửa để ghi thật thay vì
log.

Cố tình KHÔNG log nội dung tin nhắn gốc của bệnh nhân — cong_viec.md §4.5:
"Không log full prompt chứa dữ liệu bệnh nhân ra log thường. Log riêng, mã
hóa, retention ngắn." Ở đây chỉ log metadata (patient_id, intent, có
escalate không, độ dài phản hồi, timestamp) — đủ để trace luồng khi có sự
cố, không đủ để lộ nội dung y tế nếu log bị rò rỉ.
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger("agent_runs")


def log_turn(*, patient_id: str, intent: str | None, escalated: bool, response_length: int) -> None:
    logger.info(
        "agent_turn patient_id=%s intent=%s escalated=%s response_length=%d timestamp=%d",
        patient_id,
        intent or "unknown",
        escalated,
        response_length,
        int(time.time()),
    )
