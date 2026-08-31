"""Pins every value ck_alerts_triggered_by_type must accept.

0021_suspected_adverse_events and 0023_alerts_review_trigger are sibling
migration branches that each drop and recreate this constraint with their
own new value (ADVERSE_EVENT, ADHERENCE_REVIEW respectively) and no
dependency on each other. Whichever branch Alembic walks last wins — on this
deployment that silently dropped ADHERENCE_REVIEW, so every alert the
nightly graded-adherence review tried to write violated the CHECK constraint
(docs/adherence-review-fix-plan.md Defect 2, fixed by
0028_alerts_adherence_review_check_fix).

Nothing upstream of AlertRepository.create_alert validates these strings —
adherence_review/service.py and adverse_events.py pass Python literals
straight through, so the database CHECK constraint is the only gate. A test
against a mocked repository (see test_alert_service.py) cannot catch a branch
silently overwriting it; only a real write against the real constraint can.
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from src.core.database import AsyncSessionLocal, engine
from src.core.security import hash_password
from src.modules.adherence.models import Alert
from src.modules.adherence.repository import AlertRepository
from src.modules.auth.models import User
from src.modules.auth.repository import AuthRepository
from src.modules.patients.repository import PatientRepository

PATIENT_PHONE = "+84900900090"


async def _purge() -> None:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            ids = (await db.execute(select(User.id).where(User.phone == PATIENT_PHONE))).scalars().all()
            if not ids:
                return
            await db.execute(delete(Alert).where(Alert.patient_id.in_(ids)))
            await db.execute(delete(User).where(User.id.in_(ids)))


@pytest_asyncio.fixture(autouse=True)
async def _clean_slate():
    await engine.dispose()
    await _purge()
    yield
    await _purge()
    await engine.dispose()


async def _create_patient() -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await AuthRepository(db).create_user(
                phone=PATIENT_PHONE, hashed_password=hash_password("123456"), role="PATIENT"
            )
            await PatientRepository(db).create_patient_profile(user_id=user.id, name="Test Patient")
        return user.id


@pytest.mark.parametrize(
    "triggered_by_type,alert_type,severity",
    [
        # Written by AdherenceReviewService._persist_one for a DOCTOR_WARNING
        # or DOCTOR_ALERT action -- the exact write that was broken.
        ("ADHERENCE_REVIEW", "WARNING", "MEDIUM"),
        ("ADHERENCE_REVIEW", "RED_ALERT", "HIGH"),
        # Written by adherence/adverse_events.py and agents/tasks.py for a
        # patient-reported suspected side effect.
        ("ADVERSE_EVENT", "SUSPECTED_ADVERSE_EVENT", "MEDIUM"),
        # Pre-existing sources -- must keep working after the constraint
        # rewrite, not just the two new values.
        ("SOS_BUTTON", "RED_ALERT", "CRITICAL"),
        ("SEVERE_SYMPTOM", "RED_ALERT", "HIGH"),
        ("MISSED_DOSES", "WARNING", "MEDIUM"),
    ],
)
@pytest.mark.asyncio
async def test_create_alert_accepts_every_documented_trigger_and_type(
    triggered_by_type, alert_type, severity
):
    patient_id = await _create_patient()
    async with AsyncSessionLocal() as db:
        async with db.begin():
            alert = await AlertRepository(db).create_alert(
                patient_id=patient_id,
                triggered_by_type=triggered_by_type,
                alert_type=alert_type,
                severity=severity,
                message="test",
            )
        assert alert.triggered_by_type == triggered_by_type
        assert alert.alert_type == alert_type
