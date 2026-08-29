"""Pure-function tests for Stage 4 rules and escalation.

No DB, no mocks of IO — these call compute_severity/resolve_action directly,
same style as tests/test_services/test_planner.py. A SimpleNamespace stands
in for Settings (constructing a real Settings() requires env-backed required
fields unrelated to this module, per src/core/config.py).
"""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from src.modules.adherence_review.repository import (
    PriorReview,
    SeverityIndicators,
    TrendIndicators,
)
from src.modules.adherence_review.service import (
    Action,
    Severity,
    compute_severity,
    compute_trend_delta,
    primary_action,
    resolve_action,
)


def _cfg(**overrides) -> SimpleNamespace:
    defaults = dict(
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
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _ind(total, taken, skipped=0, missed=0, critical_missed=0) -> SeverityIndicators:
    return SeverityIndicators(
        patient_id=None, total=total, taken=taken, skipped=skipped, missed=missed,
        critical_missed=critical_missed,
    )


# ---------------------------------------------------------------------------
# compute_severity
# ---------------------------------------------------------------------------


class TestComputeSeverityBands:
    @pytest.mark.parametrize(
        "taken,total,expected",
        [
            (10, 10, Severity.NONE),   # 100%
            (8, 10, Severity.NONE),    # 80% -- exactly the all-clear line
            (7, 10, Severity.MILD),    # 70% -- exactly the moderate/mild line
            (5, 10, Severity.MODERATE),  # 50% -- exactly the severe/moderate line
            (4, 10, Severity.SEVERE),  # 40%
            (0, 10, Severity.SEVERE),  # 0%
        ],
    )
    def test_band_boundaries(self, taken, total, expected):
        assert compute_severity(_ind(total, taken), trend_delta=None, cfg=_cfg()) == expected

    def test_min_dose_floor_is_absolute(self):
        """4 doses, 0% taken would otherwise be SEVERE -- too little data to judge."""
        ind = _ind(total=4, taken=0)
        assert compute_severity(ind, trend_delta=None, cfg=_cfg()) == Severity.NONE

    def test_min_dose_floor_boundary_is_inclusive_of_the_configured_minimum(self):
        ind = _ind(total=5, taken=0)
        assert compute_severity(ind, trend_delta=None, cfg=_cfg()) == Severity.SEVERE


class TestComputeSeverityBumps:
    def test_critical_missed_bumps_one_level(self):
        # 90% -> band NONE, but one critical miss bumps to MILD
        ind = _ind(total=10, taken=9, critical_missed=1)
        assert compute_severity(ind, trend_delta=None, cfg=_cfg()) == Severity.MILD

    def test_critical_missed_bump_is_capped_at_severe(self):
        ind = _ind(total=10, taken=0, critical_missed=1)  # already SEVERE
        assert compute_severity(ind, trend_delta=None, cfg=_cfg()) == Severity.SEVERE

    def test_trend_alarm_bumps_one_level(self):
        ind = _ind(total=10, taken=9)  # 90% -> NONE
        assert compute_severity(ind, trend_delta=-25.0, cfg=_cfg()) == Severity.MILD

    def test_trend_alarm_boundary_is_inclusive(self):
        ind = _ind(total=10, taken=9)
        assert compute_severity(ind, trend_delta=-20.0, cfg=_cfg()) == Severity.MILD

    def test_trend_just_above_alarm_threshold_does_not_bump(self):
        ind = _ind(total=10, taken=9)
        assert compute_severity(ind, trend_delta=-19.9, cfg=_cfg()) == Severity.NONE

    def test_both_bumps_stack(self):
        # 90% (NONE) + critical miss (+1) + trend alarm (+1) = MODERATE
        ind = _ind(total=10, taken=9, critical_missed=1)
        assert compute_severity(ind, trend_delta=-25.0, cfg=_cfg()) == Severity.MODERATE

    def test_stacked_bumps_still_cap_at_severe(self):
        ind = _ind(total=10, taken=4, critical_missed=1)  # 40% -> SEVERE already
        assert compute_severity(ind, trend_delta=-99.0, cfg=_cfg()) == Severity.SEVERE


class TestComputeTrendDelta:
    def test_negative_delta_on_deterioration(self):
        current = _ind(total=10, taken=5)  # 50%
        prior = TrendIndicators(total=10, taken=9)  # 90%
        assert compute_trend_delta(current, prior) == pytest.approx(-40.0)

    def test_none_when_prior_window_is_empty(self):
        current = _ind(total=10, taken=5)
        assert compute_trend_delta(current, TrendIndicators(total=0, taken=0)) is None

    def test_none_when_prior_is_missing_entirely(self):
        current = _ind(total=10, taken=5)
        assert compute_trend_delta(current, None) is None

    def test_none_when_current_window_is_empty(self):
        current = _ind(total=0, taken=0)
        assert compute_trend_delta(current, TrendIndicators(total=10, taken=9)) is None


# ---------------------------------------------------------------------------
# resolve_action / escalation
# ---------------------------------------------------------------------------


TODAY = date(2026, 8, 29)


class TestResolveActionRejectsNone:
    def test_raises_for_severity_none(self):
        with pytest.raises(ValueError):
            resolve_action(Severity.NONE, prior=None, review_date=TODAY, cfg=_cfg())


class TestFreshEntry:
    def test_no_prior_row_is_day_one(self):
        result = resolve_action(Severity.MILD, prior=None, review_date=TODAY, cfg=_cfg())
        assert result.days_in_severity == 1
        assert result.actions == frozenset({Action.PATIENT_NOTIFICATION})

    def test_gap_in_history_resets_to_day_one(self):
        """Prior review exists but is not exactly yesterday -- a skipped
        nightly run must degrade the ladder (reset), never accelerate it."""
        stale_prior = PriorReview(review_date=TODAY - timedelta(days=5), severity="MILD", days_in_severity=4)
        result = resolve_action(Severity.MILD, prior=stale_prior, review_date=TODAY, cfg=_cfg())
        assert result.days_in_severity == 1


class TestSameSeverityContinuation:
    def test_counter_increments_and_stays_in_patient_notification_column(self):
        prior = PriorReview(review_date=TODAY - timedelta(days=1), severity="MILD", days_in_severity=1)
        result = resolve_action(Severity.MILD, prior=prior, review_date=TODAY, cfg=_cfg())
        assert result.days_in_severity == 2
        assert result.actions == frozenset({Action.PATIENT_NOTIFICATION})

    def test_mild_escalates_to_doctor_warning_at_day_three(self):
        prior = PriorReview(review_date=TODAY - timedelta(days=1), severity="MILD", days_in_severity=2)
        result = resolve_action(Severity.MILD, prior=prior, review_date=TODAY, cfg=_cfg())
        assert result.days_in_severity == 3
        assert result.actions == frozenset({Action.DOCTOR_WARNING})

    def test_severe_fires_doctor_alert_every_night_of_its_own_cooldown(self):
        # cooldown_days=3, so day1 fires, day2/day3 suppressed, day4 fires again.
        prior_day1 = None
        r1 = resolve_action(Severity.SEVERE, prior=prior_day1, review_date=TODAY, cfg=_cfg())
        assert r1.actions == frozenset({Action.DOCTOR_ALERT})

        prior_day2 = PriorReview(review_date=TODAY, severity="SEVERE", days_in_severity=1)
        r2 = resolve_action(Severity.SEVERE, prior=prior_day2, review_date=TODAY + timedelta(days=1), cfg=_cfg())
        assert r2.days_in_severity == 2
        assert r2.actions == frozenset()

        prior_day3 = PriorReview(review_date=TODAY + timedelta(days=1), severity="SEVERE", days_in_severity=2)
        r3 = resolve_action(Severity.SEVERE, prior=prior_day3, review_date=TODAY + timedelta(days=2), cfg=_cfg())
        assert r3.days_in_severity == 3
        assert r3.actions == frozenset()

        prior_day4 = PriorReview(review_date=TODAY + timedelta(days=2), severity="SEVERE", days_in_severity=3)
        r4 = resolve_action(Severity.SEVERE, prior=prior_day4, review_date=TODAY + timedelta(days=3), cfg=_cfg())
        assert r4.days_in_severity == 4
        assert r4.actions == frozenset({Action.DOCTOR_ALERT})


class TestModerateDualAction:
    def test_day_one_fires_both_patient_and_doctor_actions(self):
        result = resolve_action(Severity.MODERATE, prior=None, review_date=TODAY, cfg=_cfg())
        assert result.actions == frozenset({Action.PATIENT_NOTIFICATION, Action.DOCTOR_WARNING})

    def test_patient_notification_drops_out_at_day_three(self):
        """At day 3, PATIENT_NOTIFICATION is no longer part of the cell at
        all -- whether DOCTOR_WARNING itself fires *that specific night* is
        a separate cooldown question, covered by the continuous-cooldown
        test below (day 3 lands on offset 2 from day 1, not a multiple of
        the default 3-day cooldown, so it is legitimately silent here)."""
        prior = PriorReview(review_date=TODAY - timedelta(days=1), severity="MODERATE", days_in_severity=2)
        result = resolve_action(Severity.MODERATE, prior=prior, review_date=TODAY, cfg=_cfg())
        assert result.days_in_severity == 3
        assert Action.PATIENT_NOTIFICATION not in result.actions

    def test_doctor_warning_cooldown_counts_continuously_from_day_one_not_from_day_three(self):
        """DOCTOR_WARNING has been recommended since day 1 of MODERATE, not
        since day 3 -- its own cooldown must not reset just because
        PATIENT_NOTIFICATION stopped accompanying it."""
        # day1 fires (offset 0). day2 -> offset 1, cooldown=3, suppressed.
        prior_day1 = PriorReview(review_date=TODAY, severity="MODERATE", days_in_severity=1)
        r2 = resolve_action(Severity.MODERATE, prior=prior_day1, review_date=TODAY + timedelta(days=1), cfg=_cfg())
        assert r2.days_in_severity == 2
        assert Action.DOCTOR_WARNING not in r2.actions

        # day4 -> offset 3, 3 % 3 == 0, fires again.
        prior_day3 = PriorReview(
            review_date=TODAY + timedelta(days=2), severity="MODERATE", days_in_severity=3
        )
        r4 = resolve_action(
            Severity.MODERATE, prior=prior_day3, review_date=TODAY + timedelta(days=3), cfg=_cfg()
        )
        assert r4.days_in_severity == 4
        assert r4.actions == frozenset({Action.DOCTOR_WARNING})


class TestEscalationOnWorsening:
    def test_severity_increase_resets_counter_and_always_fires(self):
        """Escalating MILD -> SEVERE must fire immediately, bypassing
        whatever cooldown SEVERE's ladder cell would otherwise imply."""
        prior = PriorReview(review_date=TODAY - timedelta(days=1), severity="MILD", days_in_severity=4)
        result = resolve_action(Severity.SEVERE, prior=prior, review_date=TODAY, cfg=_cfg())
        assert result.days_in_severity == 1
        assert result.actions == frozenset({Action.DOCTOR_ALERT})


class TestImprovementIsSilent:
    def test_lower_severity_than_prior_suppresses_all_actions(self):
        prior = PriorReview(review_date=TODAY - timedelta(days=1), severity="SEVERE", days_in_severity=3)
        result = resolve_action(Severity.MILD, prior=prior, review_date=TODAY, cfg=_cfg())
        assert result.actions == frozenset()
        assert result.days_in_severity == 1


class TestPrimaryAction:
    def test_empty_set_is_none(self):
        assert primary_action(frozenset()) == Action.NONE

    def test_picks_the_most_consequential_action(self):
        assert primary_action(frozenset({Action.PATIENT_NOTIFICATION, Action.DOCTOR_WARNING})) == Action.DOCTOR_WARNING

    def test_single_action_passes_through(self):
        assert primary_action(frozenset({Action.PATIENT_NOTIFICATION})) == Action.PATIENT_NOTIFICATION


class TestMisconfiguredEscalationDays:
    def test_non_increasing_days_raise_at_first_use(self):
        bad_cfg = _cfg(adherence_review_escalation_day1=5, adherence_review_escalation_day3=3, adherence_review_escalation_day5=1)
        with pytest.raises(ValueError):
            resolve_action(Severity.MILD, prior=None, review_date=TODAY, cfg=bad_cfg)
