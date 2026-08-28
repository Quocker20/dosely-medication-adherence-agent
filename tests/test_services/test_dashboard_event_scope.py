import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.modules.dashboard.service import DashboardEventService


@pytest.mark.asyncio
async def test_doctor_stream_drops_frames_for_patients_outside_their_care(monkeypatch):
    doctor_id = uuid.uuid4()
    unrelated_patient_id = uuid.uuid4()
    related_patient_id = uuid.uuid4()
    unrelated = {
        "event_type": "routine.updated",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {"patient_id": str(unrelated_patient_id)},
    }
    related = {
        "event_type": "routine.updated",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {"patient_id": str(related_patient_id)},
    }

    async def stream():
        yield unrelated
        yield related

    repository = AsyncMock()
    repository.get_patient_identity.side_effect = [None, object()]
    monkeypatch.setattr(DashboardEventService, "stream", staticmethod(stream))

    frames = [
        frame async for frame in DashboardEventService.stream_for_dashboard_actor(
            {"sub": str(doctor_id), "role": "DOCTOR"}, repository,
        )
    ]

    assert frames == [related]
    assert repository.get_patient_identity.await_args_list[0].args == (unrelated_patient_id,)
    assert repository.get_patient_identity.await_args_list[1].args == (related_patient_id,)
