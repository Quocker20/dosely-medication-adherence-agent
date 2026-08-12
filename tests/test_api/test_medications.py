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
from src.modules.prescriptions.models import Medication


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


async def _cleanup_doctor(doctor_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await db.execute(delete(DoctorProfile).where(DoctorProfile.user_id == doctor_id))
            await db.execute(delete(User).where(User.id == doctor_id))


async def _login(client, phone: str, pin: str) -> str:
    response = await client.post(
        "/api/v1/auth/login", json={"phone": phone, "password": pin}
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_medications_require_authentication(client):
    response = await client.get("/api/v1/medications")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_medication_detail_not_found(client):
    doctor_id = await _create_doctor(
        "+84900500010", "555555", "Dr Slice3 Med", "LIC-SLICE3-MED"
    )
    try:
        token = await _login(client, "+84900500010", "555555")
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.get(f"/api/v1/medications/{uuid.uuid4()}", headers=headers)
        assert response.status_code == 404
    finally:
        await _cleanup_doctor(doctor_id)


@pytest.mark.asyncio
async def test_medication_list_and_detail_returns_active_only(client):
    doctor_id = await _create_doctor(
        "+84900500011", "666666", "Dr Slice3 Med2", "LIC-SLICE3-MED2"
    )
    med_id = None
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                med = Medication(
                    name="ZzzTestParacetamol",
                    source_name="TEST_SOURCE",
                    is_active=True,
                )
                db.add(med)
                await db.flush()
                med_id = med.id

        token = await _login(client, "+84900500011", "666666")
        headers = {"Authorization": f"Bearer {token}"}

        list_response = await client.get(
            "/api/v1/medications", params={"search": "ZzzTestParacetamol"}, headers=headers
        )
        assert list_response.status_code == 200
        content = list_response.json()["data"]["content"]
        assert any(item["id"] == str(med_id) for item in content)

        detail_response = await client.get(f"/api/v1/medications/{med_id}", headers=headers)
        assert detail_response.status_code == 200
        assert detail_response.json()["data"]["name"] == "ZzzTestParacetamol"
    finally:
        if med_id is not None:
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await db.execute(delete(Medication).where(Medication.id == med_id))
        await _cleanup_doctor(doctor_id)
