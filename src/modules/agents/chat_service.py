import base64
import logging
import uuid
from datetime import date

from fastapi import status
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from src.chatbot.audit import log_turn
from src.chatbot.clients.speech import (
    SpeechServiceError,
    synthesize_speech,
    transcribe_audio,
)
from src.chatbot.conversation_memory import load_working_memory, save_working_memory
from src.chatbot.graph import agent
from src.chatbot.patient_addressing import get_patient_address
from src.chatbot.patient_presentation import patient_facing_text
from src.common.exceptions import (
    AppException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from src.common.pagination import page_count
from src.common.schemas import PageResponse
from src.core.cache import build_cache_key, cached_model, invalidate_prefix
from src.core.config import get_settings
from src.modules.agents.repository import (
    ChatMemoryRepository,
    generate_conversation_title,
)
from src.modules.agents.schemas import (
    ChatConversationDetailResponse,
    ChatConversationListItem,
    ChatMessageItem,
    ChatResponse,
    VoiceChatResponse,
)

logger = logging.getLogger(__name__)


class ChatService:
    """Patient-facing conversational agent (FR-3.2), text and voice.

    Stateless and DB-free: the LangGraph agent reaches persistence through its
    own tools over the backend HTTP API, so this service only orchestrates
    transcribe -> agent -> synthesize and never touches AsyncSession.
    """

    def __init__(self, db: AsyncSession | None = None, memory_repository: ChatMemoryRepository | None = None) -> None:
        self._db = db
        self._memory = memory_repository

    async def handle_text_chat(
        self, message: str, patient_id: str, client_date=None, client_datetime=None, conversation_id=None
    ) -> ChatResponse:
        response_text, conversation_id = await self._run_agent(
            message, patient_id, client_date, client_datetime, conversation_id
        )
        return ChatResponse(response=response_text, conversationId=conversation_id)

    async def list_conversations(
        self,
        actor: dict,
        page: int = 1,
        size: int = 20,
    ) -> PageResponse[ChatConversationListItem]:
        patient_id = uuid.UUID(str(actor["sub"]))
        cache_key = build_cache_key(
            "chat:conversations:list",
            actor=actor,
            params={"page": page, "size": size},
        )
        ttl = get_settings().cache_ttl_chat_seconds

        async def _load() -> PageResponse[ChatConversationListItem]:
            if self._db is None or self._memory is None:
                return PageResponse(
                    content=[],
                    page_no=page,
                    page_size=size,
                    total_elements=0,
                    total_pages=0,
                    last=True,
                )
            rows, total = await self._memory.list_conversations(patient_id, page=page, size=size)
            items = [ChatConversationListItem.model_validate(r) for r in rows]
            total_pages = page_count(total, size)
            return PageResponse(
                content=items,
                page_no=page,
                page_size=size,
                total_elements=total,
                total_pages=total_pages,
                last=page >= total_pages if total_pages > 0 else True,
            )

        return await cached_model(cache_key, ttl, PageResponse[ChatConversationListItem], _load)

    async def get_conversation_detail(
        self,
        actor: dict,
        conversation_id: uuid.UUID,
        limit: int = 50,
        before: str | None = None,
    ) -> ChatConversationDetailResponse:
        patient_id = uuid.UUID(str(actor["sub"]))
        cache_key = build_cache_key(
            "chat:conversations:detail",
            actor=actor,
            params={"conversation_id": str(conversation_id), "limit": limit, "before": before},
        )
        ttl = get_settings().cache_ttl_chat_seconds

        async def _load() -> ChatConversationDetailResponse:
            if self._db is None or self._memory is None:
                raise NotFoundException(message="Không tìm thấy cuộc trò chuyện")
            try:
                conv = await self._memory.get_conversation(patient_id, conversation_id)
            except PermissionError as exc:
                raise ForbiddenException(message="Không có quyền truy cập cuộc trò chuyện này") from exc

            if conv is None:
                raise NotFoundException(message="Không tìm thấy cuộc trò chuyện")

            messages, has_more, next_cursor = await self._memory.get_messages_paginated(
                conversation_id=conversation_id,
                limit=limit,
                before=before,
            )
            msg_items = [
                ChatMessageItem(
                    id=m.id,
                    role=m.role,
                    content=m.content,
                    intent=m.intent,
                    created_at=m.created_at,
                )
                for m in messages
            ]
            preview = messages[-1].content if messages else None
            title = conv.summary or (generate_conversation_title(preview) if preview else "Cuộc trò chuyện mới")
            return ChatConversationDetailResponse(
                id=conv.id,
                title=title,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                messages=msg_items,
                has_more=has_more,
                next_cursor=next_cursor,
            )

        return await cached_model(cache_key, ttl, ChatConversationDetailResponse, _load)

    async def handle_voice_chat(
        self,
        audio_bytes: bytes,
        filename: str,
        patient_id: str,
        client_date=None,
        client_datetime=None,
        conversation_id=None,
    ) -> VoiceChatResponse:
        try:
            transcript = await transcribe_audio(audio_bytes, filename=filename)
        except SpeechServiceError as e:
            raise AppException(message=str(e), code=status.HTTP_502_BAD_GATEWAY) from e

        if not transcript:
            raise ValidationException(message="Không nhận được nội dung giọng nói, vui lòng nói lại.")

        response_text, conversation_id = await self._run_agent(
            transcript, patient_id, client_date, client_datetime, conversation_id
        )

        audio_base64 = None
        try:
            audio_reply = await synthesize_speech(response_text)
            audio_base64 = base64.b64encode(audio_reply).decode("ascii")
        except SpeechServiceError:
            # fail-open: a broken TTS vendor must not cost the patient the
            # text answer they already have.
            logger.warning("TTS failed, returning text-only reply")

        return VoiceChatResponse(
            transcript=transcript, response=response_text, audio_base64=audio_base64, conversationId=conversation_id
        )

    async def _run_agent(
        self, message: str, patient_id: str, client_date=None, client_datetime=None, conversation_id=None
    ) -> tuple[str, uuid.UUID]:
        persistence_available = self._db is not None and self._memory is not None
        actual_conv_id: uuid.UUID
        if self._db is not None and self._memory is not None:
            try:
                async with self._db.begin():
                    conversation = await self._memory.get_or_create(uuid.UUID(str(patient_id)), conversation_id)
                    actual_conv_id = conversation.id
                    history_rows = await self._memory.recent_messages(actual_conv_id, limit=10)
            except PermissionError as exc:
                raise ForbiddenException(message=str(exc)) from exc
            except Exception:  # memory outage must not make medication chat unavailable
                logger.warning("Durable chat memory unavailable; using turn-local memory", exc_info=True)
                actual_conv_id = uuid.UUID(str(conversation_id)) if conversation_id else uuid.uuid4()
                history_rows = []
                persistence_available = False
        else:  # isolated unit/eval mode; production DI always supplies persistence
            actual_conv_id = uuid.UUID(str(conversation_id)) if conversation_id else uuid.uuid4()
            history_rows = []
        working = await load_working_memory(str(patient_id), str(actual_conv_id)) if persistence_available else {}
        history = [
            HumanMessage(content=row.content) if row.role == "user" else AIMessage(content=row.content)
            for row in history_rows
        ]
        reference_date = client_date or (client_datetime.date() if client_datetime is not None else date.today())
        patient_address = await get_patient_address(patient_id, reference_date)
        result = await agent.ainvoke(
            {
                "messages": history + [HumanMessage(content=message)],
                "patient_id": patient_id,
                "conversation_id": str(actual_conv_id),
                "patient_address": patient_address,
                # Server is the source of truth for relative date phrases.
                "client_date": reference_date.isoformat(),
                "client_datetime": client_datetime.isoformat() if client_datetime else None,
                "memory_context": working,
            }
        )
        # Sources and citation ids remain available to the grounding/audit
        # pipeline. They are removed exactly once at the API presentation
        # boundary so no ReAct/tool fallback can leak "[Nguồn N]" to patients.
        response_text = patient_facing_text(result["messages"][-1].content)
        if persistence_available:
            async with self._db.begin():
                await self._memory.append_exchange(actual_conv_id, message, response_text, result.get("intent"))
            await invalidate_prefix("chat:conversations")
        metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        if metadata.get("resolved_medication"):
            working["current_medication"] = metadata["resolved_medication"]
        if metadata.get("adverse_event_id"):
            # Redis only keeps a short-lived pointer. Clinical symptom data
            # remains in PostgreSQL and is never copied wholesale into prompts.
            working["last_adverse_event_id"] = metadata["adverse_event_id"]
            working["last_adverse_event_at"] = metadata.get("adverse_event_reported_at")
            working["has_unreviewed_adverse_event"] = metadata.get("adverse_event_review_status") != "REVIEWED"
        if "pending_adverse_event" in metadata:
            working["pending_adverse_event"] = metadata["pending_adverse_event"]
        elif metadata.get("clear_pending_adverse_event"):
            working.pop("pending_adverse_event", None)
        elif result.get("intent") == "report_adverse_event" and working.get("pending_adverse_event"):
            working.pop("pending_adverse_event", None)
        if "pending_schedule_request" in metadata:
            working["pending_schedule_request"] = metadata["pending_schedule_request"]
        elif metadata.get("clear_pending_schedule_request"):
            working.pop("pending_schedule_request", None)
        working["last_intent"] = result.get("intent")
        if persistence_available:
            await save_working_memory(str(patient_id), str(actual_conv_id), working)
        log_turn(
            patient_id=patient_id,
            intent=result.get("intent"),
            escalated=bool(result.get("escalated")),
            response_length=len(response_text),
        )
        return response_text, actual_conv_id
