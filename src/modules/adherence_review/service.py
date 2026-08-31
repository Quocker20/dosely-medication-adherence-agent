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
   for storage is Stage 6's job (see primary_action below), not something
   decided here. Both `alert_id` and
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

import logging
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time as dtime, timedelta
from typing import Any, Dict, FrozenSet, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.schemas import PageResponse
from src.core.cache import invalidate_prefix
from src.core.config import Settings, get_settings
from src.core.redis import publish_dashboard_event
from src.modules.adherence.repository import AlertRepository, NotificationRepository
from src.modules.adherence.schemas import AlertDetailResponse
from src.modules.adherence_review.enums import Action, Severity
from src.modules.adherence_review.llm import (
    FALLBACK_REMEDY_ANALYSIS,
    RemedyAnalysis,
    RemedyContext,
    classify_remedy,
    enforce_patient_message_gate,
)
from src.modules.adherence_review.repository import (
    AdherenceIndicatorRepository,
    AdherenceReviewRepository,
    PriorReview,
    SeverityIndicators,
    TrendIndicators,
    compute_window_bounds,
)
from src.modules.adherence_review.schemas import AdherenceReviewDetailResponse


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


logger = logging.getLogger(__name__)


def _next_daytime_slot(now_utc: datetime, timezone_name: str, send_from_hour: int, send_to_hour: int) -> datetime:
    """Next UTC instant inside [send_from_hour, send_to_hour) local time.

    If `now` already falls inside the window, returns `now` unchanged
    (delivery fires immediately). Otherwise returns send_from_hour local on
    the earliest day that is still ahead of `now` -- today if the window
    hasn't opened yet, tomorrow if it has already closed. The nightly job
    runs well before send_from_hour by design (05:00 vs. an 08:00 window),
    so the common case is always "today at send_from_hour local"."""
    tz = ZoneInfo(timezone_name)
    local_now = now_utc.astimezone(tz)
    if send_from_hour <= local_now.hour < send_to_hour:
        return now_utc
    candidate_date = local_now.date() if local_now.hour < send_from_hour else local_now.date() + timedelta(days=1)
    candidate_local = datetime.combine(candidate_date, dtime(hour=send_from_hour), tzinfo=tz)
    return candidate_local.astimezone(UTC)


@dataclass(frozen=True)
class _Candidate:
    """One patient's Phase B outcome, carried into Phase C."""

    patient_id: uuid.UUID
    severity: Severity
    escalation: EscalationResult
    indicators: SeverityIndicators
    timezone: str


class AdherenceReviewService:
    """Orchestrates one nightly graded-adherence review run (Stage 6):

        Phase A (one REPEATABLE READ transaction) -> six indicator reads, commit, close
        Phase B (no DB at all)                     -> compute_severity / resolve_action, then LLM calls for the gated set
        Phase C (one transaction PER PATIENT)       -> insert review + alert/notification

    Phase C is per-patient, not one giant transaction, so a single patient's
    idempotency collision or constraint violation cannot roll back the
    whole night's work for every other patient (plan 6.2).
    """

    def __init__(
        self,
        db: AsyncSession,
        indicator_repository: AdherenceIndicatorRepository,
        review_repository: AdherenceReviewRepository,
        alert_repository: AlertRepository,
        notification_repository: NotificationRepository,
    ) -> None:
        self._db = db
        self._indicators = indicator_repository
        self._reviews = review_repository
        self._alerts = alert_repository
        self._notifications = notification_repository

    async def run_nightly_review(self, review_date: date) -> Dict[str, int]:
        """Entry point for tasks.py:scan_adherence_review. `review_date` is
        the deployment-local calendar date the run is FOR (today, at the
        moment the Beat job fires) -- the window analyzed is the
        window_days before it, never including it."""
        settings = get_settings()
        if not settings.adherence_review_enabled:
            logger.info("Adherence review disabled via settings; skipping run for %s", review_date)
            return {"skipped": 1}

        candidates, indicator_cache = await self._phase_a_and_b(review_date, settings)

        stats = {
            "candidates": len(candidates),
            "llm_calls": 0,
            "llm_dropped_by_cap": 0,
            "reviewed": 0,
            "silenced": 0,
            "replayed": 0,
            "failed": 0,
        }

        # Sort by severity descending before capping LLM calls, so a loose
        # threshold drops the LEAST severe patients first, never the most
        # severe (plan 6.5).
        severity_rank = {Severity.MILD: 1, Severity.MODERATE: 2, Severity.SEVERE: 3}
        ordered = sorted(candidates, key=lambda c: severity_rank[c.severity], reverse=True)
        llm_eligible_ids = {c.patient_id for c in ordered[: settings.adherence_review_max_llm_calls]}
        stats["llm_dropped_by_cap"] = len(ordered) - len(llm_eligible_ids)
        if stats["llm_dropped_by_cap"] > 0:
            logger.warning(
                "Adherence review: max_llm_calls cap dropped %d of %d candidates for %s",
                stats["llm_dropped_by_cap"], len(ordered), review_date,
            )

        for candidate in ordered:
            # A silenced (improving) candidate still needs its review row
            # persisted with action_taken=NONE, even though nothing fires
            # tonight -- resolve_action's own is_fresh check depends on
            # finding *some* row dated exactly "yesterday" for this patient.
            # Skipping persistence here would make tomorrow night see no
            # prior row at all, treat the patient as a brand-new entry, and
            # incorrectly reset the ladder instead of continuing the
            # (silenced) streak. Only the LLM call is skipped: there is no
            # doctor/patient message to enrich for a night nothing fires,
            # and it would burn LLM budget for zero benefit.
            if candidate.escalation.actions and candidate.patient_id in llm_eligible_ids:
                context = indicator_cache[candidate.patient_id]
                analysis = await classify_remedy(candidate.patient_id, context, settings)
                stats["llm_calls"] += 1
            else:
                analysis = FALLBACK_REMEDY_ANALYSIS
                if not candidate.escalation.actions:
                    stats["silenced"] += 1
            analysis = enforce_patient_message_gate(analysis, candidate.escalation.actions)

            try:
                replayed = await self._persist_one(review_date, candidate, analysis, settings)
            except IntegrityError:
                # Anything that reaches here is NOT the idempotent-replay
                # case -- _persist_one already narrows that one to
                # uq_adherence_reviews_patient_date and returns True instead
                # of raising. A genuine constraint violation (e.g. a CHECK
                # constraint missing a value the code writes, see Defect 2 in
                # docs/adherence-review-fix-plan.md) must not be swallowed as
                # a silent no-op success. Phase C is per-patient by design
                # (module docstring), so one patient's write failure must not
                # abort the rest of the night's run.
                logger.exception(
                    "Adherence review write failed for patient %s on %s -- "
                    "not an idempotent replay, skipping to the next patient",
                    candidate.patient_id, review_date,
                )
                stats["failed"] += 1
                continue
            if replayed:
                stats["replayed"] += 1
            else:
                stats["reviewed"] += 1

        return stats

    async def _phase_a_and_b_read(
        self, review_date: date, settings: Settings
    ) -> tuple[
        list[SeverityIndicators],
        Dict[uuid.UUID, TrendIndicators],
        Dict[uuid.UUID, list],
        Dict[uuid.UUID, list],
        Dict[uuid.UUID, list],
        Dict[uuid.UUID, PriorReview],
        Dict[uuid.UUID, Any],
    ]:
        window_start, window_end = compute_window_bounds(
            review_date, settings.adherence_review_window_days, settings.adherence_review_timezone
        )
        prior_window_start = window_start - (window_end - window_start)

        async with self._db.begin():
            severity_rows = await self._indicators.get_severity_indicators(
                window_start, window_end, settings.missed_dose_overdue_minutes
            )
            trend_map = await self._indicators.get_trend_indicators(
                prior_window_start, window_start, settings.missed_dose_overdue_minutes
            )
            slot_map = await self._indicators.get_slot_breakdown(
                window_start, window_end, settings.missed_dose_overdue_minutes
            )
            medication_map = await self._indicators.get_medication_breakdown(
                window_start, window_end, settings.missed_dose_overdue_minutes
            )
            symptom_map = await self._indicators.get_symptom_evidence(
                window_start.date(), window_end.date()
            )
            # Escalation only ever treats a prior review as "continuing" when
            # it is exactly yesterday (resolve_action's own is_fresh check) --
            # so a one-day lookback is sufficient regardless of how far back
            # a patient's actual review history goes.
            prior_reviews = await self._indicators.get_prior_reviews(review_date - timedelta(days=1))
            patient_ids = [row.patient_id for row in severity_rows]
            roster = await self._indicators.get_patient_roster(patient_ids)

        return severity_rows, trend_map, slot_map, medication_map, symptom_map, prior_reviews, roster

    async def _phase_a_and_b(
        self, review_date: date, settings: Settings
    ) -> tuple[list[_Candidate], Dict[uuid.UUID, RemedyContext]]:
        (
            severity_rows, trend_map, slot_map, medication_map, symptom_map, prior_reviews, roster,
        ) = await self._phase_a_and_b_read(review_date, settings)

        candidates: list[_Candidate] = []
        contexts: Dict[uuid.UUID, RemedyContext] = {}
        for ind in severity_rows:
            trend_delta = compute_trend_delta(ind, trend_map.get(ind.patient_id))
            severity = compute_severity(ind, trend_delta, settings)
            if severity == Severity.NONE:
                continue

            prior = prior_reviews.get(ind.patient_id)
            escalation = resolve_action(severity, prior, review_date, settings)

            entry = roster.get(ind.patient_id)
            timezone_name = entry.timezone if entry is not None else settings.adherence_review_timezone

            candidates.append(
                _Candidate(
                    patient_id=ind.patient_id,
                    severity=severity,
                    escalation=escalation,
                    indicators=ind,
                    timezone=timezone_name,
                )
            )
            contexts[ind.patient_id] = RemedyContext(
                severity=severity,
                skipped_count=ind.skipped,
                missed_count=ind.missed,
                trend_delta=trend_delta,
                slot_breakdown=slot_map.get(ind.patient_id, []),
                medication_breakdown=medication_map.get(ind.patient_id, []),
                symptom_evidence=symptom_map.get(ind.patient_id, []),
            )
        return candidates, contexts

    async def _persist_one(
        self,
        review_date: date,
        candidate: _Candidate,
        analysis: RemedyAnalysis,
        settings: Settings,
    ) -> bool:
        """Returns True if this was an idempotent replay (row already
        existed), False if a new review was written this call."""
        idempotency_key = f"adherence-review:{candidate.patient_id}:{review_date.isoformat()}"
        window_start_date = review_date - timedelta(days=settings.adherence_review_window_days)
        window_end_date = review_date - timedelta(days=1)
        ind = candidate.indicators

        alert = None
        notification = None
        try:
            async with self._db.begin():
                # Inserted FIRST and before either side effect: a duplicate
                # run collides on uq_adherence_reviews_patient_date right
                # here, before any alert or notification is ever created for
                # the replay (plan's race-condition table, Stage 6 risk
                # register).
                review = await self._reviews.insert_review(
                    {
                        "patient_id": candidate.patient_id,
                        "review_date": review_date,
                        "window_start": window_start_date,
                        "window_end": window_end_date,
                        "severity": candidate.severity.value,
                        "days_in_severity": candidate.escalation.days_in_severity,
                        "remedy_class": analysis.remedy_class.value,
                        "action_taken": primary_action(candidate.escalation.actions).value,
                        "indicators": {
                            "total": ind.total,
                            "taken": ind.taken,
                            "skipped": ind.skipped,
                            "missed": ind.missed,
                            "critical_missed": ind.critical_missed,
                        },
                        "llm_reasoning": analysis.reasoning_doctor,
                        "llm_confidence": analysis.confidence,
                    }
                )

                if Action.DOCTOR_ALERT in candidate.escalation.actions:
                    alert = await self._alerts.create_alert(
                        patient_id=candidate.patient_id,
                        triggered_by_type="ADHERENCE_REVIEW",
                        alert_type="RED_ALERT",
                        severity="HIGH",
                        message=analysis.reasoning_doctor,
                        idempotency_key=idempotency_key,
                    )
                elif Action.DOCTOR_WARNING in candidate.escalation.actions:
                    alert = await self._alerts.create_alert(
                        patient_id=candidate.patient_id,
                        triggered_by_type="ADHERENCE_REVIEW",
                        alert_type="WARNING",
                        severity="MEDIUM",
                        message=analysis.reasoning_doctor,
                        idempotency_key=idempotency_key,
                    )

                if Action.PATIENT_NOTIFICATION in candidate.escalation.actions and analysis.message_patient:
                    scheduled_at = _next_daytime_slot(
                        datetime.now(UTC),
                        candidate.timezone,
                        settings.adherence_review_patient_send_from,
                        settings.adherence_review_patient_send_to,
                    )
                    notification = await self._notifications.create_grouped_delivery(
                        recipient_user_id=candidate.patient_id,
                        channel="APP_NOTIFICATION",
                        template_code="ADHERENCE_SUGGESTION",
                        scheduled_at=scheduled_at,
                        title="Nhắc nhở tuân thủ dùng thuốc",
                        body=analysis.message_patient,
                        scheduled_dose_ids=[],
                        idempotency_key=idempotency_key,
                    )

                if alert is not None or notification is not None:
                    await self._reviews.link_alert_and_notification(
                        review.id,
                        alert_id=alert.id if alert is not None else None,
                        notification_delivery_id=notification.id if notification is not None else None,
                    )
        except IntegrityError as err:
            # A CHECK-constraint violation is also an IntegrityError. A catch
            # this broad used to treat one as an idempotent replay too --
            # rolling the review row back and reporting success while
            # writing nothing (docs/adherence-review-fix-plan.md Defect 3).
            # Only the specific unique-key collision this method is actually
            # guarding against (a duplicate nightly run for this patient/
            # night, see the module-level race-condition note above) counts
            # as a replay; anything else must propagate so the caller's loop
            # (run_nightly_review) logs it and counts it as a real failure.
            orig = getattr(err, "orig", None)
            is_replay = (
                getattr(orig, "sqlstate", None) == "23505"
                and getattr(orig, "constraint_name", None) == "uq_adherence_reviews_patient_date"
            )
            if not is_replay:
                raise
            logger.info(
                "Adherence review already exists for patient %s on %s (idempotent replay)",
                candidate.patient_id, review_date,
            )
            return True

        # After the commit, never inside it -- same placement as every other
        # write path in this codebase (AlertService.trigger_sos,
        # AdherenceLogService.record_dose_action). publish_dashboard_event
        # is fail-open; a Redis outage costs the portal its liveness, never
        # the clinical write that already committed.
        if alert is not None:
            await publish_dashboard_event(
                "alert.opened", AlertDetailResponse.model_validate(alert).model_dump(mode="json")
            )
        if alert is not None or notification is not None:
            # A new alert changes open_alerts_count; a new notification
            # changes last_survey_date's sibling stat on the roster -- both
            # cached under the same "dash:patients" prefix.
            await invalidate_prefix("dash:patients")
        if notification is not None:
            # Imported lazily, matching NotificationDispatchService's own
            # pattern (src/modules/adherence/notification_service.py) --
            # avoids a module-load-time dependency between adherence_review
            # and agents.tasks.
            from src.modules.agents.tasks import send_notification_task

            send_notification_task.delay(str(notification.id))

        return False


class AdherenceReviewQueryService:
    """Read-only access to a patient's review history (GET
    /patients/{id}/adherence-reviews) -- kept separate from
    AdherenceReviewService so the read path doesn't need to construct the
    three write-side repositories the nightly orchestrator requires."""

    def __init__(self, db: AsyncSession, review_repository: AdherenceReviewRepository) -> None:
        self._db = db
        self._reviews = review_repository

    async def list_patient_reviews(
        self, patient_id: uuid.UUID, actor_payload: dict, page: int = 1, size: int = 10
    ) -> PageResponse[AdherenceReviewDetailResponse]:
        """PATIENT/DOCTOR/CAREGIVER, same access derivation as adherence
        logs and health surveys. Out-of-scope returns an empty page, not a
        404 -- avoids leaking which patient UUIDs exist."""
        actor_id = uuid.UUID(actor_payload["sub"])
        rows, total_count = await self._reviews.list_for_patient(patient_id, actor_id, page=page, size=size)

        total_pages = math.ceil(total_count / size) if total_count > 0 else 0
        last = page >= total_pages if total_pages > 0 else True
        content = [AdherenceReviewDetailResponse.model_validate(row) for row in rows]

        return PageResponse(
            content=content, page_no=page, page_size=size,
            total_elements=total_count, total_pages=total_pages, last=last,
        )
