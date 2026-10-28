"""Real-DB seeding helpers shared by the notification-pipeline tests (Area 5)."""
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select

from src.core.database import AsyncSessionLocal
from src.core.security import hash_password
from src.modules.adherence.models import NotificationDelivery
from src.modules.admin.models import DoctorProfile
from src.modules.admin.repository import DoctorRepository
from src.modules.agents.models import ScheduledDose
from src.modules.auth.models import User, UserDevice
from src.modules.auth.repository import AuthRepository
from src.modules.patients.models import PatientProfile
from src.modules.patients.repository import PatientRepository
from src.modules.prescriptions.models import Prescription, PrescriptionItem


async def purge(phones: list[str]) -> None:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            ids = (await db.execute(select(User.id).where(User.phone.in_(phones)))).scalars().all()
            if not ids:
                return
            await db.execute(delete(NotificationDelivery).where(NotificationDelivery.recipient_user_id.in_(ids)))
            await db.execute(delete(UserDevice).where(UserDevice.user_id.in_(ids)))
            await db.execute(delete(ScheduledDose).where(ScheduledDose.patient_id.in_(ids)))
            rx_ids = (
                (
                    await db.execute(
                        select(Prescription.id).where(Prescription.patient_id.in_(ids) | Prescription.doctor_id.in_(ids))
                    )
                )
                .scalars()
                .all()
            )
            if rx_ids:
                await db.execute(delete(PrescriptionItem).where(PrescriptionItem.prescription_id.in_(rx_ids)))
                await db.execute(delete(Prescription).where(Prescription.id.in_(rx_ids)))
            await db.execute(delete(PatientProfile).where(PatientProfile.user_id.in_(ids)))
            await db.execute(delete(DoctorProfile).where(DoctorProfile.user_id.in_(ids)))
            await db.execute(delete(User).where(User.id.in_(ids)))


async def create_doctor(phone: str, license_no: str) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await AuthRepository(db).create_user(
                phone=phone, hashed_password=hash_password("123456"), role="DOCTOR"
            )
            await DoctorRepository(db).create_doctor_profile(user_id=user.id, name="Dr Seed", license_no=license_no)
            return user.id


async def create_patient(phone: str, timezone: str = "Asia/Ho_Chi_Minh") -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await AuthRepository(db).create_user(
                phone=phone, hashed_password=hash_password("123456"), role="PATIENT"
            )
            await PatientRepository(db).create_patient_profile(user_id=user.id, name="Bac An", timezone=timezone)
            return user.id


async def create_doses(
    patient_id: uuid.UUID, doctor_id: uuid.UUID, offsets: list[timedelta], *, now: datetime | None = None
) -> list[uuid.UUID]:
    """One approved prescription and a PENDING dose at now+offset for each offset."""
    now = now or datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        async with db.begin():
            rx = Prescription(patient_id=patient_id, doctor_id=doctor_id, status="APPROVED")
            db.add(rx)
            await db.flush()
            item = PrescriptionItem(
                prescription_id=rx.id,
                display_name="Amlodipin 5mg",
                dose_unit="VIEN",
                morning_dose=1,
                start_date=date.today(),
            )
            db.add(item)
            await db.flush()
            ids = []
            for offset in offsets:
                at = now + offset
                dose = ScheduledDose(
                    prescription_item_id=item.id,
                    patient_id=patient_id,
                    original_scheduled_at=at,
                    current_scheduled_at=at,
                    status="PENDING",
                )
                db.add(dose)
                await db.flush()
                ids.append(dose.id)
            return ids


async def add_device(user_id: uuid.UUID, token: str) -> None:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            db.add(UserDevice(user_id=user_id, fcm_token=token, is_active=True))
