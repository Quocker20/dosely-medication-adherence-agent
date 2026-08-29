"""WRITE tool — submit daily health survey. See cong_viec.md §2.2, FR-5.1.

Endpoint: POST /patients/{patient_id}/health-surveys (api-contract.md
Slice 7). Body matches SubmitHealthSurveyRequest (schema.md §7.4).

cong_viec.md §2.2 constraint: only structured (enum) answers should reach
this tool; free-text belongs in a separate store and must NOT be fed back
into the LLM prompt. This tool does not enforce that itself — the caller
(node that builds `responses`/`symptoms`) is responsible for keeping raw
free-text out of whatever it puts in front of the LLM.
"""
from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from src.agents.tool_authorization import authorize_patient_write
from src.modules.planning.core.backend_client import BackendAPIError, post


@tool
async def record_health_survey(
    patient_id: str,
    survey_date: str,
    answers_json: dict[str, Any],
    symptoms: list[dict[str, Any]] | None = None,
) -> str:
    """Ghi nhận khảo sát sức khỏe hằng ngày của bệnh nhân.

    Args:
        patient_id: Mã UUID của bệnh nhân
        survey_date: Ngày làm khảo sát, định dạng YYYY-MM-DD
        answers_json: Câu trả lời chỉ số (huyết áp, đường huyết...), dạng dict
        symptoms: Danh sách triệu chứng, mỗi phần tử gồm symptom_code,
            severity (MILD/MODERATE/SEVERE), description. Mặc định rỗng.

    Returns:
        Kết quả ghi nhận (id, status) dạng chuỗi, hoặc thông báo lỗi
    """
    try:
        authorize_patient_write("record_health_survey", patient_id, intent="report_health_survey")
        result = await post(
            f"/patients/{patient_id}/health-surveys",
            json={
                "survey_date": survey_date,
                "answers_json": answers_json,
                "symptoms": symptoms or [],
            },
        )
    except BackendAPIError as e:
        return f"Không ghi nhận được khảo sát: {e.detail}"
    return str(result)
