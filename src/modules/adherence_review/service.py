"""Rules and escalation for the nightly graded-adherence review.

Pure functions only — no DB, no IO, directly unit-testable like
src/modules/agents/planner.py. Severity is decided here and ONLY here;
Stage 5's LLM step receives it as already-fixed context and has no field in
its output schema through which it could change it.

Two design decisions made while implementing the plan in
docs/graded-adherence-implementation.md Stage 4, documented here because the
plan's prose underspecifies them:

1. compute_severity's bump step (critical_missed / trend) can raise a
   patient OUT of NONE, not just between MILD/MODERATE/SEVERE. The plan's
   pseudocode shows each band as an early `return`, which would make the
   bumps unreachable if taken literally — read together with "then two
   escalating adjustments, applied after the band", the intent is clearly
   that bumps apply after band selection, not that they are dead code. A
   patient at 95% adherence who missed one anticoagulant dose still
   surfaces as at least MILD; that single critical miss is exactly the
   thing the fast-path fixture cares about, and the nightly review should
   not stay silent on it just because the raw rate still looks fine.

2. The escalation ladder's MODERATE/day-1 cell fires two actions at once
   (PATIENT_NOTIFICATION and DOCTOR_WARNING), but `adherence_reviews
   .action_taken` is a single column (migration 0022). resolve_action
   therefore returns the full action set; collapsing it to one column value
   for storage is Stage 6's job (see AdherenceEscalationService.primary_action
   below), not something decided here. Both `alert_id` and
   `notification_delivery_id` on that row are independently nullable, so a
   single review row can legitimately reference both a notification and an
   alert created the same night.

Cooldown (Stage 4.3) is implemented as a per-action repeat cadence measured
from the day each action's ladder cell first applies to this severity, not a
separate lookup: "how many nights has the tier this action belongs to been
continuously recommended" is derivable from `days_in_severity` alone, which
Query 6 (get_prior_reviews) already supplies. A fresh escalation always has
an offset of zero from its own cell's start day, so it always fires — that
is what satisfies the plan's "unless severity increased" carve-out, with no
separate special case needed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import FrozenSet, Optional

from src.core.config import Settings
from src.modules.adherence_review.repository import (
    PriorReview,
    SeverityIndicators,
    TrendIndicators,
)


class Severity(str, Enum):
    NONE = "NONE"
    MILD = "MILD"
    MODERATE = "MODERATE"
    SEVERE = "SEVERE"


class Action(str, Enum):
    NONE = "NONE"
    PATIENT_NOTIFICATION = "PATIENT_NOTIFICATION"
    DOCTOR_WARNING = "DOCTOR_WARNING"
    DOCTOR_ALERT = "DOCTOR_ALERT"


# Matches the DB CHECK constraint's allowed action_taken values
# (migration 0022_adherence_reviews) and this module's own primary_action
# ordering below.
_LEVELS = [Severity.NONE, Severity.MILD, Severity.MODERATE, Severity.SEVERE]

# Highest-consequence action first: used by primary_action to collapse a
# multi-action night into the single column adherence_reviews.action_taken
# stores. NOT used by resolve_action itself, which always returns the full set.
_ACTION_SEVERITY_ORDER = [Action.NONE, Action.PATIENT_NOTIFICATION, Action.DOCTOR_WARNING, Action.DOCTOR_ALERT]

_DOCTOR_FACING = frozenset({Action.DOCTOR_WARNING, Action.DOCTOR_ALERT})


def _raise_one_level(severity: Severity) -> Severity:
    """Capped at SEVERE. Can raise out of NONE — see module docstring point 1."""
    idx = _LEVELS.index(severity)
    return _LEVELS[min(idx + 1, len(_LEVELS) - 1)]


def compute_severity(
    ind: SeverityIndicators, trend_delta: Optional[float], cfg: Settings
) -> Severity:
    """Deterministic, no AI. The min-dose floor is absolute and comes first —
    same reasoning as the zero-dose dashboard-band fix already on this
    branch: a patient with too few doses in the window has no meaningful
    rate, and guessing at one produces a false alert."""
    if ind.total < cfg.adherence_review_min_doses:
        return Severity.NONE

    rate = ind.taken / ind.total * 100
    if rate < cfg.adherence_severe_threshold:
        severity = Severity.SEVERE
    elif rate < cfg.adherence_moderate_threshold:
        severity = Severity.MODERATE
    elif rate < cfg.adherence_mild_threshold:
        severity = Severity.MILD
    else:
        severity = Severity.NONE

    if ind.critical_missed > 0:
        severity = _raise_one_level(severity)
    if trend_delta is not None and trend_delta <= cfg.adherence_trend_alarm_delta:
        severity = _raise_one_level(severity)
    return severity


def compute_trend_delta(
    current: SeverityIndicators, prior: Optional[TrendIndicators]
) -> Optional[float]:
    """current_rate - prior_rate, so a fast deterioration is negative. None
    when either window has no doses to rate — a brand-new patient with
    nothing in the prior window has no trend yet, not a 100-point crash."""
    if prior is None or prior.total == 0 or current.total == 0:
        return None
    current_rate = current.taken / current.total * 100
    prior_rate = prior.taken / prior.total * 100
    return current_rate - prior_rate


def primary_action(actions: FrozenSet[Action]) -> Action:
    """Collapse a possibly-multi-action night to the single value
    adherence_reviews.action_taken stores, ranked by consequence. A doctor
    filtering reviews by action_taken='DOCTOR_WARNING' must still find the
    MODERATE/day-1 nights that also notified the patient — see module
    docstring point 2."""
    if not actions:
        return Action.NONE
    return max(actions, key=_ACTION_SEVERITY_ORDER.index)


@dataclass(frozen=True)
class EscalationResult:
    days_in_severity: int
    actions: FrozenSet[Action]


def _escalation_days(cfg: Settings) -> tuple[int, int, int]:
    d1 = cfg.adherence_review_escalation_day1
    d3 = cfg.adherence_review_escalation_day3
    d5 = cfg.adherence_review_escalation_day5
    if not (d1 < d3 < d5):
        raise ValueError(
            f"adherence_review_escalation_day1/3/5 must be strictly increasing, got {d1}, {d3}, {d5}"
        )
    return d1, d3, d5


def _ladder_cell(severity: Severity, days_in_severity: int, cfg: Settings) -> tuple[int, FrozenSet[Action]]:
    """The un-throttled action set the ladder recommends for one
    (severity, days_in_severity) pair, plus the day that cell's streak
    started (for cooldown offset calculation below).

    | Severity | day 1                              | day 3          | day 5+         |
    |----------|-------------------------------------|----------------|----------------|
    | MILD     | PATIENT_NOTIFICATION                | PATIENT_NOTIFICATION (until day3) -> DOCTOR_WARNING | DOCTOR_WARNING |
    | MODERATE | PATIENT_NOTIFICATION + DOCTOR_WARNING | DOCTOR_WARNING (PN drops out)     | DOCTOR_WARNING |
    | SEVERE   | DOCTOR_ALERT                         | DOCTOR_ALERT   | DOCTOR_ALERT   |

    DOCTOR_WARNING's streak-start for MODERATE is day1, not day3: it has
    been continuously recommended since day1 (PATIENT_NOTIFICATION merely
    stops accompanying it), so its own cooldown cadence counts from day1
    without resetting when the cell's other member drops out.
    """
    d1, d3, _d5 = _escalation_days(cfg)

    if severity == Severity.SEVERE:
        return d1, frozenset({Action.DOCTOR_ALERT})

    if severity == Severity.MODERATE:
        if days_in_severity < d3:
            return d1, frozenset({Action.PATIENT_NOTIFICATION, Action.DOCTOR_WARNING})
        return d1, frozenset({Action.DOCTOR_WARNING})

    if severity == Severity.MILD:
        if days_in_severity < d3:
            return d1, frozenset({Action.PATIENT_NOTIFICATION})
        return d3, frozenset({Action.DOCTOR_WARNING})

    raise ValueError(f"resolve_action must not be called for {severity!r}")


def _cooldown_days_for(action: Action, cfg: Settings) -> int:
    if action in _DOCTOR_FACING:
        return cfg.adherence_review_cooldown_days
    return cfg.adherence_review_patient_cooldown_days


def _passes_cooldown(days_in_severity: int, column_start_day: int, cooldown_days: int) -> bool:
    """True on the first day a cell applies (offset 0, always fires — this
    is what makes a fresh escalation bypass cooldown for free) and every
    `cooldown_days`-th day after that."""
    return (days_in_severity - column_start_day) % cooldown_days == 0


def resolve_action(
    severity: Severity,
    prior: Optional[PriorReview],
    review_date: date,
    cfg: Settings,
) -> EscalationResult:
    """The only place escalation state is computed. `prior` is this
    patient's single most recent review at or after some lookback cutoff
    (Query 6) — never a full history scan.

    - No prior row, or prior.review_date is not exactly review_date - 1 day:
      a fresh entry (first night, or a gap from a skipped run) -> counter
      resets to 1. A skipped nightly run therefore costs one escalation
      reset, delaying escalation rather than accelerating it — the
      conservative failure direction.
    - Prior severity lower (patient got worse): act at the new, higher
      level immediately, counter resets to 1.
    - Prior severity equal: counter increments; the ladder cell for the new
      count decides what fires, subject to cooldown.
    - Prior severity higher (patient improved): counter resets to 1, and
      the review is silenced regardless of what today's severity would
      otherwise imply. Silence is the correct response to recovery.
    """
    if severity == Severity.NONE:
        raise ValueError("resolve_action must not be called for Severity.NONE")

    is_fresh = prior is None or prior.review_date != review_date - timedelta(days=1)
    if is_fresh:
        days_in_severity = 1
    else:
        prior_severity = Severity(prior.severity)
        prior_rank = _LEVELS.index(prior_severity)
        current_rank = _LEVELS.index(severity)
        if prior_rank < current_rank:
            days_in_severity = 1
        elif prior_rank == current_rank:
            days_in_severity = prior.days_in_severity + 1
        else:
            return EscalationResult(days_in_severity=1, actions=frozenset())

    column_start, ladder_actions = _ladder_cell(severity, days_in_severity, cfg)
    fired = frozenset(
        action
        for action in ladder_actions
        if _passes_cooldown(days_in_severity, column_start, _cooldown_days_for(action, cfg))
    )
    return EscalationResult(days_in_severity=days_in_severity, actions=fired)
