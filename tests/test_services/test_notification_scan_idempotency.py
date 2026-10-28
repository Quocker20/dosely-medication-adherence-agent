"""O-03: overlapping scans must not trip the UNIQUE(idempotency_key) constraint."""
import asyncio
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

from src.core.database import AsyncSessionLocal, engine
from src.core.security import hash_password
from src.modules.adherence.models import NotificationDelivery
from src.modules.adherence.repository import NotificationRepository
from src.modules.auth.models import User
from src.modules.auth.repository import AuthRepository
from src.modules.patients.models import PatientProfile
from src.modules.patients.repository import PatientRepository

PHONE = "+84900500101"


async def _cleanup() -> None:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            ids = (await db.execute(select(User.id).where(User.phone == PHONE))).scalars().all()
            if ids:
                await db.execute(delete(NotificationDelivery).where(NotificationDelivery.recipient_user_id.in_(ids)))
                await db.execute(delete(PatientProfile).where(PatientProfile.user_id.in_(ids)))
                await db.execute(delete(User).where(User.id.in_(ids)))


@pytest_asyncio.fixture(autouse=True)
async def _setup():
    await _cleanup()
    yield
    await _cleanup()
    await engine.dispose()


async def _make_patient() -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await AuthRepository(db).create_user(phone=PHONE, hashed_password=hash_password("123456"), role="PATIENT")
            await PatientRepository(db).create_patient_profile(user_id=user.id, name="Bác An")
            return user.id


def _kwargs(patient_id: uuid.UUID, key: str) -> dict:
    return {
        "recipient_user_id": patient_id,
        "channel": "APP_NOTIFICATION",
        "template_code": "DOSE_REMINDER_GROUPED",
        "scheduled_at": datetime(2026, 8, 19, 14, 0, tzinfo=UTC),
        "title": "t",
        "body": "b",
        "scheduled_dose_ids": [],
        "metadata": {},
        "idempotency_key": key,
    }


@pytest.mark.asyncio
async def test_overlapping_creates_with_same_key_yield_one_row_and_no_error():
    patient_id = await _make_patient()
    key = f"notif:test:{uuid.uuid4()}"

    async def scan() -> tuple[uuid.UUID, bool]:
        async with AsyncSessionLocal() as db:
            repo = NotificationRepository(db)
            delivery, created = await repo.create_grouped_delivery(**_kwargs(patient_id, key))
            # Hold the transaction open briefly so the other scan's INSERT
            # really collides with an uncommitted row.
            await asyncio.sleep(0.3)
            await db.commit()
            return delivery.id, created

    (id_a, created_a), (id_b, created_b) = await asyncio.gather(scan(), scan())

    assert id_a == id_b
    assert sorted([created_a, created_b]) == [False, True]
    async with AsyncSessionLocal() as db:
        count = (
            await db.execute(
                select(func.count()).select_from(NotificationDelivery).where(NotificationDelivery.idempotency_key == key)
            )
        ).scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_second_sequential_create_returns_existing_row():
    patient_id = await _make_patient()
    key = f"notif:test:{uuid.uuid4()}"
    async with AsyncSessionLocal() as db:
        repo = NotificationRepository(db)
        first, created_first = await repo.create_grouped_delivery(**_kwargs(patient_id, key))
        second, created_second = await repo.create_grouped_delivery(**_kwargs(patient_id, key))
        await db.commit()
    assert (created_first, created_second) == (True, False)
    assert first.id == second.id
