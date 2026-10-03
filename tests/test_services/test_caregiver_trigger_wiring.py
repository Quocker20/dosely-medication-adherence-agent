from datetime import datetime, timedelta, timezone
import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from src.core.config import get_settings
from src.core.database import AsyncSessionLocal, engine
from src.core.security import hash_password
from src.modules.adherence.models import Alert, NotificationDelivery
from src.modules.adherence.repository import AlertRepository
from src.modules.agents.models import ScheduledDose
from src.modules.agents.repository import ScheduledDoseRepository
from src.modules.agents.service import MissedDoseScanService
from src.modules.agents.tasks import _execute_send_caregiver_adherence_reports
from src.modules.auth.models import User
from src.modules.auth.repository import AuthRepository
from src.modules.caregivers.models import CaregiverLink
from src.modules.caregivers.repository import CaregiverRepository
from src.modules.patients.models import PatientProfile
from src.modules.patients.repository import PatientRepository
from src.modules.prescriptions.models import Medication, Prescription, PrescriptionItem

PATIENT_PHONE = "+84900400001"
CAREGIVER_PHONE = "+84900400003"
PIN = "123456"
_TEST_PHONES = [PATIENT_PHONE, CAREGIVER_PHONE]


@pytest_asyncio.fixture(autouse=True)
async def _setup(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "caregiver_report_interval_days", 7)
    monkeypatch.setattr(settings, "missed_dose_alert_threshold", 3)
    monkeypatch.setattr(settings, "missed_dose_overdue_minutes", 120)

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
            await db.execute(delete(Medication).where(Medication.source_record_key.in_(["TEST-AMLODIPINE-KEY", "TEST-MED-KEY"])))
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_periodic_adherence_report_task_claims_and_creates_deliveries(monkeypatch):
    enqueued_task_ids = []
    from src.modules.agents import tasks
    monkeypatch.setattr(tasks.send_notification_task, "delay", lambda d_id: enqueued_task_ids.append(d_id))

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        async with db.begin():
            patient = await AuthRepository(db).create_user(phone=PATIENT_PHONE, hashed_password=hash_password(PIN), role="PATIENT")
            await PatientRepository(db).create_patient_profile(user_id=patient.id, name="Bác Hùng")

            link = await CaregiverRepository(db).create_link(
                patient_id=patient.id,
                phone=CAREGIVER_PHONE,
                relationship="Con gái",
                link_code="RPT123",
            )
            # Bind link and set last_report_sent_at to 10 days ago (due for weekly report)
            await CaregiverRepository(db).bind_by_code("RPT123", 888888, now - timedelta(days=10))
            link_id = link.id

            med = Medication(name="Thuốc test", source_name="MANUAL", source_record_key="TEST-MED-KEY")
            db.add(med)
            await db.flush()

            rx = Prescription(
                patient_id=patient.id,
                doctor_id=None,
                diagnosis_note="Bệnh test",
                status="APPROVED",
                approved_at=now,
            )
            db.add(rx)
            await db.flush()

            item = PrescriptionItem(
                prescription_id=rx.id,
                medication_id=med.id,
                display_name="Thuốc test",
                dose_unit="viên",
                start_date=now.date() - timedelta(days=5),
                is_critical=True,
            )
            db.add(item)
            await db.flush()

            # Create dose history for patient
            db.add(ScheduledDose(
                patient_id=patient.id,
                prescription_item_id=item.id,
                original_scheduled_at=now - timedelta(days=2),
                current_scheduled_at=now - timedelta(days=2),
                status="TAKEN",
                taken_at=now - timedelta(days=2),
                dose_value=1,
                dose_unit="viên",
            ))
            db.add(ScheduledDose(
                patient_id=patient.id,
                prescription_item_id=item.id,
                original_scheduled_at=now - timedelta(days=1),
                current_scheduled_at=now - timedelta(days=1),
                status="MISSED",
                dose_value=1,
                dose_unit="viên",
            ))

    # Execute periodic report generator
    await _execute_send_caregiver_adherence_reports()

    async with AsyncSessionLocal() as db:
        deliveries = (await db.execute(
            select(NotificationDelivery).where(NotificationDelivery.caregiver_link_id == link_id)
        )).scalars().all()
        assert len(deliveries) == 1
        d = deliveries[0]
        assert d.template_code == "CG_REPORT"
        assert d.channel == "TELEGRAM"
        assert "Bác Hùng" in d.body
        assert "Tổng số liều: 2" in d.body
        assert "Đã uống: 1" in d.body
        assert "Quên/Bỏ lỡ: 1" in d.body
        assert "50.0%" in d.body

    assert len(enqueued_task_ids) == 1
    assert enqueued_task_ids[0] == str(deliveries[0].id)


@pytest.mark.asyncio
async def test_missed_dose_streak_creates_caregiver_notification(monkeypatch):
    enqueued_task_ids = []
    from src.modules.agents import tasks
    monkeypatch.setattr(tasks.send_notification_task, "delay", lambda d_id: enqueued_task_ids.append(d_id))

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        async with db.begin():
            patient = await AuthRepository(db).create_user(phone=PATIENT_PHONE, hashed_password=hash_password(PIN), role="PATIENT")
            await PatientRepository(db).create_patient_profile(user_id=patient.id, name="Bác Hùng")

            link = await CaregiverRepository(db).create_link(
                patient_id=patient.id,
                phone=CAREGIVER_PHONE,
                relationship="Con gái",
                link_code="MSD123",
            )
            await CaregiverRepository(db).bind_by_code("MSD123", 999999, now)
            link_id = link.id

            med = Medication(name="Amlodipine", source_name="MANUAL", source_record_key="TEST-AMLODIPINE-KEY")
            db.add(med)
            await db.flush()

            rx = Prescription(
                patient_id=patient.id,
                doctor_id=None,
                diagnosis_note="Tăng huyết áp",
                status="APPROVED",
                approved_at=now,
            )
            db.add(rx)
            await db.flush()

            item = PrescriptionItem(
                prescription_id=rx.id,
                medication_id=med.id,
                display_name="Amlodipine",
                dose_unit="viên",
                start_date=now.date() - timedelta(days=5),
                is_critical=True,
            )
            db.add(item)
            await db.flush()

            # Create 3 overdue doses that will be marked MISSED
            for i in range(3):
                dose_time = now - timedelta(hours=3 + i)
                db.add(ScheduledDose(
                    patient_id=patient.id,
                    prescription_item_id=item.id,
                    original_scheduled_at=dose_time,
                    current_scheduled_at=dose_time,
                    status="PENDING",
                    dose_value=1,
                    dose_unit="viên",
                    is_critical=True,
                ))

    async with AsyncSessionLocal() as db:
        service = MissedDoseScanService(
            db=db,
            scheduled_dose_repository=ScheduledDoseRepository(db),
            alert_repository=AlertRepository(db),
        )
        await service.run_scan()

    async with AsyncSessionLocal() as db:
        alerts = (await db.execute(select(Alert).where(Alert.patient_id == patient.id))).scalars().all()
        assert len(alerts) == 1

        deliveries = (await db.execute(
            select(NotificationDelivery).where(NotificationDelivery.caregiver_link_id == link_id)
        )).scalars().all()
        assert len(deliveries) == 1
        assert deliveries[0].template_code == "CG_MISSED_DOSE"
        assert deliveries[0].channel == "TELEGRAM"
        assert "Bác Hùng" in deliveries[0].body
        assert "3+ liều thuốc quan trọng" in deliveries[0].body

    assert len(enqueued_task_ids) == 1
