import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
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
        "timestamp": datetime.now(UTC).isoformat(),
        "data": {"patient_id": str(unrelated_patient_id)},
    }
    related = {
        "event_type": "routine.updated",
        "timestamp": datetime.now(UTC).isoformat(),
        "data": {"patient_id": str(related_patient_id)},
    }

    async def stream():
        yield unrelated
        yield related

    repository = AsyncMock()
    repository.get_patient_identity.side_effect = [None, object()]
    monkeypatch.setattr(DashboardEventService, "stream", staticmethod(stream))

    opened = 0

    @asynccontextmanager
    async def scope():
        nonlocal opened
        opened += 1
        yield repository

    frames = [
        frame async for frame in DashboardEventService.stream_for_dashboard_actor(
            {"sub": str(doctor_id), "role": "DOCTOR"}, scope,
        )
    ]

    # P-04: a fresh short session per frame check, not one held for the stream.
    assert opened == 2

    assert frames == [related]
    assert repository.get_patient_identity.await_args_list[0].args == (unrelated_patient_id,)
    assert repository.get_patient_identity.await_args_list[1].args == (related_patient_id,)
