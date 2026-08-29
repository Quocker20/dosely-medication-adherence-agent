"""AdherenceReviewService.run_nightly_review: Phase A/B/C wiring, action
routing, the LLM-call cap, idempotent replay, and the continuity fix for
silenced (improving) patients.

All four repositories and the LLM call are mocked -- this tests the
orchestrator's own logic, not the SQL underneath (that's
test_adherence_review_indicators.py) or the rules underneath (that's
test_adherence_review_rules.py).
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from src.modules.adherence_review.llm import FALLBACK_REMEDY_ANALYSIS, RemedyAnalysis, RemedyClass
from src.modules.adherence_review.repository import PatientRosterEntry, PriorReview, SeverityIndicators
from src.modules.adherence_review.service import AdherenceReviewService

REVIEW_DATE = date(2026, 8, 29)


def _cfg(**overrides) -> SimpleNamespace:
    defaults = dict(
        adherence_review_enabled=True,
        adherence_review_window_days=7,
        adherence_review_timezone="Asia/Ho_Chi_Minh",
        missed_dose_overdue_minutes=60,
        adherence_review_min_doses=5,
        adherence_severe_threshold=50.0,
        adherence_moderate_threshold=70.0,
        adherence_mild_threshold=80.0,
        adherence_trend_alarm_delta=-20.0,
        adherence_review_escalation_day1=1,
        adherence_review_escalation_day3=3,
        adherence_review_escalation_day5=5,
        adherence_review_cooldown_days=3,
        adherence_review_patient_cooldown_days=1,
        adherence_review_llm_timeout_seconds=20,
        adherence_review_max_llm_calls=300,
        adherence_review_patient_send_from=8,
        adherence_review_patient_send_to=20,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _severity_row(patient_id, total, taken, skipped=0, missed=None, critical_missed=0) -> SeverityIndicators:
    if missed is None:
        missed = total - taken - skipped
    return SeverityIndicators(
        patient_id=patient_id, total=total, taken=taken, skipped=skipped,
        missed=missed, critical_missed=critical_missed,
    )


def _make_service(indicator_repo=None, review_repo=None, alert_repo=None, notification_repo=None):
    db = MagicMock()
    begin_ctx = MagicMock()
    begin_ctx.__aenter__ = AsyncMock(return_value=None)
    begin_ctx.__aexit__ = AsyncMock(return_value=False)
    db.begin.return_value = begin_ctx

    indicator_repo = indicator_repo or AsyncMock()
    indicator_repo.get_severity_indicators.return_value = []
    indicator_repo.get_trend_indicators.return_value = {}
    indicator_repo.get_slot_breakdown.return_value = {}
    indicator_repo.get_medication_breakdown.return_value = {}
    indicator_repo.get_symptom_evidence.return_value = {}
    indicator_repo.get_prior_reviews.return_value = {}
    indicator_repo.get_patient_roster.return_value = {}

    review_repo = review_repo or AsyncMock()
    review_repo.insert_review.return_value = SimpleNamespace(id=uuid.uuid4())

    alert_repo = alert_repo or AsyncMock()
    alert_repo.create_alert.return_value = SimpleNamespace(
        id=uuid.uuid4(), patient_id=uuid.uuid4(), assigned_doctor_id=None,
        triggered_by_type="ADHERENCE_REVIEW", triggered_by_id=None,
        alert_type="WARNING", severity="MEDIUM", status="OPEN",
        message="x", created_at=datetime.now(timezone.utc),
    )

    notification_repo = notification_repo or AsyncMock()
    notification_repo.create_grouped_delivery.return_value = SimpleNamespace(id=uuid.uuid4())

    service = AdherenceReviewService(
        db=db,
        indicator_repository=indicator_repo,
        review_repository=review_repo,
        alert_repository=alert_repo,
        notification_repository=notification_repo,
    )
    return service, indicator_repo, review_repo, alert_repo, notification_repo


def _patched(cfg, classify_result=None):
    """Patches get_settings, classify_remedy, and the two post-commit
    side-effect calls this module makes -- returns the ExitStack-style list
    of patchers to stop."""
    patchers = [
        patch("src.modules.adherence_review.service.get_settings", return_value=cfg),
        patch("src.modules.adherence_review.service.publish_dashboard_event", new=AsyncMock()),
        patch("src.modules.adherence_review.service.invalidate_prefix", new=AsyncMock()),
        patch("src.modules.agents.tasks.send_notification_task", new=MagicMock()),
    ]
    if classify_result is not None:
        patchers.append(patch("src.modules.adherence_review.service.classify_remedy", new=AsyncMock(return_value=classify_result)))
    for p in patchers:
        p.start()
    return patchers


def _stop(patchers):
    for p in patchers:
        p.stop()


class TestFeatureGate:
    @pytest.mark.asyncio
    async def test_disabled_flag_skips_before_any_query(self):
        service, indicator_repo, review_repo, _, _ = _make_service()
        patchers = _patched(_cfg(adherence_review_enabled=False))
        try:
            stats = await service.run_nightly_review(REVIEW_DATE)
        finally:
            _stop(patchers)
        assert stats == {"skipped": 1}
        indicator_repo.get_severity_indicators.assert_not_called()


class TestSeverityGate:
    @pytest.mark.asyncio
    async def test_fully_adherent_patient_produces_no_review(self):
        patient_id = uuid.uuid4()
        service, indicator_repo, review_repo, _, _ = _make_service()
        indicator_repo.get_severity_indicators.return_value = [_severity_row(patient_id, total=10, taken=10)]
        patchers = _patched(_cfg())
        try:
            stats = await service.run_nightly_review(REVIEW_DATE)
        finally:
            _stop(patchers)
        assert stats["candidates"] == 0
        review_repo.insert_review.assert_not_called()

    @pytest.mark.asyncio
    async def test_below_min_doses_produces_no_review(self):
        patient_id = uuid.uuid4()
        service, indicator_repo, review_repo, _, _ = _make_service()
        indicator_repo.get_severity_indicators.return_value = [_severity_row(patient_id, total=2, taken=0)]
        patchers = _patched(_cfg())
        try:
            await service.run_nightly_review(REVIEW_DATE)
        finally:
            _stop(patchers)
        review_repo.insert_review.assert_not_called()


class TestActionRouting:
    @pytest.mark.asyncio
    async def test_mild_day_one_creates_patient_notification_only(self):
        patient_id = uuid.uuid4()
        service, indicator_repo, review_repo, alert_repo, notification_repo = _make_service()
        indicator_repo.get_severity_indicators.return_value = [_severity_row(patient_id, total=10, taken=7)]  # 70% -> MILD
        indicator_repo.get_patient_roster.return_value = {
            patient_id: PatientRosterEntry(name="A", timezone="Asia/Ho_Chi_Minh", status="ACTIVE")
        }
        analysis = RemedyAnalysis(
            remedy_class=RemedyClass.RESCHEDULE_TIMING, confidence="high",
            reasoning_doctor="x", message_patient="Nhắc nhở nhẹ nhàng.",
        )
        patchers = _patched(_cfg(), classify_result=analysis)
        try:
            stats = await service.run_nightly_review(REVIEW_DATE)
        finally:
            _stop(patchers)

        assert stats["reviewed"] == 1
        notification_repo.create_grouped_delivery.assert_awaited_once()
        alert_repo.create_alert.assert_not_called()
        fields = review_repo.insert_review.await_args.args[0]
        assert fields["action_taken"] == "PATIENT_NOTIFICATION"
        assert fields["severity"] == "MILD"

    @pytest.mark.asyncio
    async def test_severe_creates_red_alert_and_publishes(self):
        patient_id = uuid.uuid4()
        service, indicator_repo, review_repo, alert_repo, notification_repo = _make_service()
        indicator_repo.get_severity_indicators.return_value = [_severity_row(patient_id, total=10, taken=2)]  # 20% -> SEVERE
        patchers = _patched(_cfg(), classify_result=FALLBACK_REMEDY_ANALYSIS)
        try:
            with patch("src.modules.adherence_review.service.publish_dashboard_event", new=AsyncMock()) as mock_publish, \
                 patch("src.modules.adherence_review.service.invalidate_prefix", new=AsyncMock()) as mock_invalidate:
                await service.run_nightly_review(REVIEW_DATE)
        finally:
            _stop(patchers)

        alert_repo.create_alert.assert_awaited_once()
        _, kwargs = alert_repo.create_alert.await_args
        assert kwargs["alert_type"] == "RED_ALERT"
        assert kwargs["severity"] == "HIGH"
        assert kwargs["triggered_by_type"] == "ADHERENCE_REVIEW"
        notification_repo.create_grouped_delivery.assert_not_called()
        mock_publish.assert_awaited_once()
        assert mock_publish.await_args.args[0] == "alert.opened"
        mock_invalidate.assert_awaited_once_with("dash:patients")

    @pytest.mark.asyncio
    async def test_moderate_day_one_creates_both_actions(self):
        patient_id = uuid.uuid4()
        service, indicator_repo, review_repo, alert_repo, notification_repo = _make_service()
        indicator_repo.get_severity_indicators.return_value = [_severity_row(patient_id, total=10, taken=6)]  # 60% -> MODERATE
        analysis = RemedyAnalysis(
            remedy_class=RemedyClass.DISENGAGEMENT, confidence="medium",
            reasoning_doctor="x", message_patient="Nhắc nhở.",
        )
        patchers = _patched(_cfg(), classify_result=analysis)
        try:
            await service.run_nightly_review(REVIEW_DATE)
        finally:
            _stop(patchers)

        alert_repo.create_alert.assert_awaited_once()
        notification_repo.create_grouped_delivery.assert_awaited_once()
        _, alert_kwargs = alert_repo.create_alert.await_args
        assert alert_kwargs["alert_type"] == "WARNING"
        assert alert_kwargs["severity"] == "MEDIUM"
        fields = review_repo.insert_review.await_args.args[0]
        # primary_action ranks DOCTOR_WARNING above PATIENT_NOTIFICATION.
        assert fields["action_taken"] == "DOCTOR_WARNING"


class TestImprovementContinuity:
    @pytest.mark.asyncio
    async def test_silenced_patient_still_gets_a_review_row_for_continuity(self):
        """The bug this test guards against: skipping persistence entirely
        for an improving/silenced patient would make tomorrow night's
        resolve_action find no prior row, treat the patient as brand new,
        and incorrectly reset the escalation ladder instead of continuing
        the (silenced) streak."""
        patient_id = uuid.uuid4()
        service, indicator_repo, review_repo, alert_repo, notification_repo = _make_service()
        indicator_repo.get_severity_indicators.return_value = [_severity_row(patient_id, total=10, taken=7)]  # 70% -> MILD
        indicator_repo.get_prior_reviews.return_value = {
            patient_id: PriorReview(review_date=REVIEW_DATE - timedelta(days=1), severity="SEVERE", days_in_severity=3)
        }
        patchers = _patched(_cfg())
        try:
            stats = await service.run_nightly_review(REVIEW_DATE)
        finally:
            _stop(patchers)

        assert stats["silenced"] == 1
        review_repo.insert_review.assert_awaited_once()
        fields = review_repo.insert_review.await_args.args[0]
        assert fields["action_taken"] == "NONE"
        assert fields["days_in_severity"] == 1
        alert_repo.create_alert.assert_not_called()
        notification_repo.create_grouped_delivery.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_llm_call_for_a_silenced_patient(self):
        patient_id = uuid.uuid4()
        service, indicator_repo, _, _, _ = _make_service()
        indicator_repo.get_severity_indicators.return_value = [_severity_row(patient_id, total=10, taken=7)]
        indicator_repo.get_prior_reviews.return_value = {
            patient_id: PriorReview(review_date=REVIEW_DATE - timedelta(days=1), severity="SEVERE", days_in_severity=1)
        }
        patchers = _patched(_cfg())
        with patch("src.modules.adherence_review.service.classify_remedy", new=AsyncMock()) as mock_classify:
            try:
                await service.run_nightly_review(REVIEW_DATE)
            finally:
                _stop(patchers)
        mock_classify.assert_not_called()


class TestLlmCap:
    @pytest.mark.asyncio
    async def test_cap_drops_least_severe_candidate_first(self):
        severe_id, mild_id = uuid.uuid4(), uuid.uuid4()
        service, indicator_repo, review_repo, _, _ = _make_service()
        indicator_repo.get_severity_indicators.return_value = [
            _severity_row(severe_id, total=10, taken=2),   # 20% -> SEVERE
            _severity_row(mild_id, total=10, taken=7),     # 70% -> MILD
        ]
        cfg = _cfg(adherence_review_max_llm_calls=1)
        patchers = _patched(cfg)
        with patch(
            "src.modules.adherence_review.service.classify_remedy",
            new=AsyncMock(return_value=FALLBACK_REMEDY_ANALYSIS),
        ) as mock_classify:
            try:
                stats = await service.run_nightly_review(REVIEW_DATE)
            finally:
                _stop(patchers)

        assert stats["llm_calls"] == 1
        assert stats["llm_dropped_by_cap"] == 1
        mock_classify.assert_awaited_once()
        assert mock_classify.await_args.args[0] == severe_id
        # Both candidates still get a review row -- the cap only affects
        # whether classify_remedy is called, never whether the rule-decided
        # severity/action is acted on.
        assert review_repo.insert_review.await_count == 2


class TestIdempotentReplay:
    @pytest.mark.asyncio
    async def test_duplicate_review_insert_is_caught_and_nothing_downstream_runs(self):
        patient_id = uuid.uuid4()
        service, indicator_repo, review_repo, alert_repo, notification_repo = _make_service()
        indicator_repo.get_severity_indicators.return_value = [_severity_row(patient_id, total=10, taken=2)]  # SEVERE
        review_repo.insert_review.side_effect = IntegrityError("stmt", {}, Exception("dup"))
        patchers = _patched(_cfg(), classify_result=FALLBACK_REMEDY_ANALYSIS)
        try:
            stats = await service.run_nightly_review(REVIEW_DATE)
        finally:
            _stop(patchers)

        assert stats["replayed"] == 1
        assert stats["reviewed"] == 0
        # insert_review is called FIRST in _persist_one -- if it raises,
        # neither the alert nor the notification branch should ever run,
        # which is the actual race-safety guarantee (not just a side note).
        alert_repo.create_alert.assert_not_called()
        notification_repo.create_grouped_delivery.assert_not_called()
