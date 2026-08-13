import base64

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from langchain_core.messages import HumanMessage

from src.agents.audit import log_turn
from src.agents.graph import agent
from src.models.schemas import ChatRequest, ChatResponse, VoiceChatResponse
from src.services.speech import SpeechServiceError, synthesize_speech, transcribe_audio

router = APIRouter()


async def _run_agent(message: str, patient_id: str) -> str:
    result = await agent.ainvoke(
        {
            "messages": [HumanMessage(content=message)],
            "patient_id": patient_id,
        }
    )
    response_text = result["messages"][-1].content
    log_turn(
        patient_id=patient_id,
        intent=result.get("intent"),
        escalated=bool(result.get("escalated")),
        response_length=len(response_text),
    )
    return response_text


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Chat với AI agent bằng chữ."""
    try:
        response_text = await _run_agent(request.message, request.patient_id)
        return ChatResponse(response=response_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/voice", response_model=VoiceChatResponse)
async def chat_voice(
    patient_id: str = Form(...),
    audio: UploadFile = File(...),
) -> VoiceChatResponse:
    """Chat bằng giọng nói — cho bệnh nhân cao tuổi không muốn/không tiện gõ
    chữ. STT -> text -> agent graph (y hệt /chat, kể cả safety_guard) -> TTS.

    STT lỗi -> 502 rõ ràng, KHÔNG âm thầm coi như không nói gì (một câu mô
    tả triệu chứng bị nuốt vì lỗi STT là nguy hiểm — xem
    src/services/speech.py). TTS lỗi -> vẫn trả response dạng chữ,
    audio_base64=None — thiếu audio không đáng để chặn cả phản hồi.
    """
    audio_bytes = await audio.read()

    try:
        transcript = await transcribe_audio(audio_bytes, filename=audio.filename or "audio.webm")
    except SpeechServiceError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    if not transcript:
        raise HTTPException(status_code=422, detail="Không nhận được nội dung giọng nói, vui lòng nói lại.")

    try:
        response_text = await _run_agent(transcript, patient_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    audio_base64 = None
    try:
        audio_reply = await synthesize_speech(response_text)
        audio_base64 = base64.b64encode(audio_reply).decode("ascii")
    except SpeechServiceError:
        pass  # fail-open: thiếu audio, không thiếu phản hồi

    return VoiceChatResponse(transcript=transcript, response=response_text, audio_base64=audio_base64)


@router.get("/status")
async def agent_status():
    """Kiểm tra trạng thái agent."""
    return {"status": "ready", "agent": "LangGraph Agent v1.0"}
