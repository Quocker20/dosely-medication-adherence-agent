"""P-08: the blocking firebase_admin call must not run on the event loop thread."""
import threading
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.modules.agents.tasks import _execute_send_notification


@pytest.mark.asyncio
async def test_fcm_send_runs_in_a_worker_thread():
    delivery = SimpleNamespace(
        id=uuid.uuid4(),
        recipient_user_id=uuid.uuid4(),
        title="t",
        body="b",
        status="SENDING",
        template_code="ADHERENCE_SUGGESTION",
        scheduled_at=datetime.now(UTC),
        channel="PUSH",
        caregiver_link_id=None,
        attempt_no=1,
    )
    session = MagicMock()
    session.commit = AsyncMock()
    seen = {}

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    def fake_send(**kwargs):
        seen["thread"] = threading.current_thread()
        return True, []

    repo = AsyncMock()
    repo.claim_delivery.return_value = delivery
    repo.get_active_fcm_tokens.return_value = ["tok"]
    with (
        patch("src.modules.agents.tasks.task_session", lambda: _Ctx()),
        patch("src.modules.agents.tasks.NotificationRepository", return_value=repo),
        patch("src.modules.agents.tasks.FCMService.send_push_notification", side_effect=fake_send),
    ):
        await _execute_send_notification(str(delivery.id))

    assert seen["thread"] is not threading.main_thread()
    repo.update_delivery_status.assert_awaited_once_with(delivery.id, "SENT")
