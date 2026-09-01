import uuid
from datetime import datetime, timezone
import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from src.core.config import get_settings
from src.core.database import AsyncSessionLocal, engine
from src.core.security import hash_password
from src.core.telegram import FakeTelegramClient, TelegramBlockedError, TelegramRateLimitError
from src.modules.adherence.models import NotificationDelivery
from src.modules.adherence.repository import NotificationRepository
from src.modules.agents.tasks import _execute_send_notification
from src.modules.auth.models import User
from src.modules.auth.repository import AuthRepository
from src.modules.caregivers.models import CaregiverLink
from src.modules.caregivers.repository import CaregiverRepository
from src.modules.patients.models import PatientProfile
from src.modules.patients.repository import PatientRepository

PATIENT_PHONE = "+84900500001"
CAREGIVER_PHONE = "+84900500002"
PIN = "123456"
_TEST_PHONES = [PATIENT_PHONE, CAREGIVER_PHONE]


@pytest_asyncio.fixture(autouse=True)
async def _setup(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "telegram_enabled", True)
    monkeypatch.setattr(settings, "telegram_bot_token", "fake_bot_token")

    async with AsyncSessionLocal() as db:
        async with db.begin():
            ids = (await db.execute(select(User.id).where(User.phone.in_(_TEST_PHONES)))).scalars().all()
            if ids:
                cg_link_ids = (await db.execute(select(CaregiverLink.id).where(CaregiverLink.patient_id.in_(ids)))).scalars().all()
                if cg_link_ids:
                    await db.execute(delete(NotificationDelivery).where(NotificationDelivery.caregiver_link_id.in_(cg_link_ids)))
                await db.execute(delete(NotificationDelivery).where(NotificationDelivery.recipient_user_id.in_(ids)))
                await db.execute(delete(CaregiverLink).where(CaregiverLink.patient_id.in_(ids)))
                await db.execute(delete(PatientProfile).where(PatientProfile.user_id.in_(ids)))
                await db.execute(delete(User).where(User.id.in_(ids)))
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_send_telegram_notification_success(monkeypatch):
    fake_tg = FakeTelegramClient()
    from src.core import telegram
    monkeypatch.setattr(telegram, "get_telegram_client", lambda: fake_tg)

    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await AuthRepository(db).create_user(phone=PATIENT_PHONE, hashed_password=hash_password(PIN), role="PATIENT")
            await PatientRepository(db).create_patient_profile(user_id=user.id, name="Bác An")
            link = await CaregiverRepository(db).create_link(
                patient_id=user.id,
                phone=CAREGIVER_PHONE,
                relationship="Con gái",
                link_code="ABC888",
            )
            # Bind caregiver
            await CaregiverRepository(db).bind_by_code("ABC888", 777777, datetime.now(timezone.utc))
            link_id = link.id

            delivery = await NotificationRepository(db).create_caregiver_delivery(
                caregiver_link_id=link_id,
                template_code="CG_MISSED_DOSE",
                title="Cảnh báo uống thuốc",
                body="Người bệnh Bác An đã quên liều thuốc sáng nay.",
            )
            delivery_id = delivery.id

    await _execute_send_notification(str(delivery_id))

    async with AsyncSessionLocal() as db:
        updated_delivery = await NotificationRepository(db).get_delivery_by_id(delivery_id)
        assert updated_delivery.status == "DELIVERED"
        assert updated_delivery.provider_message_id is not None

        updated_link = await CaregiverRepository(db).get_link_by_id(link_id)
        assert updated_link.last_message_sent_at is not None

    assert len(fake_tg.sent_messages) == 1
    assert fake_tg.sent_messages[0]["chat_id"] == 777777
    assert "Bác An đã quên liều" in fake_tg.sent_messages[0]["text"]


@pytest.mark.asyncio
async def test_send_telegram_notification_unbound_fails(monkeypatch):
    fake_tg = FakeTelegramClient()
    from src.core import telegram
    monkeypatch.setattr(telegram, "get_telegram_client", lambda: fake_tg)

    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await AuthRepository(db).create_user(phone=PATIENT_PHONE, hashed_password=hash_password(PIN), role="PATIENT")
            await PatientRepository(db).create_patient_profile(user_id=user.id, name="Bác An")
            link = await CaregiverRepository(db).create_link(
                patient_id=user.id,
                phone=CAREGIVER_PHONE,
                relationship="Con gái",
                link_code="UNBOUND1",
            )
            link_id = link.id

            delivery = await NotificationRepository(db).create_caregiver_delivery(
                caregiver_link_id=link_id,
                template_code="CG_MISSED_DOSE",
                title="Cảnh báo",
                body="Test",
            )
            delivery_id = delivery.id

    await _execute_send_notification(str(delivery_id))

    async with AsyncSessionLocal() as db:
        updated_delivery = await NotificationRepository(db).get_delivery_by_id(delivery_id)
        assert updated_delivery.status == "FAILED"
        assert "not active or bound" in updated_delivery.delivery_metadata.get("error", "")


@pytest.mark.asyncio
async def test_send_telegram_notification_blocked_marks_cg_blocked(monkeypatch):
    fake_tg = FakeTelegramClient()
    fake_tg.error_to_raise = TelegramBlockedError("Forbidden: bot was blocked by the user")
    from src.core import telegram
    monkeypatch.setattr(telegram, "get_telegram_client", lambda: fake_tg)

    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await AuthRepository(db).create_user(phone=PATIENT_PHONE, hashed_password=hash_password(PIN), role="PATIENT")
            await PatientRepository(db).create_patient_profile(user_id=user.id, name="Bác An")
            link = await CaregiverRepository(db).create_link(
                patient_id=user.id,
                phone=CAREGIVER_PHONE,
                relationship="Con gái",
                link_code="ABC555",
            )
            await CaregiverRepository(db).bind_by_code("ABC555", 666666, datetime.now(timezone.utc))
            link_id = link.id

            delivery = await NotificationRepository(db).create_caregiver_delivery(
                caregiver_link_id=link_id,
                template_code="CG_MISSED_DOSE",
                title="Cảnh báo",
                body="Test",
            )
            delivery_id = delivery.id

    await _execute_send_notification(str(delivery_id))

    async with AsyncSessionLocal() as db:
        updated_delivery = await NotificationRepository(db).get_delivery_by_id(delivery_id)
        assert updated_delivery.status == "BLOCKED_BY_USER"

        updated_link = await CaregiverRepository(db).get_link_by_id(link_id)
        assert updated_link.status == "BLOCKED"


@pytest.mark.asyncio
async def test_send_telegram_notification_rate_limit_raises_and_sets_retrying(monkeypatch):
    fake_tg = FakeTelegramClient()
    fake_tg.error_to_raise = TelegramRateLimitError("Rate limit", retry_after=15)
    from src.core import telegram
    monkeypatch.setattr(telegram, "get_telegram_client", lambda: fake_tg)

    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await AuthRepository(db).create_user(phone=PATIENT_PHONE, hashed_password=hash_password(PIN), role="PATIENT")
            await PatientRepository(db).create_patient_profile(user_id=user.id, name="Bác An")
            link = await CaregiverRepository(db).create_link(
                patient_id=user.id,
                phone=CAREGIVER_PHONE,
                relationship="Con gái",
                link_code="ABC444",
            )
            await CaregiverRepository(db).bind_by_code("ABC444", 444444, datetime.now(timezone.utc))
            link_id = link.id

            delivery = await NotificationRepository(db).create_caregiver_delivery(
                caregiver_link_id=link_id,
                template_code="CG_MISSED_DOSE",
                title="Cảnh báo",
                body="Test",
            )
            delivery_id = delivery.id

    with pytest.raises(TelegramRateLimitError):
        await _execute_send_notification(str(delivery_id))

    async with AsyncSessionLocal() as db:
        updated_delivery = await NotificationRepository(db).get_delivery_by_id(delivery_id)
        assert updated_delivery.status == "RETRYING"
