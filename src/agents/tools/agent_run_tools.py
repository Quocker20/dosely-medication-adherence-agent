"""WRITE tool — update agent_runs job metadata. See cong_viec.md §2.2.

STUB. api-contract.md Slice 6 only has `GET /agent-runs/{agent_run_id}` —
there is no PATCH/PUT/POST to update a run's status from outside. This is
the exact open question cong_viec.md §3 item 1 raises ("AI ghi thẳng vào
bảng agent_runs... hay có internal endpoint riêng?"). No DB access layer
exists in this repo either (no SQLAlchemy/session setup), so a direct-write
path isn't available as a fallback right now. Confirm with the backend team
which path this should use, then implement `_update_agent_run`.
"""
from __future__ import annotations

from langchain_core.tools import tool


async def _update_agent_run(
    agent_run_id: str,
    status: str,
    generated_dose_count: int | None,
    error_code: str | None,
) -> dict:
    raise NotImplementedError(
        "Chưa có endpoint hoặc DB write path để cập nhật agent_runs "
        "(api-contract.md chỉ có GET /agent-runs/{id}). Cần xác nhận với "
        "backend team (xem cong_viec.md mục 3, câu hỏi 1) rồi implement lại."
    )


@tool
async def update_agent_run(
    agent_run_id: str,
    status: str,
    generated_dose_count: int | None = None,
    error_code: str | None = None,
) -> str:
    """Cập nhật metadata của một lần chạy agent (agent_runs). Chỉ ghi metadata
    job, không chạm dữ liệu y tế.

    Args:
        agent_run_id: Mã UUID của lần chạy agent
        status: Trạng thái mới (RUNNING/COMPLETED/FAILED)
        generated_dose_count: Số lượng cữ thuốc đã sinh ra (nếu có)
        error_code: Mã lỗi nếu thất bại (nếu có)

    Returns:
        Kết quả cập nhật, hoặc thông báo lỗi rõ ràng nếu chưa thực hiện được
    """
    try:
        result = await _update_agent_run(agent_run_id, status, generated_dose_count, error_code)
    except NotImplementedError as e:
        return f"[CHƯA IMPLEMENT] {e}"
    return str(result)
