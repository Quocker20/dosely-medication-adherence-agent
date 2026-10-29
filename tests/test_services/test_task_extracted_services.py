"""Unit tests for the business logic extracted from agents/tasks.py (O-06):
the daily adverse-event summary and the caregiver adherence report."""
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.adherence.adverse_event_summary_service import (
    AdverseEventSummaryService,
    build_daily_summary_message,
    group_events_by_patient,
)
from src.modules.adherence.caregiver_report_service import (
    CaregiverReportService,
    build_report_body,
    compute_adherence_stats,
)

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


def _event(patient_id, names):
    return SimpleNamespace(
        id=uuid.uuid4(),
        patient_id=patient_id,
        symptoms=[{"name": n} for n in names] + [{"other": "no-name"}],
    )


def test_group_events_by_patient_keeps_order():
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    e1, e2, e3 = _event(p1, ["a"]), _event(p2, ["b"]), _event(p1, ["c"])
    grouped = group_events_by_patient([e1, e2, e3])
    assert list(grouped) == [p1, p2]
    assert grouped[p1] == [e1, e3]


def test_daily_summary_message_dedupes_and_sorts_symptom_names():
    pid = uuid.uuid4()
    events = [_event(pid, ["ho", "chóng mặt"]), _event(pid, ["ho"])]
    message, names = build_daily_summary_message(events)
    assert names == sorted({"ho", "chóng mặt"})
    assert message.startswith("Tổng hợp 2 ghi nhận triệu chứng trong ngày: ")
    assert "ho" in message and "chóng mặt" in message


@pytest.mark.asyncio
async def test_adverse_event_summary_creates_one_alert_per_patient():
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    events = [_event(p1, ["ho"]), _event(p1, ["sốt"]), _event(p2, ["đau đầu"])]
    event_repo = MagicMock()
    event_repo.list_pending_daily_summary = AsyncMock(return_value=events)
    event_repo.mark_summarized = AsyncMock()
    alert_repo = MagicMock()
    alert_repo.create_alert = AsyncMock(side_effect=lambda **kw: SimpleNamespace(id=uuid.uuid4()))

    service = AdverseEventSummaryService(event_repository=event_repo, alert_repository=alert_repo)
    count = await service.summarize_daily(NOW)

    assert count == 2
    assert alert_repo.create_alert.await_count == 2
    first = alert_repo.create_alert.await_args_list[0].kwargs
    assert first["patient_id"] == p1
    assert first["alert_type"] == "SUSPECTED_ADVERSE_EVENT"
    assert first["severity"] == "MEDIUM"
    assert first["metadata"]["summary_type"] == "DAILY"
    assert first["metadata"]["adverse_event_ids"] == [str(events[0].id), str(events[1].id)]
    assert event_repo.mark_summarized.await_count == 2


@pytest.mark.asyncio
async def test_adverse_event_summary_noop_when_nothing_pending():
    event_repo = MagicMock()
    event_repo.list_pending_daily_summary = AsyncMock(return_value=[])
    event_repo.mark_summarized = AsyncMock()
    alert_repo = MagicMock()
    alert_repo.create_alert = AsyncMock()
    service = AdverseEventSummaryService(event_repository=event_repo, alert_repository=alert_repo)
    assert await service.summarize_daily(NOW) == 0
    alert_repo.create_alert.assert_not_awaited()


def test_compute_adherence_stats_counts_taken_and_missed():
    stats = compute_adherence_stats(["TAKEN", "MISSED", "SKIPPED", "PENDING"])
    assert (stats.total, stats.taken, stats.missed) == (4, 1, 2)
    assert stats.rate == pytest.approx(25.0)


def test_compute_adherence_stats_empty_is_full_rate():
    stats = compute_adherence_stats([])
    assert (stats.total, stats.taken, stats.missed, stats.rate) == (0, 0, 0, 100.0)


def test_report_body_contains_figures():
    body = build_report_body(7, "Bác Hùng", compute_adherence_stats(["TAKEN", "MISSED"]))
    assert "(7 ngày qua)" in body
    assert "Người bệnh: Bác Hùng" in body
    assert "Tổng số liều: 2" in body
    assert "Đã uống: 1" in body
    assert "Quên/Bỏ lỡ: 1" in body
    assert "50.0%" in body


@pytest.mark.asyncio
async def test_report_service_returns_empty_when_no_link_due():
    db = MagicMock()
    begin_ctx = MagicMock()
    begin_ctx.__aenter__ = AsyncMock(return_value=None)
    begin_ctx.__aexit__ = AsyncMock(return_value=False)
    db.begin.return_value = begin_ctx
    caregiver_repo = MagicMock()
    caregiver_repo.claim_due_reports = AsyncMock(return_value=[])
    service = CaregiverReportService(
        db=db,
        caregiver_repository=caregiver_repo,
        notification_repository=MagicMock(),
        scheduled_dose_repository=MagicMock(),
        patient_repository=MagicMock(),
    )
    assert await service.create_due_reports(NOW, 7) == []
