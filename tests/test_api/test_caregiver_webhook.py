from datetime import datetime, timezone
import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from src.core.config import get_settings
from src.core.database import AsyncSessionLocal, engine
from src.core.security import hash_password
from src.core.telegram import FakeTelegramClient
from src.modules.auth.models import User
from src.modules.auth.repository import AuthRepository
from src.modules.caregivers.models import CaregiverLink
from src.modules.caregivers.repository import CaregiverRepository
from src.modules.patients.models import PatientProfile
from src.modules.patients.repository import PatientRepository

PATIENT_PHONE = "+84900700001"
CAREGIVER_PHONE = "+84900700002"
PIN = "123456"
SECRET_TOKEN = "test_telegram_secret_token_1234567890"


@pytest_asyncio.fixture(autouse=True)
async def _setup(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "telegram_webhook_secret", SECRET_TOKEN)
    monkeypatch.setattr(settings, "telegram_enabled", True)
    monkeypatch.setattr(settings, "telegram_bot_token", "fake_bot_token")

    async with AsyncSessionLocal() as db:
        async with db.begin():
            u_ids = (await db.execute(select(User.id).where(User.phone.in_([PATIENT_PHONE, CAREGIVER_PHONE])))).scalars().all()
            if u_ids:
                await db.execute(delete(CaregiverLink).where(CaregiverLink.patient_id.in_(u_ids)))
                await db.execute(delete(PatientProfile).where(PatientProfile.user_id.in_(u_ids)))
                await db.execute(delete(User).where(User.id.in_(u_ids)))
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_webhook_requires_secret_token(client):
    response = await client.post("/webhooks/telegram", json={"update_id": 1})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_rejects_wrong_secret_token(client):
    headers = {"X-Telegram-Bot-Api-Secret-Token": "wrong_secret"}
    response = await client.post("/webhooks/telegram", json={"update_id": 1}, headers=headers)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_start_valid_code_binds_caregiver(client, monkeypatch):
    fake_tg = FakeTelegramClient()

    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await AuthRepository(db).create_user(phone=PATIENT_PHONE, hashed_password=hash_password(PIN), role="PATIENT")
            await PatientRepository(db).create_patient_profile(user_id=user.id, name="Bác An")
            link = await CaregiverRepository(db).create_link(
                patient_id=user.id,
                phone=CAREGIVER_PHONE,
                relationship="Con gái",
                link_code="ABC123",
            )
            patient_id = user.id
            link_id = link.id

    from src.main import app
    from src.core.telegram import get_telegram_client
    app.dependency_overrides[get_telegram_client] = lambda: fake_tg

    headers = {"X-Telegram-Bot-Api-Secret-Token": SECRET_TOKEN}
    payload = {
        "update_id": 100,
        "message": {
            "message_id": 1,
            "chat": {"id": 987654321, "type": "private"},
            "text": "/start ABC123",
        },
    }

    response = await client.post("/webhooks/telegram", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json() == {"ok": True}

    async with AsyncSessionLocal() as db:
        updated_link = await CaregiverRepository(db).get_link_by_id(link_id)
        assert updated_link.status == "ACTIVE"
        assert updated_link.telegram_chat_id == 987654321
        assert updated_link.link_code is None
        assert updated_link.telegram_bound_at is not None

    assert len(fake_tg.sent_messages) == 1
    assert fake_tg.sent_messages[0]["chat_id"] == 987654321
    assert "Đã liên kết tài khoản người thân thành công" in fake_tg.sent_messages[0]["text"]
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_webhook_stop_sets_inactive(client):
    fake_tg = FakeTelegramClient()

    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await AuthRepository(db).create_user(phone=PATIENT_PHONE, hashed_password=hash_password(PIN), role="PATIENT")
            await PatientRepository(db).create_patient_profile(user_id=user.id, name="Bác An")
            link = await CaregiverRepository(db).create_link(
                patient_id=user.id,
                phone=CAREGIVER_PHONE,
                relationship="Con gái",
                link_code="ABC999",
            )
            # Bind link first
            await CaregiverRepository(db).bind_by_code("ABC999", 555555, datetime.now(timezone.utc))
            link_id = link.id

    from src.main import app
    from src.core.telegram import get_telegram_client
    app.dependency_overrides[get_telegram_client] = lambda: fake_tg

    headers = {"X-Telegram-Bot-Api-Secret-Token": SECRET_TOKEN}
    payload = {
        "update_id": 101,
        "message": {
            "message_id": 2,
            "chat": {"id": 555555, "type": "private"},
            "text": "/stop",
        },
    }

    response = await client.post("/webhooks/telegram", json=payload, headers=headers)
    assert response.status_code == 200

    async with AsyncSessionLocal() as db:
        updated_link = await CaregiverRepository(db).get_link_by_id(link_id)
        assert updated_link.status == "INACTIVE"

    assert len(fake_tg.sent_messages) == 1
    assert fake_tg.sent_messages[0]["chat_id"] == 555555
    assert "hủy nhận thông báo" in fake_tg.sent_messages[0]["text"]
    app.dependency_overrides.clear()
