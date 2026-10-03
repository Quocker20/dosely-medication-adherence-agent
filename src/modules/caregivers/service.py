import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.exceptions import ConflictException, ForbiddenException, NotFoundException
from src.core.config import get_settings
from src.core.security import validate_phone_number
from src.core.telegram import TelegramClient, get_telegram_client
from src.modules.admin.repository import AuditLogRepository
from src.modules.caregivers.models import CaregiverLink
from src.modules.caregivers.repository import CaregiverRepository
from src.modules.caregivers.schemas import CaregiverLinkDetailResponse, CreateCaregiverLinkRequest

logger = logging.getLogger(__name__)

_UNAMBIGUOUS_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def generate_link_code(length: int = 6) -> str:
    """Generate a 6-character binding code from an unambiguous alphabet
    (no 0/O, 1/I/L) so humans can read it clearly.
    """
    return "".join(secrets.choice(_UNAMBIGUOUS_ALPHABET) for _ in range(length))


class CaregiverService:
    """Service handling Caregiver contact records, CRUD, and Telegram webhook events."""

    def __init__(
        self,
        db: AsyncSession,
        caregiver_repository: Optional[CaregiverRepository] = None,
        audit_repository: Optional[AuditLogRepository] = None,
        telegram_client: Optional[TelegramClient] = None,
    ) -> None:
        self._db = db
        self._repo = caregiver_repository or CaregiverRepository(db)
        self._audit_repo = audit_repository or AuditLogRepository(db)
        self._telegram = telegram_client or get_telegram_client()

    def _to_response(self, link: CaregiverLink) -> CaregiverLinkDetailResponse:
        settings = get_settings()
        bot_username = settings.telegram_bot_username
        deep_link = None
        if link.link_code and bot_username:
            deep_link = f"https://t.me/{bot_username}?start={link.link_code}"

        return CaregiverLinkDetailResponse(
            id=link.id,
            patient_id=link.patient_id,
            phone=link.phone,
            relationship=link.relationship_label,
            link_code=link.link_code,
            telegram_deep_link=deep_link,
            status=link.status,
            telegram_bound_at=link.telegram_bound_at,
            last_message_sent_at=link.last_message_sent_at,
            created_at=link.created_at,
        )

    # ── Caregiver CRUD ───────────────────────────────────────────────────

    async def create_caregiver_link(
        self,
        patient_id: uuid.UUID,
        request: CreateCaregiverLinkRequest,
        actor_payload: dict,
        ip_address: Optional[str] = None,
    ) -> CaregiverLinkDetailResponse:
        """PATIENT self-only: link a caregiver phone to the patient.
        Generates an unambiguous 6-char link_code for Telegram bot deep linking.
        No user account is created.
        """
        actor_id = uuid.UUID(actor_payload["sub"])
        if actor_id != patient_id:
            raise ForbiddenException(message="Cannot manage caregivers for another patient")

        cleaned_phone = validate_phone_number(request.phone)
        link_code = generate_link_code(6)

        try:
            async with self._db.begin():
                link = await self._repo.create_link(
                    patient_id=patient_id,
                    phone=cleaned_phone,
                    relationship=request.relationship,
                    link_code=link_code,
                )
                await self._audit_repo.create_audit_log(
                    action="ADD_CAREGIVER_LINK",
                    entity_type="CAREGIVER_LINK",
                    actor_user_id=patient_id,
                    entity_id=link.id,
                    new_values={
                        "phone": cleaned_phone,
                        "relationship": request.relationship,
                    },
                    ip_address=ip_address,
                )
        except IntegrityError as exc:
            logger.warning("IntegrityError creating caregiver link: %s", exc)
            raise ConflictException(message="Caregiver is already linked to this patient")

        return self._to_response(link)

    async def list_caregiver_links(
        self, patient_id: uuid.UUID, actor_payload: dict
    ) -> List[CaregiverLinkDetailResponse]:
        """PATIENT (self) or ADMIN only."""
        role = actor_payload.get("role")
        if role == "PATIENT":
            actor_id = uuid.UUID(actor_payload["sub"])
            if actor_id != patient_id:
                raise ForbiddenException(message="Cannot view another patient's caregivers")

        links = await self._repo.list_by_patient(patient_id)
        return [self._to_response(link) for link in links]

    async def delete_caregiver_link(
        self,
        patient_id: uuid.UUID,
        caregiver_link_id: uuid.UUID,
        actor_payload: dict,
        ip_address: Optional[str] = None,
    ) -> None:
        """PATIENT (self) or ADMIN only. Hard delete."""
        role = actor_payload.get("role")
        if role == "PATIENT":
            actor_id = uuid.UUID(actor_payload["sub"])
            if actor_id != patient_id:
                raise ForbiddenException(message="Cannot manage another patient's caregivers")

        async with self._db.begin():
            link = await self._repo.get_link(caregiver_link_id, patient_id)
            if link is None:
                raise NotFoundException(message="Caregiver link not found")
            await self._repo.delete_link(caregiver_link_id)
            await self._audit_repo.create_audit_log(
                action="REMOVE_CAREGIVER_LINK",
                entity_type="CAREGIVER_LINK",
                actor_user_id=uuid.UUID(actor_payload["sub"]),
                entity_id=caregiver_link_id,
                old_values={"phone": link.phone},
                ip_address=ip_address,
            )

    # ── Webhook Handler ──────────────────────────────────────────────────

    async def handle_webhook_update(self, payload: Dict[str, Any]) -> None:
        """Process incoming Telegram webhook update.
        Handles /start <link_code> binding, /stop opt-out, and interaction touches.
        Always fails open without raising so Telegram receives 200.
        """
        message = payload.get("message") or payload.get("edited_message")
        if not message:
            return

        chat = message.get("chat", {})
        chat_id = chat.get("id")
        if chat_id is None:
            return

        text = (message.get("text") or "").strip()
        now = datetime.now(timezone.utc)

        try:
            if text.startswith("/start"):
                parts = text.split(maxsplit=1)
                link_code = parts[1].strip() if len(parts) > 1 else None

                if link_code:
                    if self._db.in_transaction():
                        await self._db.commit()

                    async with self._db.begin():
                        bound_link = await self._repo.bind_by_code(
                            link_code=link_code,
                            telegram_chat_id=chat_id,
                            now=now,
                        )

                    if bound_link:
                        msg = (
                            "Dosely: Đã liên kết tài khoản người thân thành công! "
                            "Bạn sẽ nhận được thông báo nhắc nhở và cảnh báo an toàn của người bệnh.\n\n"
                            "Để dừng nhận thông báo, gửi /stop."
                        )
                    else:
                        msg = "Dosely: Mã liên kết không hợp lệ hoặc đã được sử dụng."

                    try:
                        await self._telegram.send_message(chat_id, msg)
                    except Exception as exc:
                        logger.warning("Failed to send /start reply to Telegram chat %s: %s", chat_id, exc)

                else:
                    if self._db.in_transaction():
                        await self._db.commit()

                    async with self._db.begin():
                        await self._repo.touch_interaction(chat_id, now)

                    welcome_msg = (
                        "Chào bạn! Đây là hệ thống thông báo người thân Dosely.\n"
                        "Để liên kết, vui lòng sử dụng liên kết mời hoặc mã QR từ ứng dụng Dosely của người bệnh."
                    )
                    try:
                        await self._telegram.send_message(chat_id, welcome_msg)
                    except Exception as exc:
                        logger.warning("Failed to send welcome reply to chat %s: %s", chat_id, exc)

            elif text == "/stop":
                if self._db.in_transaction():
                    await self._db.commit()

                async with self._db.begin():
                    await self._repo.set_inactive(chat_id)

                stop_msg = (
                    "Bạn đã hủy nhận thông báo từ Dosely.\n"
                    "Nếu muốn kích hoạt lại, vui lòng quét lại mã liên kết từ ứng dụng của người bệnh."
                )
                try:
                    await self._telegram.send_message(chat_id, stop_msg)
                except Exception as exc:
                    logger.warning("Failed to send /stop reply to chat %s: %s", chat_id, exc)

            else:
                if self._db.in_transaction():
                    await self._db.commit()

                async with self._db.begin():
                    await self._repo.touch_interaction(chat_id, now)

        except Exception as exc:
            logger.exception("Error processing webhook update for chat %s: %s", chat_id, exc)
