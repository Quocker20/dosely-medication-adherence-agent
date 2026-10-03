import uuid
from datetime import datetime, timezone
import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from src.core.config import get_settings
from src.core.database import AsyncSessionLocal, engine
from src.core.security import hash_password
from src.modules.auth.models import User
from src.modules.auth.repository import AuthRepository
from src.modules.caregivers.models import CaregiverLink
from src.modules.patients.models import PatientProfile
from src.modules.patients.repository import PatientRepository

PATIENT_PHONE = "+84900600001"
OTHER_PATIENT_PHONE = "+84900600002"
ADMIN_PHONE = "+84900600003"
CAREGIVER_PHONE = "+84900600010"
PIN = "123456"
_TEST_PHONES = [PATIENT_PHONE, OTHER_PATIENT_PHONE, ADMIN_PHONE, CAREGIVER_PHONE]


@pytest_asyncio.fixture(autouse=True)
async def _setup(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "telegram_bot_username", "Dosely_bot")
    monkeypatch.setattr(settings, "telegram_enabled", False)

    async with AsyncSessionLocal() as db:
        async with db.begin():
            ids = (await db.execute(select(User.id).where(User.phone.in_(_TEST_PHONES)))).scalars().all()
            if ids:
                await db.execute(delete(CaregiverLink).where(CaregiverLink.patient_id.in_(ids)))
                await db.execute(delete(PatientProfile).where(PatientProfile.user_id.in_(ids)))
                await db.execute(delete(User).where(User.id.in_(ids)))
    yield
    await engine.dispose()


async def _create_patient(phone: str) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await AuthRepository(db).create_user(phone=phone, hashed_password=hash_password(PIN), role="PATIENT")
            await PatientRepository(db).create_patient_profile(user_id=user.id, name="Test Patient")
        return user.id


async def _create_admin(phone: str) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await AuthRepository(db).create_user(phone=phone, hashed_password=hash_password(PIN), role="ADMIN")
        return user.id


async def _login(client, phone: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"phone": phone, "password": PIN})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_create_caregiver_link_success(client):
    patient_id = await _create_patient(PATIENT_PHONE)
    headers = await _login(client, PATIENT_PHONE)

    response = await client.post(
        f"/api/v1/patients/{patient_id}/caregivers",
        json={"phone": CAREGIVER_PHONE, "relationship": "Con trai"},
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["patient_id"] == str(patient_id)
    assert data["phone"] == CAREGIVER_PHONE
    assert data["relationship"] == "Con trai"
    assert data["status"] == "PENDING_BINDING"
    assert len(data["link_code"]) == 6
    assert data["telegram_deep_link"] == f"https://t.me/Dosely_bot?start={data['link_code']}"


@pytest.mark.asyncio
async def test_create_caregiver_link_duplicate_returns_409(client):
    patient_id = await _create_patient(PATIENT_PHONE)
    headers = await _login(client, PATIENT_PHONE)

    res1 = await client.post(
        f"/api/v1/patients/{patient_id}/caregivers",
        json={"phone": CAREGIVER_PHONE, "relationship": "Con trai"},
        headers=headers,
    )
    assert res1.status_code == 201

    res2 = await client.post(
        f"/api/v1/patients/{patient_id}/caregivers",
        json={"phone": CAREGIVER_PHONE, "relationship": "Con trai"},
        headers=headers,
    )
    assert res2.status_code == 409


@pytest.mark.asyncio
async def test_create_caregiver_link_for_other_patient_returns_403(client):
    patient_id = await _create_patient(PATIENT_PHONE)
    other_patient_id = await _create_patient(OTHER_PATIENT_PHONE)
    headers = await _login(client, OTHER_PATIENT_PHONE)

    response = await client.post(
        f"/api/v1/patients/{patient_id}/caregivers",
        json={"phone": CAREGIVER_PHONE, "relationship": "Con trai"},
        headers=headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_caregiver_links_and_delete(client):
    patient_id = await _create_patient(PATIENT_PHONE)
    headers = await _login(client, PATIENT_PHONE)

    # Create link
    create_res = await client.post(
        f"/api/v1/patients/{patient_id}/caregivers",
        json={"phone": CAREGIVER_PHONE, "relationship": "Con trai"},
        headers=headers,
    )
    assert create_res.status_code == 201
    link_id = create_res.json()["data"]["id"]

    # List links
    list_res = await client.get(f"/api/v1/patients/{patient_id}/caregivers", headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.json()["data"]) == 1
    assert list_res.json()["data"][0]["id"] == link_id

    # Delete link
    del_res = await client.delete(f"/api/v1/patients/{patient_id}/caregivers/{link_id}", headers=headers)
    assert del_res.status_code == 200

    # List again -> empty
    list_after = await client.get(f"/api/v1/patients/{patient_id}/caregivers", headers=headers)
    assert list_after.status_code == 200
    assert len(list_after.json()["data"]) == 0
