from __future__ import annotations
from datetime import datetime, timedelta
from langchain_core.messages import AIMessage, HumanMessage
from src.agents.adverse_event_risk import classify_adverse_event_risk
from src.agents.state import AgentState
from src.modules.planning.core.backend_client import BackendAPIError, get, post


def _last_text(state: AgentState) -> str:
    for message in reversed(state.get("messages") or []):
        if isinstance(message, HumanMessage): return str(message.content)
    return ""


def _is_question_not_report(text: str) -> bool:
    """Prevent a knowledge/triage question from being persisted as an event."""
    t = " ".join(text.lower().split())
    question = "?" in t or any(p in t for p in ("phải làm sao", "nên làm gì", "có ... không"))
    hypothetical = any(p in t for p in ("có đau", "có gây", "có bị", "tác dụng phụ", "có phải do"))
    explicit_report = any(p in t for p in ("tôi bị", "mình bị", "tôi đang bị", "mình đang bị", "đã bị", "bị đau"))
    return question and hypothetical and not explicit_report

def _is_confirmation(text: str) -> bool:
    return text.strip().lower() in {"có", "co", "đúng", "dung", "xác nhận", "xac nhan", "đồng ý", "dong y"}


async def _medication_context(state: AgentState) -> list[dict]:
    patient_id = state.get("patient_id")
    result: list[dict] = []
    # Full active prescription context is clinically relevant even when a
    # medicine was not taken near the reported symptom.
    try:
        params = {"as_of": state.get("client_date")} if state.get("client_date") else None
        current = await get("/patients/me/medications/current", params=params)
        for medication in (current or {}).get("medications", []):
            result.append({
                "medication_id": medication.get("medication_id") or medication.get("id"),
                "drug_name": medication.get("display_name") or medication.get("medication_name") or "Thuốc chưa rõ tên",
                "taken_at": None,
                "context_type": "ACTIVE_PRESCRIPTION",
            })
    except BackendAPIError:
        pass
    try:
        data = await get(f"/patients/{patient_id}/schedules", params={"date": state.get("client_date")} if state.get("client_date") else None)
    except BackendAPIError:
        return result
    now_raw = state.get("client_datetime")
    try: now = datetime.fromisoformat(str(now_raw).replace("Z", "+00:00"))
    except ValueError: now = None
    for dose in (data or {}).get("doses", []):
        if str(dose.get("status", "")).upper() != "TAKEN": continue
        taken_raw = dose.get("taken_at") or dose.get("current_scheduled_at")
        if now:
            try:
                taken = datetime.fromisoformat(str(taken_raw).replace("Z", "+00:00"))
                if not now - timedelta(hours=24) <= taken <= now: continue
            except ValueError: pass
        result.append({"medication_id": dose.get("medication_id"), "drug_name": dose.get("medication_name") or "Thuốc chưa rõ tên", "taken_at": taken_raw, "context_type": "RECENTLY_TAKEN"})
    return result[:30]


async def adverse_event_node(state: AgentState) -> dict:
    analysis = state.get("intent_analysis") or {}
    symptoms = list(analysis.get("symptoms") or [])
    raw = _last_text(state)
    pending = (state.get("memory_context") or {}).get("pending_adverse_event")
    if pending and (state.get("intent") == "report_adverse_event"):
        symptoms = pending.get("symptoms") or symptoms
        raw = pending.get("raw_text") or raw
    if _is_question_not_report(raw):
        return {"messages": [AIMessage(content=(
            "Mình hiểu đây là câu hỏi về khả năng tác dụng phụ/cách xử trí, chưa phải xác nhận bạn đang mắc triệu chứng. "
            "Bạn có đang thực sự bị đau bụng hoặc triệu chứng nào khác không? Nếu có, hãy cho biết triệu chứng, thời điểm bắt đầu và mức độ; "
            "mình chỉ ghi nhận gửi bác sĩ sau khi bạn xác nhận."
        ))], "metadata": {"pending_adverse_event": {"raw_text": raw, "symptoms": symptoms}}}
    if not symptoms:
        return {"messages": [AIMessage(content="Bạn đang gặp triệu chứng gì, mức độ ra sao và bắt đầu từ khi nào?")]}
    risk = classify_adverse_event_risk(raw, symptoms)
    payload = {"conversation_id": state.get("conversation_id"), "raw_text": raw, "symptoms": symptoms,
               "related_medications": await _medication_context(state), "risk_level": risk}
    try:
        saved = await post(f"/patients/{state.get('patient_id')}/adverse-events", json=payload)
    except BackendAPIError:
        return {"messages": [AIMessage(content="Mình đã nhận được thông tin triệu chứng nhưng chưa thể lưu vào hồ sơ lúc này. Nếu triệu chứng tăng lên, hãy liên hệ bác sĩ/dược sĩ.")]}
    if risk in {"HIGH", "CRITICAL"}:
        reply = "Mình đã ghi nhận triệu chứng và gửi cảnh báo để bác sĩ xem sớm. Nếu bạn khó thở, sưng môi/lưỡi, đau ngực, ngất hoặc triệu chứng tăng nhanh, hãy gọi cấp cứu ngay."
    else:
        reply = "Mình đã ghi nhận triệu chứng nghi ngờ để bác sĩ xem xét. Thông tin này chưa khẳng định thuốc là nguyên nhân; không tự ngừng hoặc đổi liều khi chưa được hướng dẫn."
    return {"messages": [AIMessage(content=reply)], "metadata": {
        "adverse_event_risk": risk,
        "adverse_event_id": str((saved or {}).get("id") or ""),
        "adverse_event_reported_at": (saved or {}).get("reported_at"),
        "adverse_event_review_status": (saved or {}).get("review_status", "NEW"),
    }}
