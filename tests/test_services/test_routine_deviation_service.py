"""Batched routine-deviation reporting.

The shared entry point behind both channels (the chat tool and the end-of-day
survey) is SchedulingService.report_routine_deviations. These tests pin the
parts that are load-bearing for safety: only one agent run per report no
matter how many anchors it carries, contradictory input refused rather than
guessed, and the override rows landing in the same transaction as the run so
a rejected run can always find them again.
"""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError

from src.common.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from src.core.config import get_settings
from src.modules.agents.schemas import (
    CancelRoutineOverrideRequest,
    ReportRoutineDeviationRequest,
)
from src.modules.agents.service import SchedulingService

PATIENT_TZ = "Asia/Ho_Chi_Minh"


class _TransactionDb:
    """Minimal stand-in for AsyncSession's transaction surface."""

    @asynccontextmanager
    async def begin(self):
        yield

    def in_transaction(self) -> bool:
        return False

    async def commit(self) -> None:
        return None


def _today_local() -> date:
    return datetime.now(UTC).astimezone(ZoneInfo(PATIENT_TZ)).date()


def _service(run_id: uuid.UUID, *, create_run_raises: bool = False):
    dose_repo = MagicMock()
    dose_repo.get_patient_timezone_scoped = AsyncMock(return_value=PATIENT_TZ)
    dose_repo.upsert_override = AsyncMock(side_effect=lambda *args, **kwargs: SimpleNamespace(id=uuid.uuid4()))
    dose_repo.mark_overrides_rejected = AsyncMock()
    dose_repo.delete_override = AsyncMock(return_value=True)

    agent_run_repo = MagicMock()
    if create_run_raises:
        agent_run_repo.create_run = AsyncMock(
            side_effect=IntegrityError("uq_agent_runs_one_running", None, Exception())
        )
    else:
        agent_run_repo.create_run = AsyncMock(return_value=SimpleNamespace(id=run_id))

    service = SchedulingService(
        _TransactionDb(),
        agent_run_repo,
        dose_repo,
        MagicMock(),
    )
    return service, dose_repo, agent_run_repo


def _deviation(anchor: str, hour: int, *, on: date | None = None) -> ReportRoutineDeviationRequest:
    return ReportRoutineDeviationRequest(
        override_date=on or _today_local(),
        anchor=anchor,
        overridden_time=time(hour, 0),
        source="SURVEY",
        reason=None,
    )


@pytest.mark.asyncio
async def test_many_deviations_produce_exactly_one_agent_run():
    """The regression this whole batching exists for: one run per *report*,
    not per anchor. uq_agent_runs_one_running only permits one in-flight run
    per patient, so a per-anchor loop failed on the second deviation and took
    the surrounding survey submission down with it."""
    patient_id = uuid.uuid4()
    run_id = uuid.uuid4()
    service, dose_repo, agent_run_repo = _service(run_id)

    with patch.object(SchedulingService, "_dispatch_generate") as dispatch:
        result = await service.report_routine_deviations(
            patient_id,
            [_deviation("lunch", 14), _deviation("dinner", 21)],
            {"sub": str(patient_id)},
        )

    assert agent_run_repo.create_run.await_count == 1
    assert dose_repo.upsert_override.await_count == 2
    assert result.agent_run_id == run_id
    dispatch.assert_called_once()


@pytest.mark.asyncio
async def test_overrides_are_stamped_with_the_run_that_will_consume_them():
    """consumed_by_run_id must be written with the row, not backfilled after
    dispatch — a worker that fails before a second commit would otherwise be
    unable to find the overrides it needs to mark REJECTED."""
    patient_id = uuid.uuid4()
    run_id = uuid.uuid4()
    service, dose_repo, _ = _service(run_id)

    with patch.object(SchedulingService, "_dispatch_generate"):
        await service.report_routine_deviations(patient_id, [_deviation("dinner", 21)], {"sub": str(patient_id)})

    assert dose_repo.upsert_override.await_args.kwargs["consumed_by_run_id"] == run_id


@pytest.mark.asyncio
async def test_dispatch_happens_only_after_the_overrides_are_committed():
    """Celery is fire-and-forget: dispatching before the overrides are stored
    lets the worker read a schedule that does not yet include them."""
    patient_id = uuid.uuid4()
    service, dose_repo, _ = _service(uuid.uuid4())

    with patch.object(SchedulingService, "_dispatch_generate") as dispatch:
        dispatch.side_effect = lambda *a, **k: setattr(
            dispatch, "upserts_at_dispatch", dose_repo.upsert_override.await_count
        )
        await service.report_routine_deviations(patient_id, [_deviation("lunch", 14)], {"sub": str(patient_id)})

    assert dispatch.upserts_at_dispatch == 1


@pytest.mark.asyncio
async def test_two_times_for_one_anchor_are_refused_not_silently_merged():
    """The unique constraint would keep whichever upsert ran last. Picking one
    of two contradictory times is exactly the guessing the planner forbids."""
    patient_id = uuid.uuid4()
    service, dose_repo, agent_run_repo = _service(uuid.uuid4())

    with pytest.raises(ValidationException):
        await service.report_routine_deviations(
            patient_id,
            [_deviation("dinner", 19), _deviation("dinner", 21)],
            {"sub": str(patient_id)},
        )

    agent_run_repo.create_run.assert_not_awaited()
    dose_repo.upsert_override.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_past_day_is_refused_for_every_entry():
    """History cannot be rewritten: those doses are already TAKEN or MISSED.
    One bad entry rejects the whole batch rather than partially applying."""
    patient_id = uuid.uuid4()
    service, dose_repo, _ = _service(uuid.uuid4())

    with pytest.raises(ValidationException):
        await service.report_routine_deviations(
            patient_id,
            [_deviation("lunch", 14), _deviation("dinner", 21, on=_today_local() - timedelta(days=1))],
            {"sub": str(patient_id)},
        )

    dose_repo.upsert_override.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_day_beyond_the_schedule_horizon_is_refused():
    """Not an arbitrary policy limit: get_active_overrides is queried over
    [today, today+horizon] and expand_schedule only materialises days inside
    it, so a row stored past the horizon would look accepted and do nothing."""
    patient_id = uuid.uuid4()
    service, dose_repo, _ = _service(uuid.uuid4())
    beyond = _today_local() + timedelta(days=get_settings().schedule_horizon_days + 1)

    with pytest.raises(ValidationException):
        await service.report_routine_deviations(
            patient_id, [_deviation("dinner", 21, on=beyond)], {"sub": str(patient_id)}
        )

    dose_repo.upsert_override.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_future_day_inside_the_horizon_is_accepted():
    patient_id = uuid.uuid4()
    service, dose_repo, _ = _service(uuid.uuid4())
    in_three_days = _today_local() + timedelta(days=3)

    with patch.object(SchedulingService, "_dispatch_generate"):
        await service.report_routine_deviations(
            patient_id, [_deviation("dinner", 21, on=in_three_days)], {"sub": str(patient_id)}
        )

    assert dose_repo.upsert_override.await_args.args[1] == in_three_days


@pytest.mark.asyncio
async def test_day_offset_is_resolved_against_the_patients_own_timezone():
    """The chat agent sends an offset precisely because it cannot know the
    patient's local date; the service is what turns it into a real day."""
    patient_id = uuid.uuid4()
    service, dose_repo, _ = _service(uuid.uuid4())
    request = ReportRoutineDeviationRequest(
        day_offset=2, anchor="dinner", overridden_time=time(21, 0), source="CHAT", reason=None
    )

    with patch.object(SchedulingService, "_dispatch_generate"):
        await service.report_routine_deviations(patient_id, [request], {"sub": str(patient_id)})

    assert dose_repo.upsert_override.await_args.args[1] == _today_local() + timedelta(days=2)


def test_a_deviation_must_carry_exactly_one_day_reference():
    """Accepting both would leave two sources of truth for the same day, and
    accepting neither would silently fall back to a guess."""
    with pytest.raises(PydanticValidationError):
        ReportRoutineDeviationRequest(
            override_date=date(2026, 8, 14),
            day_offset=1,
            anchor="lunch",
            overridden_time=time(14, 0),
            source="CHAT",
        )
    with pytest.raises(PydanticValidationError):
        ReportRoutineDeviationRequest(anchor="lunch", overridden_time=time(14, 0), source="CHAT")


@pytest.mark.asyncio
async def test_cancelling_an_override_dispatches_a_reschedule():
    """Deleting the row is what makes the next expand_schedule fall back to
    the permanent routine for that day, so the run must still be dispatched."""
    patient_id = uuid.uuid4()
    run_id = uuid.uuid4()
    service, dose_repo, _ = _service(run_id)
    request = CancelRoutineOverrideRequest(override_date=_today_local(), anchor="dinner")

    with patch.object(SchedulingService, "_dispatch_generate") as dispatch:
        result = await service.cancel_routine_override(patient_id, request, {"sub": str(patient_id)})

    dose_repo.delete_override.assert_awaited_once()
    dispatch.assert_called_once()
    assert result.agent_run_id == run_id


@pytest.mark.asyncio
async def test_cancelling_a_nonexistent_override_is_a_404_and_dispatches_nothing():
    patient_id = uuid.uuid4()
    service, dose_repo, _ = _service(uuid.uuid4())
    dose_repo.delete_override = AsyncMock(return_value=False)
    request = CancelRoutineOverrideRequest(override_date=_today_local(), anchor="dinner")

    with patch.object(SchedulingService, "_dispatch_generate") as dispatch:
        with pytest.raises(NotFoundException):
            await service.cancel_routine_override(patient_id, request, {"sub": str(patient_id)})

    dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_cancelling_a_past_day_is_refused():
    patient_id = uuid.uuid4()
    service, dose_repo, _ = _service(uuid.uuid4())
    request = CancelRoutineOverrideRequest(override_date=_today_local() - timedelta(days=1), anchor="dinner")

    with pytest.raises(ValidationException):
        await service.cancel_routine_override(patient_id, request, {"sub": str(patient_id)})

    dose_repo.delete_override.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_empty_report_is_refused_rather_than_dispatching_a_pointless_run():
    patient_id = uuid.uuid4()
    service, _, agent_run_repo = _service(uuid.uuid4())

    with pytest.raises(ValidationException):
        await service.report_routine_deviations(patient_id, [], {"sub": str(patient_id)})

    agent_run_repo.create_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_reporting_for_another_patient_is_forbidden():
    patient_id = uuid.uuid4()
    service, dose_repo, _ = _service(uuid.uuid4())

    with pytest.raises(ForbiddenException):
        await service.report_routine_deviations(patient_id, [_deviation("lunch", 14)], {"sub": str(uuid.uuid4())})

    dose_repo.upsert_override.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_run_already_in_flight_surfaces_as_conflict_and_stores_no_override():
    """Creating the run first is what makes this safe: the override upsert
    shares its transaction, so a rejected run leaves no orphaned ACTIVE row
    behind for a later reschedule to pick up."""
    patient_id = uuid.uuid4()
    service, _, _ = _service(uuid.uuid4(), create_run_raises=True)

    with patch.object(SchedulingService, "_dispatch_generate") as dispatch:
        with pytest.raises(ConflictException):
            await service.report_routine_deviations(patient_id, [_deviation("lunch", 14)], {"sub": str(patient_id)})

    dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_single_anchor_helper_delegates_to_the_batch_path():
    patient_id = uuid.uuid4()
    run_id = uuid.uuid4()
    service, dose_repo, agent_run_repo = _service(run_id)

    with patch.object(SchedulingService, "_dispatch_generate"):
        result = await service.report_routine_deviation(
            patient_id, _deviation("breakfast", 9), {"sub": str(patient_id)}
        )

    assert result.agent_run_id == run_id
    assert dose_repo.upsert_override.await_count == 1
    assert agent_run_repo.create_run.await_count == 1
