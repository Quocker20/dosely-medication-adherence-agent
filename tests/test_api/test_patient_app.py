"""Patient mobile app: schedule read and dose-action contract.

These used to run against the in-memory demo app (legacy ids such as ``p-02``,
no auth). That app is gone: ids are UUIDs and every route needs a bearer
token. Idempotent dose actions, survey alerts, SOS and the adherence summary
are pinned against the real stack in test_alerts.py; this module keeps the two
mobile-facing contracts that had no equivalent there -- the schedule read and
the Idempotency-Key / append-only rules on dose actions.
"""
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio

from src.core.database import engine
from tests.test_api.test_alerts import (
    OTHER_PATIENT_PHONE,
    PATIENT_PHONE,
    _create_doctor,
    _create_dose,
    _create_patient,
    _idem,
    _login,
    _purge,
)


@pytest_asyncio.fixture(autouse=True)
async def _clean_slate():
    """Same fixed phones as test_alerts, so reuse its purge on both sides."""
    await engine.dispose()
    await _purge()
    yield
    await _purge()
    await engine.dispose()


async def _prime_schedule() -> tuple:
    doctor_id = await _create_doctor()
    patient_id = await _create_patient()
    dose_id = await _create_dose(patient_id, doctor_id)
    return doctor_id, patient_id, dose_id


def _local_date_of_default_dose():
    """_create_dose defaults to 30 minutes ago; the schedule is read by the
    patient's local calendar day, so derive the date the same way."""
    when = datetime.now(UTC) - timedelta(minutes=30)
    return when.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date()


@pytest.mark.asyncio
async def test_schedule_requires_authentication(client):
    _, patient_id, _ = await _prime_schedule()

    response = await client.get(f"/api/v1/patients/{patient_id}/schedules")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_patient_schedule_is_ready_for_mobile(client):
    _, patient_id, dose_id = await _prime_schedule()
    headers = await _login(client, PATIENT_PHONE)

    response = await client.get(
        f"/api/v1/patients/{patient_id}/schedules",
        params={"date": _local_date_of_default_dose().isoformat()},
        headers=headers,
    )

    assert response.status_code == 200
    schedule = response.json()["data"]
    assert schedule["patient_id"] == str(patient_id)
    assert [d["scheduled_dose_id"] for d in schedule["doses"]] == [str(dose_id)]
    dose = schedule["doses"][0]
    assert dose["status"] == "PENDING"
    assert dose["medication_name"] == "Amlodipin 5mg"


@pytest.mark.asyncio
async def test_schedule_of_another_patient_is_empty_not_leaked(client):
    _, patient_id, _ = await _prime_schedule()
    await _create_patient(OTHER_PATIENT_PHONE, "Bệnh nhân B")
    headers = await _login(client, OTHER_PATIENT_PHONE)

    response = await client.get(
        f"/api/v1/patients/{patient_id}/schedules",
        params={"date": _local_date_of_default_dose().isoformat()},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["doses"] == []


@pytest.mark.asyncio
async def test_dose_action_requires_idempotency_key(client):
    _, _, dose_id = await _prime_schedule()
    headers = await _login(client, PATIENT_PHONE)

    response = await client.post(
        f"/api/v1/scheduled-doses/{dose_id}/actions",
        json={"action": "TAKEN"},
        headers=headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_second_action_with_new_key_on_a_decided_dose_is_conflict(client):
    """Actions are append-only history: once a dose is TAKEN, a different
    intent under a fresh Idempotency-Key must not silently overwrite it."""
    _, _, dose_id = await _prime_schedule()
    headers = await _login(client, PATIENT_PHONE)

    first = await client.post(
        f"/api/v1/scheduled-doses/{dose_id}/actions",
        json={"action": "TAKEN", "note": "Đã uống sau bữa trưa"},
        headers={**headers, **_idem("app-dose-1")},
    )
    second = await client.post(
        f"/api/v1/scheduled-doses/{dose_id}/actions",
        json={"action": "SKIPPED"},
        headers={**headers, **_idem("app-dose-2")},
    )

    assert first.status_code == 201
    assert second.status_code == 409
