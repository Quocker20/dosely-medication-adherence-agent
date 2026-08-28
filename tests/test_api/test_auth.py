import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from src.core.database import AsyncSessionLocal, engine


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_pool():
    """See tests/test_api/test_patients.py for why this is needed: a pooled
    asyncpg connection created under a previous test's event loop cannot be
    reused under the next one."""
    yield
    await engine.dispose()


from src.core.security import hash_password
from src.modules.admin.models import DoctorProfile
from src.modules.admin.repository import DoctorRepository
from src.modules.auth.models import User
from src.modules.auth.repository import AuthRepository


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


async def _create_patient_via_doctor(client, doctor_headers: dict, phone: str, name: str) -> tuple:
    response = await client.post(
        "/api/v1/doctors/patients",
        json={"phone": phone, "name": name},
        headers=doctor_headers,
    )
    assert response.status_code == 201
    body = response.json()["data"]
    return uuid.UUID(body["patient"]["user_id"]), body["temp_password"]


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


async def _login(client, phone: str, pin: str) -> dict:
    response = await client.post(
        "/api/v1/auth/login", json={"phone": phone, "password": pin}
    )
    assert response.status_code == 200
    return response.json()["data"]


async def _get_user(user_id: uuid.UUID) -> User:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one()


@pytest.mark.asyncio
async def test_login_reports_must_change_password_and_need_onboarding_for_new_patient(client):
    doctor_id = await _create_doctor(
        "+84900600001", "111111", "Dr Auth A", "LIC-AUTH-A"
    )
    doctor_body = await _login(client, "+84900600001", "111111")
    doctor_headers = {"Authorization": f"Bearer {doctor_body['access_token']}"}
    patient_phone = "+84900600099"
    try:
        patient_id, temp_pin = await _create_patient_via_doctor(
            client, doctor_headers, patient_phone, "Patient Auth"
        )

        login_body = await _login(client, patient_phone, temp_pin)
        assert login_body["must_change_password"] is True
        assert login_body["need_onboarding"] is True
    finally:
        await _cleanup([doctor_id], [patient_phone])


@pytest.mark.asyncio
async def test_doctor_change_password_clears_need_onboarding(client):
    doctor_id = await _create_doctor(
        "+84900600002", "222222", "Dr Auth B", "LIC-AUTH-B"
    )
    try:
        login_body = await _login(client, "+84900600002", "222222")
        assert login_body["must_change_password"] is True
        assert login_body["need_onboarding"] is True
        headers = {"Authorization": f"Bearer {login_body['access_token']}"}

        response = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "222222", "new_password": "333333"},
            headers=headers,
        )
        assert response.status_code == 200

        relogin_body = await _login(client, "+84900600002", "333333")
        assert relogin_body["must_change_password"] is False
        assert relogin_body["need_onboarding"] is False
    finally:
        await _cleanup([doctor_id], [])


@pytest.mark.asyncio
async def test_patient_change_password_does_not_clear_need_onboarding(client):
    """The exact bug this migration fixes: a PATIENT who changes their temp
    PIN but closes the app before finishing onboarding must still be routed
    back to onboarding on the next login -- need_onboarding must not have
    been cleared by the PIN change itself."""
    doctor_id = await _create_doctor(
        "+84900600003", "333333", "Dr Auth C", "LIC-AUTH-C"
    )
    doctor_body = await _login(client, "+84900600003", "333333")
    doctor_headers = {"Authorization": f"Bearer {doctor_body['access_token']}"}
    patient_phone = "+84900600098"
    try:
        patient_id, temp_pin = await _create_patient_via_doctor(
            client, doctor_headers, patient_phone, "Patient Auth C"
        )
        login_body = await _login(client, patient_phone, temp_pin)
        headers = {"Authorization": f"Bearer {login_body['access_token']}"}

        response = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": temp_pin, "new_password": "999999"},
            headers=headers,
        )
        assert response.status_code == 200

        # create_refresh_token's JWT truncates iat/exp to whole seconds with
        # no jti, so a same-user re-login within the same second produces an
        # identical token -> identical refresh_tokens.token_hash -> unique
        # violation. Pre-existing issue, unrelated to need_onboarding; sidestep
        # it here rather than fold an unrelated fix into this change.
        await asyncio.sleep(1.1)

        # Simulate closing the app right after the PIN change, before
        # touching onboarding, then relaunching.
        relogin_body = await _login(client, patient_phone, "999999")
        assert relogin_body["must_change_password"] is False
        assert relogin_body["need_onboarding"] is True
    finally:
        await _cleanup([doctor_id], [patient_phone])


@pytest.mark.asyncio
async def test_onboard_patient_clears_need_onboarding(client):
    doctor_id = await _create_doctor(
        "+84900600004", "444444", "Dr Auth D", "LIC-AUTH-D"
    )
    doctor_body = await _login(client, "+84900600004", "444444")
    doctor_headers = {"Authorization": f"Bearer {doctor_body['access_token']}"}
    patient_phone = "+84900600097"
    try:
        patient_id, temp_pin = await _create_patient_via_doctor(
            client, doctor_headers, patient_phone, "Patient Auth D"
        )
        login_body = await _login(client, patient_phone, temp_pin)
        patient_headers = {"Authorization": f"Bearer {login_body['access_token']}"}

        response = await client.post(
            "/api/v1/patients/me/profile",
            json={
                "name": "Patient Real Name",
                "routine": {
                    "wake_time": "06:00:00",
                    "breakfast_time": "07:00:00",
                    "lunch_time": "12:00:00",
                    "dinner_time": "18:00:00",
                    "sleep_time": "22:00:00",
                },
            },
            headers=patient_headers,
        )
        assert response.status_code == 200

        user = await _get_user(patient_id)
        assert user.need_onboarding is False
    finally:
        await _cleanup([doctor_id], [patient_phone])


@pytest.mark.asyncio
async def test_routine_update_clears_need_onboarding_but_empty_put_does_not(client):
    doctor_id = await _create_doctor(
        "+84900600005", "555555", "Dr Auth E", "LIC-AUTH-E"
    )
    doctor_body = await _login(client, "+84900600005", "555555")
    doctor_headers = {"Authorization": f"Bearer {doctor_body['access_token']}"}
    patient_phone = "+84900600096"
    try:
        patient_id, temp_pin = await _create_patient_via_doctor(
            client, doctor_headers, patient_phone, "Patient Auth E"
        )
        login_body = await _login(client, patient_phone, temp_pin)
        patient_headers = {"Authorization": f"Bearer {login_body['access_token']}"}

        # Empty PUT: nothing changed, must not count as onboarding-complete.
        empty_response = await client.put(
            f"/api/v1/patients/{patient_id}/routine",
            json={},
            headers=patient_headers,
        )
        assert empty_response.status_code == 200
        user = await _get_user(patient_id)
        assert user.need_onboarding is True

        # Non-empty PUT: patient reviewed/edited the seeded defaults.
        response = await client.put(
            f"/api/v1/patients/{patient_id}/routine",
            json={"wake_time": "06:30:00"},
            headers=patient_headers,
        )
        assert response.status_code == 200
        user = await _get_user(patient_id)
        assert user.need_onboarding is False

        # Idempotent: a second non-empty PUT after the flag is already
        # cleared must not error (repository's need_onboarding predicate
        # makes it a no-op write).
        response2 = await client.put(
            f"/api/v1/patients/{patient_id}/routine",
            json={"wake_time": "07:00:00"},
            headers=patient_headers,
        )
        assert response2.status_code == 200
        user = await _get_user(patient_id)
        assert user.need_onboarding is False
    finally:
        await _cleanup([doctor_id], [patient_phone])
