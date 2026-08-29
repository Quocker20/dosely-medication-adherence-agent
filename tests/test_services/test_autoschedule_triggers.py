"""Automatic Planning/Rescheduling Agent triggers.

Two entry points feed the same worker task: approving a prescription and
editing a routine. A third, creating a patient, seeds the routine anchors the
planner needs so the first approval can actually plan. These tests pin the
behaviour that makes that safe — above all that a broker failure never rolls
back a clinical action.
"""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from src.common.exceptions import NotFoundException
from src.core.config import get_settings
from src.modules.agents.service import AutoscheduleOutcome, SchedulingService
from src.modules.patients.constants import DEFAULT_ROUTINE
from src.modules.patients.schemas import UpdateRoutineRequest
from src.modules.patients.service import PatientService
from src.modules.prescriptions.service import PrescriptionService


class _TransactionDb:
    """Minimal stand-in for AsyncSession's transaction surface."""

    @asynccontextmanager
    async def begin(self):
        yield

    def in_transaction(self) -> bool:
        return False

    async def commit(self) -> None:
        return None


def _patient_service(patient_repository: MagicMock) -> PatientService:
    return PatientService(
        db=_TransactionDb(),
        patient_repository=patient_repository,
        doctor_repository=MagicMock(),
        audit_repository=MagicMock(),
        # AsyncMock, not MagicMock: update_routine awaits
        # auth_repository.clear_need_onboarding(...).
        auth_repository=AsyncMock(),
        caregiver_repository=MagicMock(),
    )


def _routine_row(patient_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        patient_id=patient_id,
        wake_time=time(6, 0),
        breakfast_time=time(7, 0),
        lunch_time=time(11, 30),
        dinner_time=time(18, 0),
        sleep_time=time(22, 0),
        updated_at=datetime.now(UTC),
    )


# --------------------------------------------------------------------------
# Routine edit -> reschedule
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_partial_routine_update_only_sends_changed_fields():
    """A partial PUT must not carry the untouched anchors along as None.

    upsert_routine writes exactly the keys it is handed, so passing all five
    every time is what used to NULL breakfast/lunch and strand the planner
    with MissingRoutineAnchorError.
    """
    patient_id = uuid.uuid4()
    repository = MagicMock()
    repository.upsert_routine = AsyncMock(return_value=_routine_row(patient_id))

    with patch.object(PatientService, "_dispatch_reschedule"):
        await _patient_service(repository).update_routine(
            patient_id=patient_id,
            request=UpdateRoutineRequest(dinner_time=time(21, 0)),
            actor_payload={"sub": str(patient_id), "role": "PATIENT"},
        )

    repository.upsert_routine.assert_awaited_once_with(
        patient_id=patient_id,
        updates={"dinner_time": time(21, 0)},
    )


@pytest.mark.asyncio
async def test_routine_update_dispatches_reschedule():
    patient_id = uuid.uuid4()
    repository = MagicMock()
    repository.upsert_routine = AsyncMock(return_value=_routine_row(patient_id))

    with patch("src.modules.patients.service.celery_app") as celery:
        await _patient_service(repository).update_routine(
            patient_id=patient_id,
            request=UpdateRoutineRequest(dinner_time=time(21, 0)),
            actor_payload={"sub": str(patient_id), "role": "PATIENT"},
        )

    celery.send_task.assert_called_once_with(
        "agents.autoschedule",
        args=[str(patient_id), None, "ROUTINE_UPDATED"],
    )


@pytest.mark.asyncio
async def test_routine_update_survives_broker_failure():
    """The routine is already committed; a dead broker must not surface as an
    error for a change that succeeded."""
    patient_id = uuid.uuid4()
    repository = MagicMock()
    repository.upsert_routine = AsyncMock(return_value=_routine_row(patient_id))

    with patch("src.modules.patients.service.celery_app") as celery:
        celery.send_task.side_effect = RuntimeError("broker down")
        result = await _patient_service(repository).update_routine(
            patient_id=patient_id,
            request=UpdateRoutineRequest(dinner_time=time(21, 0)),
            actor_payload={"sub": str(patient_id), "role": "PATIENT"},
        )

    assert result.patient_id == patient_id


@pytest.mark.asyncio
async def test_rejected_routine_update_does_not_dispatch():
    """Access denial must not leak through a side channel."""
    repository = MagicMock()
    repository.upsert_routine = AsyncMock()

    with patch("src.modules.patients.service.celery_app") as celery:
        with pytest.raises(NotFoundException):
            await _patient_service(repository).update_routine(
                patient_id=uuid.uuid4(),
                request=UpdateRoutineRequest(dinner_time=time(21, 0)),
                actor_payload={"sub": str(uuid.uuid4()), "role": "PATIENT"},
            )

    celery.send_task.assert_not_called()
    repository.upsert_routine.assert_not_awaited()


# --------------------------------------------------------------------------
# Prescription approval -> generation
# --------------------------------------------------------------------------


def _prescription_service() -> PrescriptionService:
    return PrescriptionService(
        db=_TransactionDb(),
        prescription_repository=MagicMock(),
        doctor_repository=MagicMock(),
        audit_repository=MagicMock(),
        medication_repository=MagicMock(),
        auth_repository=MagicMock(),
        patient_repository=MagicMock(),
        scheduled_dose_repository=MagicMock(),
    )


def test_approval_dispatches_generation_with_prescription_scope():
    patient_id, prescription_id = uuid.uuid4(), uuid.uuid4()

    with patch("src.modules.prescriptions.service.celery_app") as celery:
        _prescription_service()._dispatch_schedule_generation(patient_id, prescription_id)

    celery.send_task.assert_called_once_with(
        "agents.autoschedule",
        args=[str(patient_id), str(prescription_id), "PRESCRIPTION_APPROVED"],
    )


def test_approval_dispatch_swallows_broker_failure():
    """Approval is the doctor's HITL decision and is already committed —
    infrastructure must never be able to undo it."""
    with patch("src.modules.prescriptions.service.celery_app") as celery:
        celery.send_task.side_effect = RuntimeError("broker down")
        # Must not raise.
        _prescription_service()._dispatch_schedule_generation(uuid.uuid4(), uuid.uuid4())


def test_autoschedule_can_be_disabled():
    with patch("src.modules.prescriptions.service.celery_app") as celery:
        with patch("src.modules.prescriptions.service.get_settings") as settings:
            settings.return_value = SimpleNamespace(prescription_autoschedule_enabled=False)
            _prescription_service()._dispatch_schedule_generation(uuid.uuid4(), uuid.uuid4())

    celery.send_task.assert_not_called()


# --------------------------------------------------------------------------
# The worker-side trigger itself
# --------------------------------------------------------------------------


def _scheduling_service(dose_repo: MagicMock, run_repo: MagicMock) -> SchedulingService:
    return SchedulingService(
        db=_TransactionDb(),
        agent_run_repository=run_repo,
        scheduled_dose_repository=dose_repo,
        patient_repository=MagicMock(),
    )


@pytest.mark.asyncio
async def test_autoschedule_skips_when_nothing_is_approved():
    """A patient editing their routine before ever being prescribed anything
    must not pile up NEEDS_REVIEW runs for a clinician to triage."""
    dose_repo = MagicMock()
    dose_repo.get_approved_items = AsyncMock(return_value=[])
    run_repo = MagicMock()
    run_repo.create_run = AsyncMock()

    outcome = await _scheduling_service(dose_repo, run_repo).request_autoschedule(
        patient_id=uuid.uuid4(), prescription_id=None, trigger_type="ROUTINE_UPDATED"
    )

    assert outcome is AutoscheduleOutcome.NOTHING_TO_PLAN
    run_repo.create_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_autoschedule_records_the_real_trigger_not_manual():
    patient_id, prescription_id = uuid.uuid4(), uuid.uuid4()
    dose_repo = MagicMock()
    dose_repo.get_approved_items = AsyncMock(return_value=[(MagicMock(), prescription_id)])
    run_repo = MagicMock()
    run_repo.create_run = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))

    with patch.object(SchedulingService, "_dispatch_generate") as dispatch:
        outcome = await _scheduling_service(dose_repo, run_repo).request_autoschedule(
            patient_id=patient_id,
            prescription_id=prescription_id,
            trigger_type="PRESCRIPTION_APPROVED",
        )

    assert outcome is AutoscheduleOutcome.DISPATCHED
    kwargs = run_repo.create_run.await_args.kwargs
    assert kwargs["trigger_type"] == "PRESCRIPTION_APPROVED"
    assert kwargs["agent_type"] == "PLANNING_AGENT"
    assert kwargs["prescription_id"] == prescription_id
    assert dispatch.call_args.kwargs["is_reschedule"] is False


@pytest.mark.asyncio
async def test_routine_trigger_runs_as_rescheduling_agent():
    dose_repo = MagicMock()
    dose_repo.get_approved_items = AsyncMock(return_value=[(MagicMock(), uuid.uuid4())])
    run_repo = MagicMock()
    run_repo.create_run = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))

    with patch.object(SchedulingService, "_dispatch_generate") as dispatch:
        await _scheduling_service(dose_repo, run_repo).request_autoschedule(
            patient_id=uuid.uuid4(), prescription_id=None, trigger_type="ROUTINE_UPDATED"
        )

    assert run_repo.create_run.await_args.kwargs["agent_type"] == "RESCHEDULING_AGENT"
    assert dispatch.call_args.kwargs["is_reschedule"] is True


@pytest.mark.asyncio
async def test_autoschedule_reports_in_flight_run_for_retry():
    """uq_agent_runs_one_running means come back shortly, not 409 — the
    approved drug still needs a schedule."""
    dose_repo = MagicMock()
    dose_repo.get_approved_items = AsyncMock(return_value=[(MagicMock(), uuid.uuid4())])
    run_repo = MagicMock()
    run_repo.create_run = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception()))

    with patch.object(SchedulingService, "_dispatch_generate") as dispatch:
        outcome = await _scheduling_service(dose_repo, run_repo).request_autoschedule(
            patient_id=uuid.uuid4(),
            prescription_id=uuid.uuid4(),
            trigger_type="PRESCRIPTION_APPROVED",
        )

    assert outcome is AutoscheduleOutcome.RUN_IN_FLIGHT
    dispatch.assert_not_called()


# --------------------------------------------------------------------------
# Seeded routine
# --------------------------------------------------------------------------


def test_default_routine_gap_clears_the_min_dose_interval():
    """Breakfast->lunch is the tightest pair; if it fell under
    min_dose_gap_minutes every 3-a-day prescription would land in
    NEEDS_REVIEW on the patient's very first approval."""

    def _minutes(value: time) -> int:
        return value.hour * 60 + value.minute

    breakfast_to_lunch = _minutes(DEFAULT_ROUTINE["lunch_time"]) - _minutes(
        DEFAULT_ROUTINE["breakfast_time"]
    )
    lunch_to_dinner = _minutes(DEFAULT_ROUTINE["dinner_time"]) - _minutes(
        DEFAULT_ROUTINE["lunch_time"]
    )

    minimum = get_settings().min_dose_gap_minutes
    assert breakfast_to_lunch >= minimum
    assert lunch_to_dinner >= minimum


def test_default_routine_covers_every_planner_anchor():
    """expand_schedule anchors morning/noon/evening/bedtime doses on these
    four keys; a missing one raises MissingRoutineAnchorError."""
    for anchor in ("breakfast_time", "lunch_time", "dinner_time", "sleep_time"):
        assert DEFAULT_ROUTINE.get(anchor) is not None
