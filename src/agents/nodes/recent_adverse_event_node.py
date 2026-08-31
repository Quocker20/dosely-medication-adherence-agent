from langchain_core.messages import AIMessage
from src.agents.state import AgentState
from src.modules.planning.core.backend_client import BackendAPIError, get


async def recent_adverse_event_node(state: AgentState) -> dict:
    memory = state.get("memory_context") or {}
    event_id = memory.get("last_adverse_event_id")
    if not event_id:
        return {"messages": [AIMessage(content="Mình chưa có ghi nhận triệu chứng nào trước đó trong cuộc trò chuyện này. Bạn hãy mô tả triệu chứng hiện tại.")]}
    try:
        event = await get(f"/patients/{state.get('patient_id')}/adverse-events/{event_id}")
    except BackendAPIError:
        return {"messages": [AIMessage(content="Mình chưa thể đọc lại ghi nhận triệu chứng trước đó. Bạn hãy mô tả lại triệu chứng hiện tại để được đánh giá an toàn.")]}
    symptoms = ", ".join(str(item.get("name")) for item in (event or {}).get("symptoms", []) if item.get("name"))
    return {"messages": [AIMessage(content=(
        f"Ghi nhận gần nhất là: {symptoms or 'triệu chứng chưa rõ'}, mức nguy cơ {(event or {}).get('risk_level', 'chưa xác định')}. "
        "Nếu triệu chứng vẫn còn, tăng lên hoặc xuất hiện khó thở, sưng môi/lưỡi, đau ngực hay ngất, hãy liên hệ hỗ trợ y tế ngay. Không tự ngừng hoặc đổi liều thuốc."
    ))]}
