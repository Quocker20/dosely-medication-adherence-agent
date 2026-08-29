"""GET /patients/{id}/adherence-reviews access scoping, and
POST /admin/adherence-reviews/run's role gate + task dispatch.
"""
import uuid
from datetime import date, timedelta
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from src.core.database import AsyncSessionLocal, engine
from src.core.security import hash_password
from src.modules.adherence.models import Alert, HealthSurvey
from src.modules.adherence_review.models import AdherenceReview
from src.modules.agents.models import ScheduledDose
from src.modules.auth.models import User
from src.modules.auth.repository import AuthRepository
from src.modules.patients.models import CaregiverLink, PatientProfile
from src.modules.patients.repository import PatientRepository
from src.modules.prescriptions.models import Prescription

DOCTOR_PHONE = "+84900900001"
OTHER_DOCTOR_PHONE = "+84900900002"
ADMIN_PHONE = "+84900900003"
PATIENT_PHONE = "+84900900010"
CAREGIVER_PHONE = "+84900900011"
PIN = "123456"

_TEST_PHONES = [DOCTOR_PHONE, OTHER_DOCTOR_PHONE, ADMIN_PHONE, PATIENT_PHONE, CAREGIVER_PHONE]


async def _purge_test_data() -> None:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            ids = (await db.execute(select(User.id).where(User.phone.in_(_TEST_PHONES)))).scalars().all()
            if not ids:
                return
            await db.execute(delete(AdherenceReview).where(AdherenceReview.patient_id.in_(ids)))
            await db.execute(delete(ScheduledDose).where(ScheduledDose.patient_id.in_(ids)))
            await db.execute(delete(Alert).where(Alert.patient_id.in_(ids)))
            await db.execute(delete(HealthSurvey).where(HealthSurvey.patient_id.in_(ids)))
            await db.execute(delete(CaregiverLink).where(CaregiverLink.patient_id.in_(ids)))
            await db.execute(delete(Prescription).where(Prescription.patient_id.in_(ids)))
            await db.execute(delete(Prescription).where(Prescription.doctor_id.in_(ids)))
            await db.execute(delete(PatientProfile).where(PatientProfile.user_id.in_(ids)))
            await db.execute(delete(User).where(User.id.in_(ids)))


@pytest_asyncio.fixture(autouse=True)
async def _clean_slate():
    await engine.dispose()
    await _purge_test_data()
    yield
    await _purge_test_data()
    await engine.dispose()


async def _create_doctor(phone: str) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            from src.modules.admin.repository import DoctorRepository

            user = await AuthRepository(db).create_user(phone=phone, hashed_password=hash_password(PIN), role="DOCTOR")
            await DoctorRepository(db).create_doctor_profile(user_id=user.id, name="Dr Test", license_no=f"LIC-{phone[-4:]}")
        return user.id


async def _create_admin(phone: str) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await AuthRepository(db).create_user(phone=phone, hashed_password=hash_password(PIN), role="ADMIN")
        return user.id


async def _create_patient(phone: str) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await AuthRepository(db).create_user(phone=phone, hashed_password=hash_password(PIN), role="PATIENT")
            await PatientRepository(db).create_patient_profile(user_id=user.id, name="Test Patient")
        return user.id


async def _create_caregiver(phone: str, patient_id: uuid.UUID) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await AuthRepository(db).create_user(phone=phone, hashed_password=hash_password(PIN), role="CAREGIVER")
            db.add(CaregiverLink(patient_id=patient_id, caregiver_user_id=user.id, status="ACTIVE", channels=["APP_NOTIFICATION"]))
        return user.id


async def _create_prescription(patient_id: uuid.UUID, doctor_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            db.add(Prescription(patient_id=patient_id, doctor_id=doctor_id, status="APPROVED"))


async def _add_review(patient_id: uuid.UUID, review_date: date) -> None:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            db.add(
                AdherenceReview(
                    patient_id=patient_id,
                    review_date=review_date,
                    window_start=review_date - timedelta(days=7),
                    window_end=review_date - timedelta(days=1),
                    severity="MODERATE",
                    days_in_severity=1,
                    remedy_class="UNCLEAR",
                    action_taken="DOCTOR_WARNING",
                    indicators={"total": 10, "taken": 6, "skipped": 0, "missed": 4, "critical_missed": 0},
                )
            )


async def _login(client, phone: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"phone": phone, "password": PIN})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


class TestListPatientAdherenceReviews:
    @pytest.mark.asyncio
    async def test_requires_authentication(self, client):
        patient_id = await _create_patient(PATIENT_PHONE)
        response = await client.get(f"/api/v1/patients/{patient_id}/adherence-reviews")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_patient_sees_their_own_review(self, client):
        patient_id = await _create_patient(PATIENT_PHONE)
        await _add_review(patient_id, date.today())
        headers = await _login(client, PATIENT_PHONE)

        response = await client.get(f"/api/v1/patients/{patient_id}/adherence-reviews", headers=headers)
        assert response.status_code == 200
        content = response.json()["data"]["content"]
        assert len(content) == 1
        assert content[0]["patient_id"] == str(patient_id)
        assert content[0]["severity"] == "MODERATE"
        assert content[0]["action_taken"] == "DOCTOR_WARNING"
        assert content[0]["indicators"]["total"] == 10

    @pytest.mark.asyncio
    async def test_doctor_who_prescribed_sees_it(self, client):
        doctor_id = await _create_doctor(DOCTOR_PHONE)
        patient_id = await _create_patient(PATIENT_PHONE)
        await _create_prescription(patient_id, doctor_id)
        await _add_review(patient_id, date.today())
        headers = await _login(client, DOCTOR_PHONE)

        response = await client.get(f"/api/v1/patients/{patient_id}/adherence-reviews", headers=headers)
        assert response.status_code == 200
        assert response.json()["data"]["total_elements"] == 1

    @pytest.mark.asyncio
    async def test_active_caregiver_sees_it(self, client):
        patient_id = await _create_patient(PATIENT_PHONE)
        await _create_caregiver(CAREGIVER_PHONE, patient_id)
        await _add_review(patient_id, date.today())
        headers = await _login(client, CAREGIVER_PHONE)

        response = await client.get(f"/api/v1/patients/{patient_id}/adherence-reviews", headers=headers)
        assert response.status_code == 200
        assert response.json()["data"]["total_elements"] == 1

    @pytest.mark.asyncio
    async def test_unrelated_doctor_gets_an_empty_page_not_403(self, client):
        """Out-of-scope must be indistinguishable from empty history --
        never a 403/404 that would confirm the patient_id is real."""
        await _create_doctor(OTHER_DOCTOR_PHONE)
        patient_id = await _create_patient(PATIENT_PHONE)
        await _add_review(patient_id, date.today())
        headers = await _login(client, OTHER_DOCTOR_PHONE)

        response = await client.get(f"/api/v1/patients/{patient_id}/adherence-reviews", headers=headers)
        assert response.status_code == 200
        assert response.json()["data"]["total_elements"] == 0
        assert response.json()["data"]["content"] == []

    @pytest.mark.asyncio
    async def test_admin_role_is_rejected(self, client):
        """ADMIN is not in AdherenceReaderDep -- this endpoint is
        patient-context only, unlike the platform-wide dashboard."""
        await _create_admin(ADMIN_PHONE)
        patient_id = await _create_patient(PATIENT_PHONE)
        headers = await _login(client, ADMIN_PHONE)

        response = await client.get(f"/api/v1/patients/{patient_id}/adherence-reviews", headers=headers)
        assert response.status_code == 403


class TestTriggerAdherenceReviewRun:
    @pytest.mark.asyncio
    async def test_requires_admin_role(self, client):
        await _create_doctor(DOCTOR_PHONE)
        headers = await _login(client, DOCTOR_PHONE)
        response = await client.post("/api/v1/admin/adherence-reviews/run", headers=headers)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_triggers_the_scan_task_and_gets_202(self, client):
        await _create_admin(ADMIN_PHONE)
        headers = await _login(client, ADMIN_PHONE)

        with patch("src.modules.adherence_review.router.celery_app") as mock_celery:
            response = await client.post("/api/v1/admin/adherence-reviews/run", headers=headers)

        assert response.status_code == 202
        mock_celery.send_task.assert_called_once_with("adherence_review.scan")
