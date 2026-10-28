"""MissedDoseScanService: the fast-path streak alert is narrowed to
PrescriptionItem.is_critical doses only (docs/graded-adherence-implementation.md
Stage 2). A missed vitamin no longer pages a doctor identically to a missed
anticoagulant, and the state-machine half (PENDING -> MISSED) still runs for
every dose regardless of is_critical.
"""
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from src.modules.agents.missed_dose_scan_service import MissedDoseScanService

PATIENT_ID = uuid.uuid4()
CRITICAL_DOSE_ID = uuid.uuid4()
NON_CRITICAL_DOSE_ID = uuid.uuid4()


def _service_with_mocks(dose_repo=None, alert_repo=None):
    db = MagicMock()
    begin_ctx = MagicMock()
    begin_ctx.__aenter__ = AsyncMock(return_value=None)
    begin_ctx.__aexit__ = AsyncMock(return_value=False)
    db.begin.return_value = begin_ctx

    service = MissedDoseScanService(
        db=db,
        scheduled_dose_repository=dose_repo or AsyncMock(),
        alert_repository=alert_repo or AsyncMock(),
    )
    return service


class TestStateFlipUnaffectedByCriticality:
    @pytest.mark.asyncio
    async def test_no_affected_rows_short_circuits_before_any_streak_query(self):
        """The state-flip half runs unconditionally; an empty result means
        nothing was overdue this tick, so there is nothing left to do."""
        dose_repo = AsyncMock()
        dose_repo.mark_overdue_pending_as_missed.return_value = []
        alert_repo = AsyncMock()
        service = _service_with_mocks(dose_repo, alert_repo)

        await service.run_scan()

        dose_repo.get_recent_critical_dose_statuses.assert_not_called()
        alert_repo.create_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_all_non_critical_flips_skip_the_streak_query_entirely(self):
        """No critical dose was newly missed this tick -> no patient's
        critical streak could have changed -> nothing to recheck. This is a
        pure optimization, not a correctness gap: if a prior tick already
        checked this patient's critical streak, it has not moved since."""
        now = datetime.now(UTC)
        dose_repo = AsyncMock()
        dose_repo.mark_overdue_pending_as_missed.return_value = [
            (PATIENT_ID, NON_CRITICAL_DOSE_ID, now, False),
        ]
        alert_repo = AsyncMock()
        service = _service_with_mocks(dose_repo, alert_repo)

        await service.run_scan()

        dose_repo.get_recent_critical_dose_statuses.assert_not_called()
        alert_repo.create_alert.assert_not_called()


class TestCriticalStreakAlert:
    @pytest.fixture(autouse=True)
    def caregiver_repo(self):
        """run_scan builds its own CaregiverRepository(self._db) to fan the
        alert out to caregivers; with a bare MagicMock db that would try to
        await a real query. Default: the patient has no deliverable links."""
        repo = AsyncMock()
        repo.list_deliverable_for_patient.return_value = []
        with patch("src.modules.caregivers.repository.CaregiverRepository", return_value=repo):
            yield repo

    @pytest.mark.asyncio
    async def test_alerts_when_critical_streak_meets_threshold(self):
        now = datetime.now(UTC)
        dose_repo = AsyncMock()
        dose_repo.mark_overdue_pending_as_missed.return_value = [
            (PATIENT_ID, CRITICAL_DOSE_ID, now, True),
        ]
        dose_repo.get_recent_critical_dose_statuses.return_value = {
            PATIENT_ID: [{"status": "MISSED"}, {"status": "MISSED"}, {"status": "MISSED"}]
        }
        alert_repo = AsyncMock()
        service = _service_with_mocks(dose_repo, alert_repo)

        await service.run_scan()

        dose_repo.get_recent_critical_dose_statuses.assert_awaited_once()
        call_args = dose_repo.get_recent_critical_dose_statuses.await_args
        assert call_args.args[0] == [PATIENT_ID]

        alert_repo.create_alert.assert_awaited_once()
        _, kwargs = alert_repo.create_alert.await_args
        assert kwargs["patient_id"] == PATIENT_ID
        assert kwargs["triggered_by_type"] == "MISSED_DOSES"
        assert kwargs["triggered_by_id"] == CRITICAL_DOSE_ID
        assert kwargs["alert_type"] == "RED_ALERT"
        assert kwargs["severity"] == "HIGH"
        assert kwargs["idempotency_key"] == f"missed-dose-streak:{PATIENT_ID}:{CRITICAL_DOSE_ID}"

    @pytest.mark.asyncio
    async def test_streak_alert_fans_out_to_bound_caregivers(self, caregiver_repo):
        link_id = uuid.uuid4()
        delivery_id = uuid.uuid4()
        caregiver_repo.list_deliverable_for_patient.return_value = [SimpleNamespace(id=link_id)]
        now = datetime.now(UTC)
        dose_repo = AsyncMock()
        dose_repo.mark_overdue_pending_as_missed.return_value = [
            (PATIENT_ID, CRITICAL_DOSE_ID, now, True),
        ]
        dose_repo.get_recent_critical_dose_statuses.return_value = {
            PATIENT_ID: [{"status": "MISSED"}, {"status": "MISSED"}, {"status": "MISSED"}]
        }
        alert = SimpleNamespace(id=uuid.uuid4())
        alert_repo = AsyncMock()
        alert_repo.create_alert.return_value = alert
        service = _service_with_mocks(dose_repo, alert_repo)
        service._db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value="Bác An"))
        )
        notif_repo = AsyncMock()
        notif_repo.create_caregiver_delivery.return_value = SimpleNamespace(id=delivery_id)

        with (
            patch("src.modules.adherence.repository.NotificationRepository", return_value=notif_repo),
            patch("src.modules.agents.tasks.send_notification_task.delay") as delay,
        ):
            await service.run_scan()

        notif_repo.create_caregiver_delivery.assert_awaited_once()
        kwargs = notif_repo.create_caregiver_delivery.await_args.kwargs
        assert kwargs["caregiver_link_id"] == link_id
        assert kwargs["template_code"] == "CG_MISSED_DOSE"
        assert kwargs["metadata"] == {"alert_id": str(alert.id)}
        delay.assert_called_once_with(str(delivery_id))

    @pytest.mark.asyncio
    async def test_below_threshold_streak_does_not_alert(self):
        now = datetime.now(UTC)
        dose_repo = AsyncMock()
        dose_repo.mark_overdue_pending_as_missed.return_value = [
            (PATIENT_ID, CRITICAL_DOSE_ID, now, True),
        ]
        dose_repo.get_recent_critical_dose_statuses.return_value = {
            PATIENT_ID: [{"status": "TAKEN"}, {"status": "MISSED"}, {"status": "MISSED"}]
        }
        alert_repo = AsyncMock()
        service = _service_with_mocks(dose_repo, alert_repo)

        await service.run_scan()

        alert_repo.create_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_critical_flip_never_becomes_the_tracked_last_dose(self):
        """Deliberate invariant: even if a non-critical dose was flipped
        later in the same tick than the critical one, the alert's
        triggered_by_id/idempotency-key must still point at the critical
        dose -- never at whichever flip happened to be most recent overall."""
        earlier = datetime.now(UTC) - timedelta(minutes=5)
        later = datetime.now(UTC)
        dose_repo = AsyncMock()
        dose_repo.mark_overdue_pending_as_missed.return_value = [
            (PATIENT_ID, CRITICAL_DOSE_ID, earlier, True),
            (PATIENT_ID, NON_CRITICAL_DOSE_ID, later, False),
        ]
        dose_repo.get_recent_critical_dose_statuses.return_value = {
            PATIENT_ID: [{"status": "MISSED"}, {"status": "MISSED"}, {"status": "MISSED"}]
        }
        alert_repo = AsyncMock()
        service = _service_with_mocks(dose_repo, alert_repo)

        await service.run_scan()

        _, kwargs = alert_repo.create_alert.await_args
        assert kwargs["triggered_by_id"] == CRITICAL_DOSE_ID

    @pytest.mark.asyncio
    async def test_integrity_error_is_swallowed_as_idempotent_replay(self):
        now = datetime.now(UTC)
        dose_repo = AsyncMock()
        dose_repo.mark_overdue_pending_as_missed.return_value = [
            (PATIENT_ID, CRITICAL_DOSE_ID, now, True),
        ]
        dose_repo.get_recent_critical_dose_statuses.return_value = {
            PATIENT_ID: [{"status": "MISSED"}, {"status": "MISSED"}, {"status": "MISSED"}]
        }
        alert_repo = AsyncMock()
        alert_repo.create_alert.side_effect = IntegrityError("stmt", {}, Exception("dup"))
        service = _service_with_mocks(dose_repo, alert_repo)

        await service.run_scan()  # must not raise
