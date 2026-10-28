"""Real-DB check that the thin daily-summary task still rolls events up."""
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from src.core.database import AsyncSessionLocal, engine
from src.core.security import hash_password
from src.modules.adherence.models import Alert, SuspectedAdverseEvent
from src.modules.agents.tasks import _execute_daily_adverse_event_summary
from src.modules.auth.models import User
from src.modules.auth.repository import AuthRepository
from src.modules.patients.models import PatientProfile
from src.modules.patients.repository import PatientRepository

PHONE = "+84900400011"


async def _cleanup() -> None:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            ids = (await db.execute(select(User.id).where(User.phone == PHONE))).scalars().all()
            if ids:
                await db.execute(delete(SuspectedAdverseEvent).where(SuspectedAdverseEvent.patient_id.in_(ids)))
                await db.execute(delete(Alert).where(Alert.patient_id.in_(ids)))
                await db.execute(delete(PatientProfile).where(PatientProfile.user_id.in_(ids)))
                await db.execute(delete(User).where(User.id.in_(ids)))


@pytest_asyncio.fixture(autouse=True)
async def _setup():
    await _cleanup()
    yield
    await _cleanup()
    await engine.dispose()


@pytest.mark.asyncio
async def test_daily_summary_task_creates_alert_and_marks_events():
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await AuthRepository(db).create_user(phone=PHONE, hashed_password=hash_password("123456"), role="PATIENT")
            await PatientRepository(db).create_patient_profile(user_id=user.id, name="Bác Hùng")
            patient_id = user.id
            for symptom in ("ho", "chóng mặt"):
                db.add(SuspectedAdverseEvent(
                    patient_id=patient_id,
                    raw_text=symptom,
                    symptoms=[{"name": symptom}],
                    risk_level="LOW",
                    reported_at=now - timedelta(hours=1),
                ))

    await _execute_daily_adverse_event_summary()

    async with AsyncSessionLocal() as db:
        alerts = (await db.execute(select(Alert).where(Alert.patient_id == patient_id))).scalars().all()
        assert len(alerts) == 1
        assert alerts[0].alert_type == "SUSPECTED_ADVERSE_EVENT"
        events = (await db.execute(
            select(SuspectedAdverseEvent).where(SuspectedAdverseEvent.patient_id == patient_id)
        )).scalars().all()
        assert len(events) == 2
        assert all(e.daily_notified_at is not None and e.alert_id == alerts[0].id for e in events)
