import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.adherence.repository import AdherenceLogRepository


@pytest.mark.asyncio
async def test_snooze_dissolves_the_entire_notification_group() -> None:
    group_id = uuid.uuid4()
    updated_dose = SimpleNamespace(notification_group_id=group_id)
    first_result = MagicMock()
    first_result.scalar_one_or_none.return_value = updated_dose
    second_result = MagicMock()
    db = SimpleNamespace(execute=AsyncMock(side_effect=[first_result, second_result]))
    repository = AdherenceLogRepository(db)

    result = await repository.apply_dose_action_cas(
        dose_id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        action="SNOOZE",
        snooze_minutes=10,
    )

    assert result is updated_dose
    assert db.execute.await_count == 2
