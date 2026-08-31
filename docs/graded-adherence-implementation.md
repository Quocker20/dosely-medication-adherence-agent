# Graded Adherence Response — Implementation Plan

Companion to `docs/graded-adherence-response.md` (the approval proposal). That
document explains *why*; this one is the build spec. Every decision below was
made against the current code on `feat/adherence` after the `main` merge, not
from the proposal alone.

---

## 0. Decisions made during the codebase scan

| Question | Decision | Evidence |
|---|---|---|
| Which module owns this? | New vertical slice `src/modules/adherence_review/` with `models.py`, `repository.py`, `service.py`, `schemas.py`, `router.py`, `tasks.py` | It owns a new table, so `models.py` is justified per `structure.md`. `adherence/service.py` is already ~760 lines and `adherence/repository.py` ~870; adding a fourth service there buries it. It does have a genuine HTTP surface (review history + manual trigger), so `router.py` satisfies the CLAUDE.md "every module MUST have router/service/repository/schemas" rule honestly rather than by exception. |
| Does `get_llm()` support structured output? | Yes | `src/modules/planning/core/llm.py` returns `ChatOpenAI`; LangChain exposes `.with_structured_output(PydanticModel)` on it. |
| Where does `is_critical` get snapshotted? | Four hops: `PrescriptionItem` model → `PlannableItem` → `ScheduleRow` → `row_dicts` in `planning_persist_node` | `src/agents/nodes/planning_normalize_node.py:41`, `src/modules/agents/planner.py:70,88,379`, `src/agents/nodes/planning_persist_node.py:20` |
| Can the nightly job reuse the dashboard's aggregate queries? | **No.** `DashboardRepository` uses correlated scalar subqueries per row — correct at `size ≤ 100`, catastrophic across the whole patient table. The nightly job uses set-based `GROUP BY patient_id` instead. | `src/modules/dashboard/repository.py:105-129` |
| Where is the feedback signal? | `audit_logs.new_values->>'resolution_note'`, joined via `entity_type='ALERT' AND entity_id = alerts.id`. No new column needed — `adherence_reviews.alert_id` completes the path. | `src/modules/adherence/service.py:724-742` |
| Severity band boundaries | Reuse the dashboard's existing 50/70 cutoffs and add 80 as the all-clear line: `SEVERE <50`, `MODERATE 50–70`, `MILD 70–80`, `NONE ≥80` | `src/modules/dashboard/repository.py:180-195`. Keeps the number a doctor sees on the roster consistent with the tier that generated the alert. |

### Verified locally

All five Stage 1 migrations were run against the project's `remindrx_postgres`
container: `upgrade head` → schema inspected column-by-column against this
spec → `downgrade` back to `0020_merge_heads` → schema confirmed empty →
`upgrade head` again. Full round-trip, no manual intervention needed at the
final state.

**Bug found and fixed during that run:** `alembic_version.version_num` is
`VARCHAR(32)`. Three of the four revision-id strings drafted below
(`0021_prescription_item_is_critical`, `0023_alerts_adherence_review_trigger`,
`0024_scheduled_doses_window_scan_index`) exceeded that at 34–38 characters.
The failure mode is not obvious: because `CREATE INDEX CONCURRENTLY` needs
`autocommit_block()`, Alembic commits the ambient transaction on entering the
block — so a too-long id doesn't fail the migration, it fails silently
*after* the DDL has already committed, on the version-stamp UPDATE that runs
in a fresh transaction afterward. The result is schema changes applied with
no matching `alembic_version` row, which then collide with "column already
exists" on any retry. Filenames below are unchanged; only the internal
`revision = "..."` strings were shortened (this repo already has precedent
for filename ≠ revision id, e.g. `0016_seed_medication_catalog.py` →
`revision = "0016_seed_medications"`):

| File | Revision id actually used |
|---|---|
| `0021_prescription_item_is_critical.py` | `0021_dose_is_critical` |
| `0023_alerts_adherence_review_trigger.py` | `0023_alerts_review_trigger` |
| `0024_scheduled_doses_window_scan_index.py` | `0024_dose_window_scan_idx` |

**Any future migration in this feature must keep its revision id ≤ 32
characters** — check with `len()` before naming it, not after running it.

### Blocker found: the migration tree has two heads

```
0015_agent_run_claim ─┬─ 0016_merge_heads ─ 0017 ─ 0018 ─ 0019_user_need_onboarding   ← head
                      └─ 0016_seed_medications                                         ← head
```

`alembic upgrade head` fails with *"Multiple head revisions are present"* until
these are merged. This is pre-existing on `main`, not caused by this feature,
but it blocks every migration below. **Stage 1 starts by fixing it.**

---

## Stage 1 — Database

All schema work lands first, in one reviewable batch, so later stages never
block on a migration.

### 1.1 · `0020_merge_heads` — unblock the tree

```python
revision = "0020_merge_heads"
down_revision = ("0019_user_need_onboarding", "0016_seed_medications")
```

Empty `upgrade()`/`downgrade()`. Verify with `alembic heads` → exactly one.

> **Superseded on 29/08/2026.** The chatbot work landed `0020_chat_memory`
> independently, merging the same two parents, so once both branches reached
> `main` the tree had two heads again (`0020_chat_memory` and
> `0024_dose_window_scan_idx`). `0025_merge_chat_adherence` rejoins them —
> that, not `0020_merge_heads`, is what makes `alembic heads` return one today.
> Two teams merging the same pair in parallel is the failure mode to watch for:
> check `alembic heads` right after every rebase onto `main`, not just after
> writing a migration.

### 1.2 · `0021_prescription_item_is_critical`

```sql
ALTER TABLE prescription_items
    ADD COLUMN is_critical BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE scheduled_doses
    ADD COLUMN is_critical BOOLEAN NOT NULL DEFAULT FALSE;
```

- `NOT NULL DEFAULT FALSE` is safe on PG 11+ — the default is stored in the
  catalog, so this is a metadata-only change with no table rewrite and no long
  `ACCESS EXCLUSIVE` hold.
- Existing rows read `false`. That is the intended semantic: the fast path
  covers nobody until doctors start flagging, as stated in the proposal.
- `scheduled_doses.is_critical` is an **immutable generation-time snapshot**,
  matching the `dose_slot`/`medication_id`/`dose_value` precedent from
  migration 0011. It cannot drift: items are only editable while the
  prescription is `DRAFT`, and doses are generated on approve.

**Partial index for the narrowed fast path:**

```sql
CREATE INDEX CONCURRENTLY idx_scheduled_doses_critical_patient_time
    ON scheduled_doses (patient_id, current_scheduled_at DESC)
    WHERE is_critical;
```

Partial, so it indexes only flagged doses — small on day one, and it stays
proportional to real usage rather than table size. Use
`op.get_context().autocommit_block()` for `CONCURRENTLY` (same pattern as
migration 0008).

### 1.3 · `0022_adherence_reviews`

```sql
CREATE TABLE adherence_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patient_profiles(user_id) ON DELETE CASCADE,
    review_date DATE NOT NULL,
    window_start DATE NOT NULL,
    window_end DATE NOT NULL,

    severity VARCHAR(20) NOT NULL
        CONSTRAINT ck_adherence_reviews_severity
        CHECK (severity IN ('MILD','MODERATE','SEVERE')),
    days_in_severity INTEGER NOT NULL DEFAULT 1
        CONSTRAINT ck_adherence_reviews_days CHECK (days_in_severity >= 1),

    remedy_class VARCHAR(40)
        CONSTRAINT ck_adherence_reviews_remedy
        CHECK (remedy_class IS NULL OR remedy_class IN (
            'RESCHEDULE_TIMING','SUSPECTED_SIDE_EFFECT','DELIBERATE_REFUSAL',
            'DISENGAGEMENT','EXTERNAL_DISRUPTION','UNCLEAR')),

    action_taken VARCHAR(30) NOT NULL
        CONSTRAINT ck_adherence_reviews_action
        CHECK (action_taken IN ('NONE','PATIENT_NOTIFICATION','DOCTOR_WARNING','DOCTOR_ALERT')),

    -- The numbers that produced `severity`, frozen for audit. An alert must be
    -- reconstructable after the fact even if the dose rows later change.
    indicators JSONB NOT NULL DEFAULT '{}'::jsonb,

    llm_reasoning TEXT,
    llm_confidence VARCHAR(10)
        CONSTRAINT ck_adherence_reviews_confidence
        CHECK (llm_confidence IS NULL OR llm_confidence IN ('high','medium','low')),
    model_version VARCHAR(100),
    prompt_version VARCHAR(50),

    alert_id UUID REFERENCES alerts(id) ON DELETE SET NULL,
    notification_delivery_id UUID REFERENCES notification_deliveries(id) ON DELETE SET NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Idempotency AND the concurrency guarantee: a second run on the same night
-- collides instead of double-alerting. See §7.2.
CREATE UNIQUE INDEX CONCURRENTLY uq_adherence_reviews_patient_date
    ON adherence_reviews (patient_id, review_date);

-- Escalation lookup: "the most recent review for each of these patients".
CREATE INDEX CONCURRENTLY idx_adherence_reviews_patient_date_desc
    ON adherence_reviews (patient_id, review_date DESC);
```

**Only non-`NONE` reviews are persisted.** Storing a row per patient per night
would add ~365 rows/patient/year of almost entirely `NONE`. The `CHECK`
constraint enforces this at the DB layer so a coding mistake cannot quietly
start writing them.

Consequence, and the mitigation: a *skipped* nightly run leaves a gap that
looks identical to recovery. `days_in_severity` is therefore carried forward
from the previous row's stored counter, not recomputed by counting rows — and
if the previous row is more than one day old, the counter resets to 1. A missed
run costs one escalation reset, which delays escalation rather than
accelerating it. Failing in the conservative direction is the right trade.

### 1.4 · `0023_alerts_adherence_review_trigger`

```sql
ALTER TABLE alerts DROP CONSTRAINT ck_alerts_triggered_by_type;
ALTER TABLE alerts ADD CONSTRAINT ck_alerts_triggered_by_type
    CHECK (triggered_by_type IN
        ('SOS_BUTTON','SEVERE_SYMPTOM','MISSED_DOSES','ADHERENCE_REVIEW'))
    NOT VALID;
ALTER TABLE alerts VALIDATE CONSTRAINT ck_alerts_triggered_by_type;
```

`NOT VALID` then `VALIDATE` — the two-step pattern already used in migrations
0008/0009 — takes only `SHARE UPDATE EXCLUSIVE` during validation instead of
blocking writes to a table on the safety path.

`MISSED_DOSES` is **kept** in the constraint. Historical rows carry it, and the
narrowed critical-only fast path still writes it.

### 1.5 · `0024_scheduled_doses_window_scan_index`

```sql
CREATE INDEX CONCURRENTLY idx_scheduled_doses_window_scan
    ON scheduled_doses (current_scheduled_at, patient_id, status)
    INCLUDE (dose_slot, medication_id, is_critical, snooze_count,
             original_scheduled_at, taken_at);
```

The nightly aggregates filter on a time range across *all* patients and group
by `patient_id`. The existing `idx_scheduled_doses_patient_time` leads with
`patient_id`, so it cannot serve a patient-agnostic range scan — without this
index every nightly query is a sequential scan of the whole table, and
`scheduled_doses` grows without bound as history accumulates.

The `INCLUDE` columns make Stage 3's queries index-only, avoiding a heap fetch
per row.

**Honest note:** at current data volumes a seq scan once a night would be
tolerable. This index is for the second year, not the first week. It is cheap
to add now and awkward to add under load later.

### 1.6 · Update `docs/database_v1_init.sql`

The init script is the canonical schema reference and is kept in sync by hand.
Add: both `is_critical` columns, the whole `adherence_reviews` table, the
amended `ck_alerts_triggered_by_type`, and all three new indexes — each with
the same style of comment the existing entries carry (what query it serves,
which migration added it).

---

## Stage 2 — `is_critical` threading and the narrowed scanner

### 2.1 · Thread the flag through the planner (4 files, in order)

1. `src/modules/prescriptions/models.py` — `PrescriptionItem.is_critical: Mapped[bool]`
2. `src/modules/agents/models.py` — `ScheduledDose.is_critical: Mapped[bool]`
3. `src/modules/agents/planner.py` — add `is_critical: bool` to both
   `PlannableItem` (line ~70) and `ScheduleRow` (line ~88); pass it through in
   `expand_schedule` (line ~379). It is a pure carried value: it must **not**
   participate in slot selection, gap validation, or any scheduling decision.
4. `src/agents/nodes/planning_normalize_node.py:41` — populate it on `PlannableItem`
5. `src/agents/nodes/planning_persist_node.py:20` — add to `row_dicts`

Also `src/modules/agents/grouping.py` — `_assert_schedule_unchanged` compares
`ScheduleRow`s; confirm the new field does not break that equality check or
leak into `candidate_view_for_llm` (the grouping LLM has no business seeing
criticality).

### 2.2 · API surface

- `CreatePrescriptionItemRequest` / `UpdatePrescriptionItemRequest`:
  `is_critical: bool = False`
- `PrescriptionItemDetailResponse`: `is_critical: bool`
- Update `docs/api-contract.md` §Slice 5 and `docs/schema.md` §5.6/5.7.

Doctor-set only, and items are DRAFT-locked — no new authorization logic.

### 2.3 · Narrow the missed-dose scanner

In `src/modules/agents/service.py`:

- **Keep** `mark_overdue_pending_as_missed` (line 512) at its 15-minute
  cadence, untouched. Without it doses sit `PENDING` forever, and
  `apply_dose_action_cas` — which only guards `status='PENDING' AND
  current_scheduled_at <= now() + 20 minutes` (the 20-minute
  `_EARLY_ACTION_GRACE_MINUTES` window absorbs client clock drift and the
  patient app's own early-unlock UI, not old doses) — would let a patient
  mark a three-week-old dose as `TAKEN`. That is silent retroactive-adherence
  corruption, not a cosmetic issue.
- **Narrow** the streak block (lines 516–552) to critical doses only.

Add to `ScheduledDoseRepository`:

```python
async def get_recent_critical_dose_statuses(
    self, patient_ids: list[uuid.UUID], lookback: int, before: datetime
) -> dict[uuid.UUID, list[dict[str, str]]]:
```

Same `ROW_NUMBER() OVER (PARTITION BY patient_id ...)` shape as the existing
`get_recent_dose_statuses` (line 459) — one query for all patients, never one
per patient — plus `WHERE is_critical`. Rides
`idx_scheduled_doses_critical_patient_time`.

> **Semantic change, deliberate.** `count_missed_dose_streak`
> (`src/agents/tools/safety_tools.py:129`) walks backwards and breaks on the
> first non-missed dose. Today a patient who takes their statin but skips
> warfarin has streak 0 — the taken statin interrupts the run. Filtered to
> critical doses, the same patient shows streak 3 after three days. The
> filtered path is **more sensitive, not less**. This is the intent, but it
> must be an explicit test, not a discovery in production.

Also: for a once-daily critical drug, "3 consecutive missed" spans three days.
The alert message must not imply same-day urgency — include the elapsed span.

---

## Stage 3 — Indicator queries (`adherence_review/repository.py`)

**The central performance rule for this stage: every query returns numbers for
the entire population in one round trip.** Five queries total for the nightly
run, regardless of patient count. Never a query inside a per-patient loop.

All five run inside **one `REPEATABLE READ` transaction** so the packages
describe a single consistent instant. Under the default `READ COMMITTED` each
statement takes its own snapshot, and a patient actioning a dose mid-run could
make the slot breakdown disagree with the totals it is supposed to decompose.

### 3.1 · Window definition

A single UTC window derived from the deployment-local calendar day:
`[D-7 00:00, D 00:00)` in `Asia/Ho_Chi_Minh` (the Celery timezone, and the
`patient_profiles.timezone` default), converted to UTC once.

**Accepted limitation:** patients in other timezones get a window skewed by
their UTC offset. The alternative — per-patient local boundaries — forces
per-patient queries, which is exactly the N+1 this stage exists to avoid.
Document it in the repository docstring; revisit only if the platform ships
outside one timezone.

### 3.2 · Query 1 — severity package (one row per patient)

```sql
SELECT patient_id,
       count(*)                                        AS total,
       count(*) FILTER (WHERE status = 'TAKEN')        AS taken,
       count(*) FILTER (WHERE status = 'SKIPPED')      AS skipped,
       count(*) FILTER (WHERE status IN ('MISSED','PENDING')) AS missed,
       count(*) FILTER (WHERE is_critical AND status IN ('MISSED','PENDING')) AS critical_missed
FROM scheduled_doses
WHERE current_scheduled_at >= :start AND current_scheduled_at < :end
  AND (status <> 'PENDING' OR current_scheduled_at <= now() - :overdue)
GROUP BY patient_id
```

The `is_due` predicate is the same rule as
`AdherenceLogRepository.get_dose_status_counts` and
`DashboardRepository._is_due_filter` — a dose still `PENDING` inside its grace
window has had no chance to be actioned, so it belongs in neither numerator nor
denominator. Overdue-but-`PENDING` counts as missed so the four figures sum to
`total` and the result cannot race the 15-minute scan.

### 3.3 · Query 2 — trend (prior window, same shape)

Same query over `[D-14, D-7)`, returning `total` and `taken` only. Compute
`trend_delta` in Python. One extra query, not one per patient.

### 3.4 · Query 3 — per-slot breakdown

```sql
SELECT patient_id, dose_slot,
       count(*) AS total,
       count(*) FILTER (WHERE status IN ('MISSED','PENDING')) AS missed
FROM scheduled_doses
WHERE ... same window + is_due ...
GROUP BY patient_id, dose_slot
```

Returns ≤ 4 rows per patient. Fold into a dict in Python.

### 3.5 · Query 4 — per-medication breakdown

Same shape, `GROUP BY patient_id, medication_id`, joined to the frozen
`display_name`. **Read the name from `scheduled_doses`' own snapshot columns,
not by joining `medications`** — `prescription_items.medication_id` carries no
FK (dropped in migration 0007) and the catalog row may have been edited or
deleted since. Take `display_name` via `prescription_items` on the dose's
`prescription_item_id`, which is a real FK.

Cap at the top 5 medications per patient by miss count when building the LLM
payload — a patient on 15 drugs should not produce a 15-row prompt.

### 3.6 · Query 5 — symptom evidence

```sql
SELECT hs.patient_id, hs.survey_date, sr.symptom_code, sr.severity
FROM health_surveys hs
JOIN symptom_reports sr ON sr.survey_id = hs.id
WHERE hs.survey_date >= :window_start AND hs.survey_date <= :window_end
```

Rides the existing `idx_health_surveys_date_id` — no new index needed. Uses
`selectinload`-free explicit join because `HealthSurvey.symptom_reports` is
`lazy="raise"`.

Only `symptom_code` and `severity` are selected. `answers_json` and
`symptom_reports.description` are patient-authored free text and are
**excluded from the LLM payload entirely** for v1, until the `answers_json`
key shape is specified (open item in the proposal). Codes and severities are a
closed vocabulary and carry no injection surface.

### 3.7 · Query 6 — prior reviews for escalation

```sql
SELECT DISTINCT ON (patient_id) patient_id, review_date, severity, days_in_severity
FROM adherence_reviews
WHERE review_date >= :cutoff
ORDER BY patient_id, review_date DESC
```

One query for every patient's latest review. Rides
`idx_adherence_reviews_patient_date_desc`.

### 3.8 · Patient roster

One query joining `patient_profiles` + `users` for name/timezone/status of the
patients that appear in Query 1. Not per-patient.

---

## Stage 4 — Rules and escalation (`adherence_review/service.py`)

Pure functions, no DB, no IO — directly unit-testable like
`src/modules/agents/planner.py`.

### 4.1 · Severity

```python
def compute_severity(ind: SeverityIndicators, cfg: Settings) -> Severity:
    if ind.total < cfg.adherence_review_min_doses:      # too little data to judge
        return Severity.NONE
    rate = ind.taken / ind.total * 100
    if rate < cfg.adherence_severe_threshold:    return Severity.SEVERE     # <50
    if rate < cfg.adherence_moderate_threshold:  return Severity.MODERATE   # 50–70
    if rate < cfg.adherence_mild_threshold:      return Severity.MILD       # 70–80
    return Severity.NONE
```

Then two escalating adjustments, applied after the band:

- `critical_missed > 0` → raise one level (capped at `SEVERE`). The same flag
  that drives the fast path also weights the nightly severity, as decided.
- `trend_delta <= cfg.adherence_trend_alarm_delta` → raise one level.

The min-dose floor comes first and is absolute. It is the same reasoning as the
zero-dose band fix already on this branch: a patient with four doses in the
window has no meaningful rate, and guessing at one produces a false alert.

### 4.2 · Escalation

```python
def resolve_action(severity, prior, review_date, cfg) -> tuple[int, Action]:
```

- No prior row, or prior `review_date` is not exactly `review_date - 1 day`
  → `days_in_severity = 1` (fresh entry; see §1.3 on skipped runs)
- Prior severity **lower** than today → act at the new level, reset counter to 1
- Prior severity **equal** → `days_in_severity = prior + 1`; escalate at the
  configured step boundaries
- Prior severity **higher** → improving; `days_in_severity = 1`, and suppress
  the alert. Silence is the correct response to recovery.

Action ladder (step days from config, defaults 1/3/5):

| Severity | day 1 | day 3 | day 5+ |
|---|---|---|---|
| MILD | `PATIENT_NOTIFICATION` | `PATIENT_NOTIFICATION` | `DOCTOR_WARNING` |
| MODERATE | `PATIENT_NOTIFICATION` + `DOCTOR_WARNING` | `DOCTOR_WARNING` | `DOCTOR_WARNING` |
| SEVERE | `DOCTOR_ALERT` | `DOCTOR_ALERT` | `DOCTOR_ALERT` |

### 4.3 · Cooldown

Suppress a repeat *doctor-facing* action within
`adherence_review_cooldown_days` unless severity increased. Patient
notifications have their own, shorter cooldown. Both read from Query 6's
result — no extra lookup.

---

## Stage 5 — LLM step (`adherence_review/llm.py`)

### 5.1 · Contract

```python
class RemedyClass(str, Enum):
    RESCHEDULE_TIMING = "RESCHEDULE_TIMING"
    SUSPECTED_SIDE_EFFECT = "SUSPECTED_SIDE_EFFECT"
    DELIBERATE_REFUSAL = "DELIBERATE_REFUSAL"
    DISENGAGEMENT = "DISENGAGEMENT"
    EXTERNAL_DISRUPTION = "EXTERNAL_DISRUPTION"
    UNCLEAR = "UNCLEAR"

class RemedyAnalysis(BaseModel):
    remedy_class: RemedyClass
    confidence: Literal["high", "medium", "low"]
    reasoning_doctor: str = Field(max_length=600)
    message_patient: str | None = Field(default=None, max_length=240)
```

Called via `get_llm().with_structured_output(RemedyAnalysis)`. The enum makes
an invalid class a validation error, not a routing bug.

**Severity is not in the output schema.** It is passed *in* as context and
there is structurally no field for the model to change it through.

### 5.2 · Guardrails

- **Never called inside a DB transaction.** Read phase commits and closes,
  then the LLM runs, then a fresh transaction writes. An LLM call takes
  seconds; holding a connection across it would exhaust the pool.
- **Per-call timeout** (`adherence_review_llm_timeout_seconds`). On timeout or
  any exception: fall back to `remedy_class=UNCLEAR`, `reasoning_doctor=None`,
  and **still take the rule-decided action**. The severity was never the
  model's to decide, so a model outage must degrade the explanation, never
  suppress a clinically-warranted alert. Log and count these.
- **Patient-facing text is dropped unless `action == PATIENT_NOTIFICATION`.**
  Enforced at the routing layer, not by prompt instruction.
- **Prompt states: cite only the supplied indicators, introduce no new clinical
  claims, never mention dosage.** Backed by the max-length caps above and by a
  reject-list check on `message_patient` reusing
  `src/agents/medication_policy.py`, which already exists for this exact class
  of leak in chat.
- De-identified: `patient_id` and clinical numbers only. No name, phone, or DOB
  in the prompt — same rule as `AgentState`'s docstring.

### 5.3 · Not a LangGraph graph

One structured call with no conditional edges. `AgentState` is chat-shaped
(`messages`, `intent`, `escalated`, and now `patient_address`/`client_date`) and
does not fit. Revisit only if branching appears.

---

## Stage 6 — Nightly job and delivery

### 6.1 · Task

`src/modules/adherence_review/tasks.py`, following the exact engine/session
pattern of `_execute_missed_dose_scan` (`src/modules/agents/tasks.py:115`) —
`create_async_engine(..., poolclass=NullPool)` and an explicit `dispose()`.

```python
beat_schedule["scan-adherence-review"] = {
    "task": "adherence_review.scan",
    "schedule": crontab(hour=settings.adherence_review_run_hour, minute=0),
}
```

`crontab`, not `timedelta` — the run must land at a fixed local hour. Celery is
already configured `timezone="Asia/Ho_Chi_Minh"`.

Default `adherence_review_run_hour = 5`. Compute at 05:00 so the previous day
is closed and doctor alerts are waiting at shift start; midnight has no
advantage and lands alerts in an empty portal.

### 6.2 · Phased execution

```
Phase A (one REPEATABLE READ txn)  →  6 aggregate queries, commit, close
Phase B (no txn)                   →  rules + escalation (pure), then
                                      LLM calls for the gated set
Phase C (one txn per patient)      →  INSERT review + alert/notification
```

Phase C is per-patient rather than one big transaction so that a single
patient's failure — an idempotency collision, a constraint violation — cannot
roll back the whole night's work.

### 6.3 · Actions

| Action | Write |
|---|---|
| `PATIENT_NOTIFICATION` | `NotificationDelivery(template_code='ADHERENCE_SUGGESTION', scheduled_at=<next daytime slot>)`, then enqueue `send_notification_task` |
| `DOCTOR_WARNING` | `Alert(alert_type='WARNING', severity='MEDIUM', triggered_by_type='ADHERENCE_REVIEW')` |
| `DOCTOR_ALERT` | `Alert(alert_type='RED_ALERT', severity='HIGH', triggered_by_type='ADHERENCE_REVIEW')` |

Idempotency key on both: `adherence-review:{patient_id}:{review_date}`.
Both tables have a `UNIQUE` on `idempotency_key`, so a duplicate run raises
`IntegrityError` and is caught as a replay — the same pattern
`MissedDoseScanService` and `AlertService.trigger_sos` already use.

**Daytime gating:** patient deliveries set `scheduled_at` to the next slot
inside `[adherence_review_patient_send_from, ..._to]` (default 08:00–20:00
local). The existing `scan-due-doses` dispatcher already respects
`scheduled_at`, so no new delivery machinery is needed. Doctor alerts are not
gated — a warning sitting in the portal at 05:00 costs nothing.

### 6.4 · Post-commit side effects

Exactly as the existing write paths do it — **after** the transaction commits,
never inside:

```python
await publish_dashboard_event("alert.opened", response.model_dump(mode="json"))
await invalidate_prefix("dash:patients")
```

> **Required, not optional:** `DashboardEventService.stream_for_dashboard_actor`
> (added by `5d40e61` on main) re-authorizes every frame against the
> doctor↔patient relationship and **discards any frame whose `data` has no
> `patient_id`**. `AlertDetailResponse` carries `patient_id` at the top level,
> so alert frames pass — but any *new* event type this feature emits must
> include it or it will be silently dropped for every connected doctor.

### 6.5 · Cap and kill switch

- `adherence_review_enabled: bool = True` — a one-flag stop.
- `adherence_review_max_llm_calls: int = 300` — sort the gated set by severity
  descending before truncating, so the cap drops the least severe. **Log the
  number dropped**; a non-zero count is the signal that thresholds are too
  loose and must be visible, not silently swallowed.

### 6.6 · Router

`GET /patients/{patient_id}/adherence-reviews` — PATIENT/DOCTOR/CAREGIVER,
reusing the adherence access rule (`_access_filter`); out-of-scope returns an
empty page, matching `list_patient_surveys`.

`POST /admin/adherence-reviews/run` — ADMIN only, triggers the task
out-of-band. Needed to test the pipeline without waiting for 05:00.

---

## Stage 7 — Dashboard ordering

`DashboardRepository.list_dashboard_patients` currently sorts by
`open_alerts.desc()` (line 218) with no severity weighting. Introducing a
`WARNING` tier would let warning volume push genuinely-red patients off page 1.

Replace the single count with two correlated subqueries — `critical_alerts`
(`severity IN ('CRITICAL','HIGH')`) and `warning_alerts` (`severity='MEDIUM'`),
both still `status IN ('OPEN','ACKNOWLEDGED')` — and order
`critical DESC, warning DESC, created_at DESC`.

`DashboardPatientListResponse.open_alerts_count` keeps its current meaning
(the sum) so existing clients are unaffected; the split is for ordering only.
Add the two counts as new optional fields if the portal wants to render them.

---

## Cross-cutting risk register

### N+1 — avoided by construction

| Temptation | What we do instead |
|---|---|
| Per-patient indicator queries | 6 set-based queries for the whole population (§3) |
| Per-patient prior-review lookup | One `DISTINCT ON` query (§3.7) |
| Per-patient name/timezone fetch | One roster join (§3.8) |
| Reusing `DashboardRepository`'s correlated subqueries | Explicitly rejected — correct at `size ≤ 100`, quadratic across the table |
| Per-dose medication catalog lookup | Snapshot columns + one `prescription_items` join (§3.5) |

One LLM call per gated patient is inherent and bounded by §6.5's cap.

### Full-scan avoidance

| Query | Index |
|---|---|
| Nightly window aggregates | `idx_scheduled_doses_window_scan` (new, §1.5) — index-only via `INCLUDE` |
| Critical streak check | `idx_scheduled_doses_critical_patient_time` (new, partial, §1.2) |
| Symptom evidence | `idx_health_surveys_date_id` (existing) |
| Prior reviews | `idx_adherence_reviews_patient_date_desc` (new, §1.3) |
| Overdue flip (unchanged) | `idx_scheduled_doses_pending_due` (existing, partial) |

Verify each with `EXPLAIN (ANALYZE, BUFFERS)` against a seeded dataset before
merging Stage 3 — an index that the planner declines to use is not an index.

### Race conditions

| Race | Mitigation |
|---|---|
| Two nightly runs overlap (slow run + Beat retry, or a manual trigger) | `uq_adherence_reviews_patient_date` makes the per-patient write collide. Insert the review row **first** in Phase C, so a duplicate run aborts that patient before writing an alert. This is the real guarantee; a `pg_try_advisory_lock` on the job is a cheap addition but not the safety net. |
| Duplicate alert / notification | `UNIQUE` on `idempotency_key` on both tables, `IntegrityError` caught as replay — existing pattern |
| Patient actions a dose mid-run | Single `REPEATABLE READ` snapshot for all six read queries (§3), so the packages cannot disagree with each other |
| Streak scan races the overdue flip | Unchanged from today: overdue-`PENDING` is counted as missed, so either snapshot yields the same bucket |
| WS frame published before commit | Publish strictly after the transaction closes (§6.4), matching every existing write path |
| `is_critical` snapshot drifting from the item | Impossible: items are DRAFT-locked, doses generate on approve |
| LLM call holding a DB connection | Structurally prevented by the Phase A/B/C split (§6.2) |

### Other

- **Cache staleness** — new alerts change `open_alerts_count`; `invalidate_prefix("dash:patients")` after each commit.
- **Table growth** — `adherence_reviews` stores non-`NONE` rows only, but still accumulates. A retention job (>1 year) is a follow-up, not v1.
- **Migration lock duration** — `NOT NULL DEFAULT FALSE` is metadata-only on PG 11+; all three indexes use `CONCURRENTLY` in an `autocommit_block`; the `CHECK` uses `NOT VALID` + `VALIDATE`.
- **Prompt injection** — free-text survey fields are excluded from the payload for v1 (§3.6). Even if reintroduced, severity is already fixed before the model runs, so the worst case is a wrong remedy class, never a wrong urgency.

---

## Test plan

New files, following the existing structure:

- `tests/test_services/test_adherence_severity.py` — pure `compute_severity`
  table: band boundaries, min-dose floor, the critical-miss bump, the trend
  bump, and that a bump cannot exceed `SEVERE`
- `tests/test_services/test_adherence_escalation.py` — the ladder: fresh entry,
  same-severity increment, rise resets, fall suppresses, **and the skipped-run
  gap resetting to 1 rather than escalating**
- `tests/test_services/test_adherence_review_indicators.py` — the six queries
  against seeded data; asserts one query per package and that the four status
  counts sum to `total`
- `tests/test_services/test_critical_streak.py` — the semantic change from
  §2.3: interleaved non-critical `TAKEN` doses no longer break a critical
  streak, and a non-critical streak raises nothing
- `tests/test_services/test_adherence_review_llm.py` — `RemedyAnalysis`
  validation; an out-of-enum class is rejected; timeout falls back to
  `UNCLEAR` **and still takes the rule action**; `message_patient` is dropped
  when the action is not patient-facing
- `tests/test_api/test_adherence_reviews.py` — router access scoping (self /
  doctor-prescribed / active caregiver / out-of-scope empty page)
- Extend `tests/test_api/test_dashboard.py` — severity-weighted ordering: a
  patient with one `RED_ALERT` sorts above a patient with five `WARNING`s

`MissedDoseScanService` currently has no covering tests, so §2.3's narrowing
establishes the pattern rather than following one. Budget for that.

---

## Configuration keys

```python
# Feature gate
adherence_review_enabled: bool = True
adherence_review_run_hour: int = Field(default=5, ge=0, le=23)

# Window and eligibility
adherence_review_window_days: int = Field(default=7, ge=1, le=90)
adherence_review_min_doses: int = Field(default=5, ge=1, le=100)

# Severity bands — aligned with the dashboard's existing 50/70 cutoffs
adherence_severe_threshold: float = Field(default=50.0, ge=0, le=100)
adherence_moderate_threshold: float = Field(default=70.0, ge=0, le=100)
adherence_mild_threshold: float = Field(default=80.0, ge=0, le=100)
adherence_trend_alarm_delta: float = Field(default=-20.0, ge=-100, le=0)

# Escalation ladder
adherence_review_escalation_days: str = "1,3,5"
adherence_review_cooldown_days: int = Field(default=3, ge=0, le=30)

# LLM
adherence_review_max_llm_calls: int = Field(default=300, ge=0, le=10000)
adherence_review_llm_timeout_seconds: int = Field(default=20, ge=1, le=120)
adherence_review_prompt_version: str = "v1"

# Patient delivery window (local)
adherence_review_patient_send_from: int = Field(default=8, ge=0, le=23)
adherence_review_patient_send_to: int = Field(default=20, ge=0, le=23)
```

---

## Sequencing

| Stage | Depends on | Ships independently? |
|---|---|---|
| 1 · Database | — | Yes (schema only, no behaviour change) |
| 2 · `is_critical` + scanner | 1 | Yes — narrowed fast path is a complete improvement on its own |
| 3 · Indicators | 1 | Yes (queries only, no caller) |
| 4 · Rules + escalation | 3 | **Yes — this is the first user-visible value, with no AI involved** |
| 5 · LLM | 4 | Yes — adds explanations to alerts that already work |
| 6 · Job + delivery | 4 (5 optional) | Yes |
| 7 · Dashboard ordering | 1 | Yes, and should land **before** 6 so the first `WARNING` never buries a `RED_ALERT` |

Stages 1–4 plus 7 deliver a working graded-alert system with generic message
text and no model in the loop. Stage 5 is additive. If approval comes back
with "no LLM," nothing built before it is wasted.
