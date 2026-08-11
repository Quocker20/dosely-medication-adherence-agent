import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete

from src.core.database import AsyncSessionLocal, engine


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_pool():
    """Dispose pooled asyncpg connections after each test.

    pytest-asyncio gives each test function a fresh event loop; a pooled
    asyncpg connection created under a previous test's loop cannot be reused
    under the next one ("another operation is in progress"). Disposing forces
    a fresh connection bound to the current loop on next use.
    """
    yield
    await engine.dispose()
from src.core.security import hash_password
from src.modules.admin.models import DoctorProfile
from src.modules.admin.repository import DoctorRepository
from src.modules.auth.models import User
from src.modules.auth.repository import AuthRepository
from src.modules.prescriptions.models import Prescription


async def _create_doctor(phone: str, pin: str, name: str, license_no: str) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            auth_repo = AuthRepository(db)
            doctor_repo = DoctorRepository(db)
            user = await auth_repo.create_user(
                phone=phone, hashed_password=hash_password(pin), role="DOCTOR"
            )
            await doctor_repo.create_doctor_profile(
                user_id=user.id, name=name, license_no=license_no
            )
        return user.id


async def _cleanup(doctor_ids: list[uuid.UUID], patient_phones: list[str]) -> None:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            for phone in patient_phones:
                await db.execute(delete(User).where(User.phone == phone))
            if doctor_ids:
                await db.execute(
                    delete(DoctorProfile).where(DoctorProfile.user_id.in_(doctor_ids))
                )
                await db.execute(delete(User).where(User.id.in_(doctor_ids)))


async def _create_prescription(patient_id: uuid.UUID, doctor_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            db.add(Prescription(patient_id=patient_id, doctor_id=doctor_id))


async def _login(client, phone: str, pin: str) -> str:
    response = await client.post(
        "/api/v1/auth/login", json={"phone": phone, "password": pin}
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_create_patient_success_and_duplicate_phone(client):
    doctor_id = await _create_doctor(
        "+84900500001", "111111", "Dr Slice3 A", "LIC-SLICE3-A"
    )
    patient_phone = "+84900500099"
    try:
        token = await _login(client, "+84900500001", "111111")
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.post(
            "/api/v1/doctors/patients",
            json={"phone": patient_phone, "name": "Patient Slice3", "sex": "FEMALE"},
            headers=headers,
        )
        assert response.status_code == 201
        body = response.json()["data"]
        assert body["patient"]["phone"] == patient_phone
        assert body["patient"]["role"] == "PATIENT"
        assert len(body["temp_password"]) == 6

        dup_response = await client.post(
            "/api/v1/doctors/patients",
            json={"phone": patient_phone, "name": "Duplicate"},
            headers=headers,
        )
        assert dup_response.status_code == 409
    finally:
        await _cleanup([doctor_id], [patient_phone])


@pytest.mark.asyncio
async def test_create_patient_invalid_phone_rejected(client):
    doctor_id = await _create_doctor(
        "+84900500002", "222222", "Dr Slice3 B", "LIC-SLICE3-B"
    )
    try:
        token = await _login(client, "+84900500002", "222222")
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.post(
            "/api/v1/doctors/patients",
            json={"phone": "not-a-phone", "name": "Bad Phone"},
            headers=headers,
        )
        assert response.status_code == 422
    finally:
        await _cleanup([doctor_id], [])


@pytest.mark.asyncio
async def test_patient_roster_is_scoped_by_prescription(client):
    doctor1_id = await _create_doctor(
        "+84900500003", "333333", "Dr Slice3 C1", "LIC-SLICE3-C1"
    )
    doctor2_id = await _create_doctor(
        "+84900500004", "444444", "Dr Slice3 C2", "LIC-SLICE3-C2"
    )
    patient_phone = "+84900500098"
    try:
        token1 = await _login(client, "+84900500003", "333333")
        token2 = await _login(client, "+84900500004", "444444")
        headers1 = {"Authorization": f"Bearer {token1}"}
        headers2 = {"Authorization": f"Bearer {token2}"}

        create_response = await client.post(
            "/api/v1/doctors/patients",
            json={"phone": patient_phone, "name": "Scoped Patient"},
            headers=headers1,
        )
        assert create_response.status_code == 201
        patient_id = create_response.json()["data"]["patient"]["user_id"]

        # No prescription yet from either doctor: roster is empty for both.
        list1 = await client.get("/api/v1/doctors/patients", headers=headers1)
        assert list1.json()["data"]["total_elements"] == 0

        # get_patient stays unscoped by prescription — either doctor can fetch by id.
        get_other = await client.get(
            f"/api/v1/doctors/patients/{patient_id}", headers=headers2
        )
        assert get_other.status_code == 200

        await _create_prescription(uuid.UUID(patient_id), doctor1_id)

        list1 = await client.get("/api/v1/doctors/patients", headers=headers1)
        phones1 = [item["phone"] for item in list1.json()["data"]["content"]]
        assert patient_phone in phones1

        list2 = await client.get("/api/v1/doctors/patients", headers=headers2)
        assert list2.json()["data"]["total_elements"] == 0
    finally:
        await _cleanup([doctor1_id, doctor2_id], [patient_phone])


@pytest.mark.asyncio
async def test_patient_endpoints_require_doctor_role(client):
    response = await client.post(
        "/api/v1/doctors/patients",
        json={"phone": "+84900500097", "name": "No Auth"},
    )
    assert response.status_code == 401
