from datetime import datetime, timezone
import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from src.core.config import get_settings
from src.core.database import AsyncSessionLocal, engine
from src.core.security import hash_password
from src.core.telegram import FakeTelegramClient, TelegramBlockedError
from src.modules.adherence.models import Alert, NotificationDelivery
from src.modules.adherence.repository import AlertRepository, NotificationRepository
from src.modules.adherence.schemas import TriggerSosRequest
from src.modules.adherence.service import AlertService
from src.modules.agents.models import ScheduledDose
from src.modules.agents.tasks import _execute_send_notification
from src.modules.auth.models import User
from src.modules.auth.repository import AuthRepository
from src.modules.caregivers.models import CaregiverLink
from src.modules.caregivers.repository import CaregiverRepository
from src.modules.patients.models import PatientProfile
from src.modules.patients.repository import PatientRepository
from src.modules.prescriptions.models import Medication, Prescription, PrescriptionItem

PATIENT_PHONE = "+84900500001"
CAREGIVER_PHONE = "+84900500003"
PIN = "123456"
_TEST_PHONES = [PATIENT_PHONE, CAREGIVER_PHONE]


@pytest_asyncio.fixture(autouse=True)
async def _setup(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "telegram_enabled", True)
    monkeypatch.setattr(settings, "telegram_bot_token", "mock_bot_token_123")
    monkeypatch.setattr(settings, "caregiver_report_interval_days", 7)
    monkeypatch.setattr(settings, "missed_dose_alert_threshold", 3)
    monkeypatch.setattr(settings, "missed_dose_overdue_minutes", 120)
    from src.modules.agents import tasks
    monkeypatch.setattr(tasks.send_notification_task, "delay", lambda d_id: None)

    async with AsyncSessionLocal() as db:
        async with db.begin():
            await db.execute(delete(NotificationDelivery))
            await db.execute(delete(CaregiverLink))
            ids = (await db.execute(select(User.id).where(User.phone.in_(_TEST_PHONES)))).scalars().all()
            if ids:
                await db.execute(delete(ScheduledDose).where(ScheduledDose.patient_id.in_(ids)))
                await db.execute(delete(Alert).where(Alert.patient_id.in_(ids)))
                await db.execute(delete(PrescriptionItem).where(PrescriptionItem.prescription_id.in_(
                    select(Prescription.id).where(Prescription.patient_id.in_(ids))
                )))
                await db.execute(delete(Prescription).where(Prescription.patient_id.in_(ids)))
                await db.execute(delete(PatientProfile).where(PatientProfile.user_id.in_(ids)))
                await db.execute(delete(User).where(User.id.in_(ids)))
            await db.execute(delete(Medication).where(Medication.source_record_key == "TEST-AMLODIPINE-10"))
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_full_flow_link_bind_alert_and_telegram_send(monkeypatch):
    fake_client = FakeTelegramClient()
    monkeypatch.setattr("src.core.telegram.get_telegram_client", lambda: fake_client)
    monkeypatch.setattr("src.core.telegram._fake_instance", fake_client)

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        async with db.begin():
            patient = await AuthRepository(db).create_user(phone=PATIENT_PHONE, hashed_password=hash_password(PIN), role="PATIENT")
            await PatientRepository(db).create_patient_profile(user_id=patient.id, name="Cụ Ông")

            # Create & bind caregiver link
            link = await CaregiverRepository(db).create_link(
                patient_id=patient.id,
                phone=CAREGIVER_PHONE,
                relationship="Con trai",
                link_code="CUONG1",
            )
            await CaregiverRepository(db).bind_by_code("CUONG1", 777123456, now)
            patient_id = patient.id
            link_id = link.id

    # 1. Trigger SOS Alert
    async with AsyncSessionLocal() as db:
        alert_service = AlertService(
            db=db,
            alert_repository=AlertRepository(db),
            audit_repository=None,
            patient_repository=PatientRepository(db),
        )
        await alert_service.trigger_sos(
            patient_id=patient_id,
            request=TriggerSosRequest(
                triggered_by_type="SOS_BUTTON",
                severity="CRITICAL",
                message="Bệnh nhân bấm nút SOS khẩn cấp",
            ),
            actor_payload={"sub": str(patient_id)},
            idempotency_key="sos-test-key-1",
        )

    # Verify notification delivery created for caregiver
    async with AsyncSessionLocal() as db:
        deliveries = (await db.execute(
            select(NotificationDelivery).where(NotificationDelivery.caregiver_link_id == link_id)
        )).scalars().all()
        assert len(deliveries) == 1
        delivery = deliveries[0]
        assert delivery.template_code == "CG_ALERT_RED"
        assert delivery.channel == "TELEGRAM"
        assert "Cụ Ông" in delivery.body
        assert delivery.status == "QUEUED"
        delivery_id = delivery.id

    # 2. Execute send notification via Celery task execution
    await _execute_send_notification(str(delivery_id))

    # Verify FakeTelegramClient recorded the message
    assert len(fake_client.sent_messages) == 1
    msg = fake_client.sent_messages[0]
    assert msg["chat_id"] == 777123456
    assert "Cụ Ông" in msg["text"]
    assert "SOS" in msg["text"]

    # Verify delivery marked DELIVERED
    async with AsyncSessionLocal() as db:
        d = await db.get(NotificationDelivery, delivery_id)
        assert d.status == "DELIVERED"


@pytest.mark.asyncio
async def test_blocked_caregiver_marks_link_and_delivery_blocked(monkeypatch):
    fake_client = FakeTelegramClient()
    fake_client.error_to_raise = TelegramBlockedError("Forbidden: bot was blocked by the user")
    monkeypatch.setattr("src.core.telegram.get_telegram_client", lambda: fake_client)
    monkeypatch.setattr("src.core.telegram._fake_instance", fake_client)

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        async with db.begin():
            patient = await AuthRepository(db).create_user(phone=PATIENT_PHONE, hashed_password=hash_password(PIN), role="PATIENT")
            await PatientRepository(db).create_patient_profile(user_id=patient.id, name="Cụ Bà")
            link = await CaregiverRepository(db).create_link(
                patient_id=patient.id,
                phone=CAREGIVER_PHONE,
                relationship="Con gái",
                link_code="BLK001",
            )
            await CaregiverRepository(db).bind_by_code("BLK001", 888123456, now)
            delivery = await NotificationRepository(db).create_caregiver_delivery(
                caregiver_link_id=link.id,
                template_code="CG_REPORT",
                title="Báo cáo",
                body="Test body",
            )
            delivery_id = delivery.id
            link_id = link.id

    # Execute send
    await _execute_send_notification(str(delivery_id))

    async with AsyncSessionLocal() as db:
        d = await db.get(NotificationDelivery, delivery_id)
        assert d.status == "BLOCKED_BY_USER"

        cg = await db.get(CaregiverLink, link_id)
        assert cg.status == "BLOCKED"
