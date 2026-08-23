"""Tests for grouped notifications and batch dose actions (Option A)."""
import uuid
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

import pytest

from src.common.exceptions import ConflictException, NotFoundException, ValidationException
from src.modules.adherence.models import AdherenceLog, NotificationDelivery, NotificationDoseItem
from src.modules.adherence.notification_service import NotificationDispatchService
from src.modules.adherence.schemas import (
    BatchRecordDoseActionRequest,
    BatchRecordDoseActionResponse,
)
from src.modules.adherence.service import AdherenceLogService
from src.modules.agents.models import ScheduledDose

PATIENT_ID = uuid.uuid4()
DOSE_ID_1 = uuid.uuid4()
DOSE_ID_2 = uuid.uuid4()
DOSE_ID_3 = uuid.uuid4()


class TestNotificationTextFormatting:
    def test_single_dose_formatting(self):
        # 14:00 UTC corresponds to 21:00 Asia/Ho_Chi_Minh (UTC+7)
        scheduled_at = datetime(2026, 8, 19, 14, 0, tzinfo=timezone.utc)
        doses = [
            {
                "scheduled_dose_id": DOSE_ID_1,
                "medication_name": "Paracetamol",
                "dose_value": Decimal("500"),
                "dose_unit": "mg",
            }
        ]
        title, body = NotificationDispatchService.format_notification_text(scheduled_at, doses)
        assert title == "Nhắc nhở uống thuốc (21:00)"
        assert "Paracetamol (500 mg)" in body

    def test_multiple_doses_consolidated_formatting(self):
        # 14:00 UTC corresponds to 21:00 Asia/Ho_Chi_Minh (UTC+7)
        scheduled_at = datetime(2026, 8, 19, 14, 0, tzinfo=timezone.utc)
        doses = [
            {
                "scheduled_dose_id": DOSE_ID_1,
                "medication_name": "Thuốc A",
                "dose_value": Decimal("1"),
                "dose_unit": "viên",
            },
            {
                "scheduled_dose_id": DOSE_ID_2,
                "medication_name": "Thuốc B",
                "dose_value": Decimal("2"),
                "dose_unit": "viên",
            },
            {
                "scheduled_dose_id": DOSE_ID_3,
                "medication_name": "Thuốc C",
                "dose_value": Decimal("1"),
                "dose_unit": "gói",
            },
        ]
        title, body = NotificationDispatchService.format_notification_text(scheduled_at, doses)
        assert title == "Nhắc nhở uống thuốc (21:00)"
        assert "3 loại thuốc" in body
        assert "Thuốc A (1 viên)" in body
        assert "Thuốc B (2 viên)" in body
        assert "Thuốc C (1 gói)" in body

    def test_duplicate_medication_merge(self):
        """Two Metformin 500mg (1 viên each) + one Paracetamol 500mg should
        merge into: Metformin 500mg (2 viên), Paracetamol 500mg (1 viên)."""
        scheduled_at = datetime(2026, 8, 23, 1, 0, tzinfo=timezone.utc)  # 08:00 VN
        doses = [
            {
                "scheduled_dose_id": DOSE_ID_1,
                "medication_name": "Metformin 500mg",
                "dose_value": Decimal("1"),
                "dose_unit": "viên",
            },
            {
                "scheduled_dose_id": DOSE_ID_2,
                "medication_name": "Paracetamol 500mg",
                "dose_value": Decimal("1"),
                "dose_unit": "viên",
            },
            {
                "scheduled_dose_id": DOSE_ID_3,
                "medication_name": "Metformin 500mg",
                "dose_value": Decimal("1"),
                "dose_unit": "viên",
            },
        ]
        title, body = NotificationDispatchService.format_notification_text(scheduled_at, doses)
        assert title == "Nhắc nhở uống thuốc (08:00)"
        # Should be merged to 2 unique medications, not 3
        assert "2 loại thuốc" in body
        assert "Metformin 500mg (2 viên)" in body
        assert "Paracetamol 500mg (1 viên)" in body


@pytest.mark.asyncio
class TestNotificationDispatchService:
    async def test_create_consolidated_reminders(self):
        scheduled_at = datetime(2026, 8, 19, 21, 0, tzinfo=timezone.utc)
        cutoff = datetime(2026, 8, 19, 21, 5, tzinfo=timezone.utc)

        dose_groups = {
            (PATIENT_ID, scheduled_at): [
                {
                    "scheduled_dose_id": DOSE_ID_1,
                    "medication_name": "Thuốc A",
                    "dose_value": Decimal("1"),
                    "dose_unit": "viên",
                },
                {
                    "scheduled_dose_id": DOSE_ID_2,
                    "medication_name": "Thuốc B",
                    "dose_value": Decimal("2"),
                    "dose_unit": "viên",
                },
                {
                    "scheduled_dose_id": DOSE_ID_3,
                    "medication_name": "Thuốc C",
                    "dose_value": Decimal("1"),
                    "dose_unit": "viên",
                },
            ]
        }

        mock_db = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.begin.return_value.__aenter__ = AsyncMock()
        mock_db.begin.return_value.__aexit__ = AsyncMock()

        mock_dose_repo = AsyncMock()
        mock_dose_repo.get_due_dose_groups.return_value = dose_groups

        mock_notif_repo = AsyncMock()
        mock_notif_repo.get_delivery_by_idempotency_key.return_value = None

        fake_delivery = SimpleNamespace(
            id=uuid.uuid4(),
            recipient_user_id=PATIENT_ID,
            scheduled_at=scheduled_at,
            title="Nhắc nhở uống thuốc (21:00)",
            body="Đến giờ uống 3 loại thuốc...",
        )
        mock_notif_repo.create_grouped_delivery.return_value = fake_delivery

        service = NotificationDispatchService(
            db=mock_db,
            scheduled_dose_repository=mock_dose_repo,
            notification_repository=mock_notif_repo,
        )

        with patch("src.modules.agents.tasks.send_notification_task.delay") as mock_delay:
            deliveries = await service.create_consolidated_reminders(cutoff=cutoff)
            assert len(deliveries) == 1
            assert deliveries[0].recipient_user_id == PATIENT_ID
            mock_delay.assert_called_once_with(str(fake_delivery.id))

        mock_notif_repo.create_grouped_delivery.assert_awaited_once()
        call_kwargs = mock_notif_repo.create_grouped_delivery.await_args.kwargs
        assert call_kwargs["recipient_user_id"] == PATIENT_ID
        assert call_kwargs["scheduled_dose_ids"] == [DOSE_ID_1, DOSE_ID_2, DOSE_ID_3]
        assert "3 loại thuốc" in call_kwargs["body"]

    async def test_execute_send_notification_success(self):
        from src.modules.agents.tasks import _execute_send_notification
        delivery_id = uuid.uuid4()
        fake_delivery = SimpleNamespace(
            id=delivery_id,
            recipient_user_id=PATIENT_ID,
            title="Nhắc nhở",
            body="Đến giờ uống thuốc",
        )

        mock_session = MagicMock()
        mock_session.begin.return_value.__aenter__ = AsyncMock()
        mock_session.begin.return_value.__aexit__ = AsyncMock()

        with (
            patch("src.modules.agents.tasks.create_async_engine") as mock_engine_cls,
            patch("src.modules.agents.tasks.async_sessionmaker") as mock_sm_cls,
            patch("src.modules.agents.tasks.NotificationRepository") as mock_repo_cls,
            patch("src.modules.agents.tasks.FCMService.send_push_notification") as mock_fcm,
        ):
            mock_engine = AsyncMock()
            mock_engine_cls.return_value = mock_engine
            mock_sm = MagicMock()
            mock_sm.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_sm.return_value.__aexit__ = AsyncMock()
            mock_sm_cls.return_value = mock_sm

            mock_repo = AsyncMock()
            mock_repo.get_delivery_by_id.return_value = fake_delivery
            mock_repo.get_active_fcm_tokens.return_value = ["token_123"]
            mock_repo_cls.return_value = mock_repo
            mock_fcm.return_value = True

            await _execute_send_notification(str(delivery_id))

            mock_repo.get_delivery_by_id.assert_awaited_once_with(delivery_id)
            mock_repo.get_active_fcm_tokens.assert_awaited_once_with(PATIENT_ID)
            mock_fcm.assert_called_once_with(
                tokens=["token_123"],
                title="Nhắc nhở",
                body="Đến giờ uống thuốc",
                data={"delivery_id": str(delivery_id), "action": "dose_reminder"},
            )
            mock_repo.update_delivery_status.assert_awaited_once_with(delivery_id, "SENT")


def _fake_dose(dose_id, patient_id=PATIENT_ID, status="PENDING", snooze_count=0):
    return ScheduledDose(
        id=dose_id,
        prescription_item_id=uuid.uuid4(),
        patient_id=patient_id,
        original_scheduled_at=datetime(2026, 8, 19, 21, 0, tzinfo=timezone.utc),
        current_scheduled_at=datetime(2026, 8, 19, 21, 0, tzinfo=timezone.utc),
        status=status,
        snooze_count=snooze_count,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _fake_log(dose_id, patient_id=PATIENT_ID, action="SNOOZE", key="idem-1"):
    return AdherenceLog(
        id=uuid.uuid4(),
        scheduled_dose_id=dose_id,
        patient_id=patient_id,
        action=action,
        performed_at=datetime.now(timezone.utc),
        action_source="PATIENT_MOBILE_APP",
        payload={"snooze_duration_minutes": 15},
        idempotency_key=f"{key}:{dose_id}",
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
class TestBatchDoseActionsService:
    async def test_batch_snooze_success(self):
        mock_db = MagicMock()
        mock_db.in_transaction.return_value = False
        mock_db.begin.return_value.__aenter__ = AsyncMock()
        mock_db.begin.return_value.__aexit__ = AsyncMock()

        mock_repo = AsyncMock()
        mock_repo.get_batch_logs_by_idempotency_key.return_value = []

        updated_doses = [
            _fake_dose(DOSE_ID_1, snooze_count=1),
            _fake_dose(DOSE_ID_2, snooze_count=1),
            _fake_dose(DOSE_ID_3, snooze_count=1),
        ]
        mock_repo.batch_apply_dose_actions_cas.return_value = updated_doses

        fake_logs = [
            _fake_log(DOSE_ID_1, action="SNOOZE", key="batch-key-1"),
            _fake_log(DOSE_ID_2, action="SNOOZE", key="batch-key-1"),
            _fake_log(DOSE_ID_3, action="SNOOZE", key="batch-key-1"),
        ]
        mock_repo.insert_batch_logs.return_value = fake_logs

        service = AdherenceLogService(db=mock_db, adherence_log_repository=mock_repo)

        request = BatchRecordDoseActionRequest(
            dose_ids=[DOSE_ID_1, DOSE_ID_2, DOSE_ID_3],
            action="SNOOZE",
            action_source="PATIENT_MOBILE_APP",
            payload={"snooze_duration_minutes": 15},
        )

        with patch("src.modules.adherence.service.publish_dashboard_event", new_callable=AsyncMock):
            response = await service.batch_record_dose_action(
                request=request,
                actor_payload={"sub": str(PATIENT_ID), "role": "PATIENT"},
                idempotency_key="batch-key-1",
            )

        assert response.action == "SNOOZE"
        assert response.updated_dose_count == 3
        assert response.updated_dose_ids == [DOSE_ID_1, DOSE_ID_2, DOSE_ID_3]
        assert len(response.logs) == 3

        mock_repo.batch_apply_dose_actions_cas.assert_awaited_once_with(
            [DOSE_ID_1, DOSE_ID_2, DOSE_ID_3], PATIENT_ID, "SNOOZE", 15
        )

    async def test_batch_action_requires_idempotency_key(self):
        mock_db = MagicMock()
        mock_repo = AsyncMock()
        service = AdherenceLogService(db=mock_db, adherence_log_repository=mock_repo)

        request = BatchRecordDoseActionRequest(
            dose_ids=[DOSE_ID_1],
            action="TAKEN",
        )

        with pytest.raises(ValidationException) as exc_info:
            await service.batch_record_dose_action(
                request=request,
                actor_payload={"sub": str(PATIENT_ID), "role": "PATIENT"},
                idempotency_key=None,
            )
        assert "Idempotency-Key header is required" in str(exc_info.value.message)

    async def test_batch_action_idempotent_replay(self):
        mock_db = MagicMock()
        mock_repo = AsyncMock()

        existing_logs = [
            _fake_log(DOSE_ID_1, action="TAKEN", key="replay-key"),
            _fake_log(DOSE_ID_2, action="TAKEN", key="replay-key"),
        ]
        mock_repo.get_batch_logs_by_idempotency_key.return_value = existing_logs

        service = AdherenceLogService(db=mock_db, adherence_log_repository=mock_repo)

        request = BatchRecordDoseActionRequest(
            dose_ids=[DOSE_ID_1, DOSE_ID_2],
            action="TAKEN",
        )

        response = await service.batch_record_dose_action(
            request=request,
            actor_payload={"sub": str(PATIENT_ID), "role": "PATIENT"},
            idempotency_key="replay-key",
        )

        assert response.action == "TAKEN"
        assert response.updated_dose_count == 2
        assert response.updated_dose_ids == [DOSE_ID_1, DOSE_ID_2]
        mock_repo.batch_apply_dose_actions_cas.assert_not_called()

    async def test_snooze_exceeds_max_count(self):
        mock_db = MagicMock()
        mock_db.commit = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_batch_logs_by_idempotency_key.return_value = []

        dose_with_max_snooze = _fake_dose(DOSE_ID_1, snooze_count=3)
        mock_repo.get_doses_scoped.return_value = [dose_with_max_snooze]

        service = AdherenceLogService(db=mock_db, adherence_log_repository=mock_repo)

        request = BatchRecordDoseActionRequest(
            dose_ids=[DOSE_ID_1],
            action="SNOOZE",
            payload={"snooze_duration_minutes": 15},
        )

        with pytest.raises(ConflictException) as exc_info:
            await service.batch_record_dose_action(
                request=request,
                actor_payload={"sub": str(PATIENT_ID), "role": "PATIENT"},
                idempotency_key="snooze-max-key",
            )
        assert "giới hạn hoãn tối đa" in str(exc_info.value.message)

    async def test_snooze_violates_min_dose_gap(self):
        mock_db = MagicMock()
        mock_db.commit = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_batch_logs_by_idempotency_key.return_value = []

        current_time = datetime(2026, 8, 23, 8, 0, tzinfo=timezone.utc)
        dose = _fake_dose(DOSE_ID_1, snooze_count=0)
        dose.current_scheduled_at = current_time
        mock_repo.get_doses_scoped.return_value = [dose]

        # Next dose is only 60 minutes away, but minimum required gap is 120 minutes
        next_dose = _fake_dose(DOSE_ID_2, snooze_count=0)
        next_dose.current_scheduled_at = current_time + timedelta(minutes=60)
        mock_repo.get_next_dose_and_min_gap.return_value = (next_dose, 120)

        service = AdherenceLogService(db=mock_db, adherence_log_repository=mock_repo)

        request = BatchRecordDoseActionRequest(
            dose_ids=[DOSE_ID_1],
            action="SNOOZE",
            payload={"snooze_duration_minutes": 15},
        )

        with pytest.raises(ConflictException) as exc_info:
            await service.batch_record_dose_action(
                request=request,
                actor_payload={"sub": str(PATIENT_ID), "role": "PATIENT"},
                idempotency_key="snooze-gap-key",
            )
        assert "khoảng cách tối thiểu" in str(exc_info.value.message)
