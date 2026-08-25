import uuid
from contextlib import asynccontextmanager
from datetime import datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.common.exceptions import NotFoundException
from src.modules.patients.schemas import UpdateRoutineRequest
from src.modules.patients.service import PatientService


class _TransactionDb:
    @asynccontextmanager
    async def begin(self):
        yield


def _service(patient_repository: MagicMock) -> PatientService:
    return PatientService(
        db=_TransactionDb(),
        patient_repository=patient_repository,
        doctor_repository=MagicMock(),
        audit_repository=MagicMock(),
        auth_repository=MagicMock(),
        caregiver_repository=MagicMock(),
    )


@pytest.mark.asyncio
async def test_update_routine_upserts_for_profile_without_existing_routine():
    patient_id = uuid.uuid4()
    saved = SimpleNamespace(
        id=uuid.uuid4(),
        patient_id=patient_id,
        wake_time=time(6, 30),
        breakfast_time=time(7, 0),
        lunch_time=time(12, 0),
        dinner_time=time(18, 30),
        sleep_time=time(22, 30),
        updated_at=datetime.now(timezone.utc),
    )
    repository = MagicMock()
    repository.upsert_routine = AsyncMock(return_value=saved)

    result = await _service(repository).update_routine(
        patient_id=patient_id,
        request=UpdateRoutineRequest(
            wake_time=saved.wake_time,
            breakfast_time=saved.breakfast_time,
            lunch_time=saved.lunch_time,
            dinner_time=saved.dinner_time,
            sleep_time=saved.sleep_time,
        ),
        actor_payload={"sub": str(patient_id), "role": "PATIENT"},
    )

    repository.upsert_routine.assert_awaited_once_with(
        patient_id=patient_id,
        updates={
            "wake_time": saved.wake_time,
            "breakfast_time": saved.breakfast_time,
            "lunch_time": saved.lunch_time,
            "dinner_time": saved.dinner_time,
            "sleep_time": saved.sleep_time,
        },
    )
    assert result.patient_id == patient_id
    assert result.wake_time == time(6, 30)


@pytest.mark.asyncio
async def test_update_routine_rejects_another_patient_without_writing():
    repository = MagicMock()
    repository.upsert_routine = AsyncMock()

    with pytest.raises(NotFoundException):
        await _service(repository).update_routine(
            patient_id=uuid.uuid4(),
            request=UpdateRoutineRequest(wake_time=time(6, 30)),
            actor_payload={"sub": str(uuid.uuid4()), "role": "PATIENT"},
        )

    repository.upsert_routine.assert_not_awaited()
