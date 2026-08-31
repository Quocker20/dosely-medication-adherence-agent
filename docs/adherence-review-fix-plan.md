# Adherence Review — Fix Plan

Status: the nightly graded-adherence review has **never completed a single run in
production**. Celery Beat dispatched `adherence_review.scan` correctly on both
nights since the feature shipped; the worker crashed before its first database
query each time. Zero `adherence_reviews` rows, zero alerts, zero patient
notifications.

This document is the step-by-step remediation plan. It covers one confirmed
defect, one latent defect that will kill the job the moment the first one is
fixed, and three secondary defects found while scanning the migration graph and
the Celery import boundary.

**Progress:** all five defects have a code fix in the working tree, on branch
`fix/adherence-review`, uncommitted. Every fix that can be checked without a
reachable database has been checked — against the real repository files, not
synthetic stand-ins — and passes; one new integration test needs a live
database to run and has not been executed yet. Nothing has been deployed.
Deploy (Step 8 onward) is being done manually, separately from this pass.

---

## 1. Evidence

Beat dispatched the task on schedule (`22:00 UTC` = `05:00 +07`, matching
`adherence_review_run_hour=5`):

```
[2026-08-29 22:00:00,000: INFO/MainProcess] Scheduler: Sending due task scan-adherence-review (adherence_review.scan)
[2026-08-30 22:00:00,000: INFO/MainProcess] Scheduler: Sending due task scan-adherence-review (adherence_review.scan)
```

The worker received both and raised the same error both times:

```
Task adherence_review.scan[...] raised unexpected: NoReferencedTableError(
  "Foreign key associated with column 'alerts.assigned_doctor_id' could not find
   table 'doctor_profiles' with which to generate a foreign key to target column
   'user_id'")
  File "/app/src/modules/adherence_review/tasks.py", line 48, in _execute_adherence_review_scan
```

Line 48 is `stats = await service.run_nightly_review(review_date)` — the failure
happens on the first ORM use, before Phase A reads anything.

Ruled out by this evidence:

- Not a Beat scheduling problem — the task was dispatched twice.
- Not a stale image — containers were created `2026-08-29 17:47:44 UTC`, after
  the Stage 6 merge landed on `main`.
- Not a configuration kill switch — `printenv | grep ADHERENCE_REVIEW` in the
  worker returns nothing, so every setting is at its default
  (`adherence_review_enabled=True`, `run_hour=5`, `window_days=7`,
  `min_doses=5`, bands 50/70/80).
- Not a threshold or data-volume problem — the job never reached the code that
  evaluates thresholds.

---

## 2. Defects

### Defect 1 — ORM registry incomplete in the Celery process (P0, confirmed)

`Alert.assigned_doctor_id` declares `ForeignKey("doctor_profiles.user_id")`
(`src/modules/adherence/models.py:172`). `DoctorProfile` — the class that
registers the `doctor_profiles` table on `Base.metadata` — lives in
`src/modules/admin/models.py`.

A mapped class only registers itself when its module is imported, and SQLAlchemy
resolves every `ForeignKey` target at `configure_mappers()` time across the
**whole** registry, not just the classes the caller touches. A static
import-closure walk over `src/` confirms `admin.models` is unreachable from the
task entrypoint:

```
src/modules/adherence_review/tasks.py   admin.models reached: False
src/modules/agents/tasks.py             admin.models reached: False
```

`src/main.py` never hits this because it imports every router, and through them
every model. A Celery worker process imports only what its own task modules
name. This is exactly the failure mode `alembic/env.py:12-18` already documents
and guards against; `tasks.py` was written without the same guard.

**Fix.** Add the model-registry import block to
`src/modules/adherence_review/tasks.py`, immediately after the `src.core`
imports and before the repository imports, with a comment explaining why the
apparently-unused imports must stay:

```python
from src.modules.adherence import models as _adherence_models  # noqa: F401
from src.modules.adherence_review import models as _adherence_review_models  # noqa: F401
from src.modules.admin import models as _admin_models  # noqa: F401
from src.modules.agents import models as _agents_models  # noqa: F401
from src.modules.auth import models as _auth_models  # noqa: F401
from src.modules.patients import models as _patients_models  # noqa: F401
from src.modules.prescriptions import models as _prescriptions_models  # noqa: F401
```

No migration, no schema change. See Step 6 for the shared-registry refactor that
removes the duplication this creates.

---

### Defect 2 — `ck_alerts_triggered_by_type` rewritten by two parallel branches (P0, confirmed, fixed)

**Confirmed against production** via the Step 0 query below: `ADHERENCE_REVIEW`
is missing. `0021` won the traversal race, `0023` lost. Fixed by
`alembic/versions/0028_alerts_adherence_review_check_fix.py`, which writes the
union of both branches' value sets and downgrades back to exactly the set
found in production (not an earlier revision's set).

Two migrations on **sibling branches** both drop and recreate the same CHECK
constraint with **mutually exclusive** value sets:

| Revision | Branch | Value set written |
| --- | --- | --- |
| `0021_suspected_adverse_events` (line 19) | adverse events | `SOS_BUTTON, SEVERE_SYMPTOM, MISSED_DOSES, ADVERSE_EVENT` |
| `0023_alerts_review_trigger` (line 38) | adherence review | `SOS_BUTTON, SEVERE_SYMPTOM, MISSED_DOSES, ADHERENCE_REVIEW` |

Neither set contains the other's new value. The branches only meet at
`0026_seed_curated_products`, whose `down_revision` is
`('0021_suspected_adverse_events', '0025_merge_chat_adherence')`. Whichever
branch Alembic walks last wins, and nothing in either revision expresses a
dependency on the other — the surviving constraint is an accident of traversal
order, not a decision.

Whichever way it landed, one production write path is broken:

- If `ADHERENCE_REVIEW` is missing, the nightly review's `DOCTOR_WARNING` and
  `DOCTOR_ALERT` writes violate the constraint
  (`src/modules/adherence_review/service.py:467`, `_persist_one`).
- If `ADVERSE_EVENT` is missing, the adverse-event path breaks instead
  (`src/modules/adherence/adverse_events.py:126`,
  `src/modules/agents/tasks.py:178`).

This defect is currently invisible because Defect 1 kills the run earlier. It
will surface as soon as Defect 1 is fixed, and Defect 3 will hide it again.

**Verification query** (Supabase SQL Editor) — run this before writing the fix,
so the migration is written against the real state:

```sql
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conname LIKE 'ck_alerts%';
```

**Fix.** Do **not** edit `0021` or `0023` — both have already run in production.
Add a new revision on top of the current head (`0027_merge_catalog_legacy`) that
sets the union of both value sets:

```
triggered_by_type IN ('SOS_BUTTON','SEVERE_SYMPTOM','MISSED_DOSES','ADVERSE_EVENT','ADHERENCE_REVIEW')
```

Use the same `DROP CONSTRAINT` / `ADD CONSTRAINT ... NOT VALID` / `VALIDATE
CONSTRAINT` two-step as `0009` and `0023`: `VALIDATE` takes only SHARE UPDATE
EXCLUSIVE, so re-scanning existing rows does not block writers on `alerts` —
which include the SOS red-alert safety path.

`ck_alerts_alert_type` needs no change. The `0021` version
(`RED_ALERT, WARNING, SUSPECTED_ADVERSE_EVENT`) is a superset of the `0009`
version, and `0023` does not touch that column.

---

### Defect 3 — over-broad `except IntegrityError` masks constraint violations (P1, fixed)

`_persist_one` wraps the entire `async with self._db.begin():` block — the review
insert **and** the alert/notification writes — in a single
`except IntegrityError` at `src/modules/adherence_review/service.py:555`, and
treats every hit as an idempotent replay.

A CHECK violation is also an `IntegrityError`. So Defect 2 would be logged as
`"Adherence review already exists for patient ... (idempotent replay)"`,
counted in `stats['replayed']`, and the review row would roll back with it. The
job would report success while writing nothing, indefinitely.

**Fix.** Narrow the catch. Only SQLSTATE `23505` (`unique_violation`) raised by
`uq_adherence_reviews_patient_date` is a genuine replay. Inspect
`err.orig.sqlstate` (asyncpg) and confirm the constraint name; anything else must
be `logger.exception`-ed and either re-raised or counted into a new
`stats['failed']` bucket so the run continues to the next patient. Phase C is
already per-patient (plan 6.2), so continuing is safe and preferable to aborting
the night.

---

### Defect 4 — `alembic/env.py` does not import `adherence_review` models (P1)

`alembic/env.py:19-24` imports six model modules; `adherence_review` is missing.
`alembic upgrade head` is unaffected — it replays revisions and never consults
metadata — which is why this has stayed hidden. The next
`alembic revision --autogenerate` will read the absent table as "should not
exist" and emit `DROP TABLE adherence_reviews`.

This is the identical defect that file's own docstring was written to prevent.

**Fix.** Add:

```python
from src.modules.adherence_review import models as _adherence_review_models  # noqa: F401,E402
```

Then verify by running `alembic revision --autogenerate` into a throwaway file
against a schema at head, confirming the generated `upgrade()` body is empty, and
deleting the file.

---

### Defect 5 — the same import gap probably affects every other Celery task (P1, needs confirmation)

The import-closure walk shows `src/modules/agents/tasks.py` also fails to reach
`admin.models`. That module owns five tasks:

- `agents.autoschedule`
- `agents.scan_missed_doses`
- `agents.scan_due_doses`
- `agents.summarize_daily_adverse_events`
- `agents.send_notification`

`configure_mappers()` is process-global and all-or-nothing, so if nothing else in
the worker process imports `admin.models` at runtime, every one of these fails
the same way — meaning background reminders and the missed-dose scan may also be
down, not just the nightly review.

**Verification** — run before writing any code, this determines the real blast
radius:

```bash
docker logs remindrx_worker --since 3h 2>&1 | grep -c NoReferencedTableError
```

```bash
docker logs remindrx_worker --since 3h 2>&1 | grep "raised unexpected" | sed 's/\[.*\]//' | sort | uniq -c
```

`agents.scan_due_doses` runs every minute. If it is also broken, the first count
will be in the hundreds. If it returns 0 aside from the two adherence-review
lines, something imports `admin.models` at runtime and the scope narrows back to
Defect 1 alone.

**Fix.** Whatever the count says, apply the shared registry import (Step 6) to
`src/modules/agents/tasks.py` as well. The current situation — where a task
module works only because of an incidental transitive import — is not a
guarantee anyone should rely on.

---

## 3. Why the test suite did not catch this

- `tests/conftest.py:8` imports `src.main.app`, which pulls in every router and
  therefore every model. Every fixture runs with a fully populated registry, so
  no test ever exercises the isolated import path a Celery worker actually uses.
- `tests/test_services/test_adherence_review_orchestrator.py` mocks all four
  repositories and the LLM call. It tests orchestration logic, never real ORM
  configuration and never a real CHECK constraint.
- Net result: roughly thirty tests across four files, all green, against a
  feature that has produced zero output in production.

---

## 4. Execution steps

### Step 0 — Establish real state before writing code — DONE

1. Ran the `pg_constraint` query from Defect 2 against production. Confirmed:
   `ADHERENCE_REVIEW` is missing, `ADVERSE_EVENT` is present. `0021` won the
   traversal race.
2. Worker-log commands from Defect 5 (whether `agents.tasks` was also failing
   in production) were **not** run — the fix was applied proactively based on
   the static import-closure analysis, which showed the identical gap. Still
   worth confirming in production logs post-deploy, but does not block the
   fix.

### Step 1 — Fix the ORM registry (Defect 1) — DONE

Added the model-registry import to `src/modules/adherence_review/tasks.py`
(via `src/core/models_registry.py`, see Step 6).

**Correction found while verifying:** the obvious check —
`import <module>; from sqlalchemy.orm import configure_mappers;
configure_mappers()` — returns `OK` regardless of whether the fix is present.
Proved this directly: importing only `src.modules.adherence.models` (which
declares `Alert.assigned_doctor_id`) with `admin.models` never imported, then
calling `configure_mappers()`, still returns cleanly.
`configure_mappers()` validates `relationship()`-based mappings; a plain
`Column`-level `ForeignKey("doctor_profiles.user_id")` string reference is
resolved lazily against `MetaData` and is not touched by it. What production
actually hit was accessing `ForeignKey.column` — triggered in real usage by
unit-of-work dependency sorting during flush — which raises the identical
`NoReferencedTableError` outside of `configure_mappers()` entirely. Confirmed
directly:

```python
fk = list(Alert.__table__.c.assigned_doctor_id.foreign_keys)[0]
fk.column  # raises NoReferencedTableError here, not at configure_mappers()
```

The faithful, DB-free proxy for the real trigger is
`Base.metadata.sorted_tables`, which forces the same resolution path for
every table's `ForeignKeyConstraint`. Verified against the actual repository
files (not synthetic code) both ways, restoring the fix after each check:

```bash
# with the fix reverted (git stash), both task modules:
.venv/Scripts/python.exe -c "import src.modules.adherence_review.tasks; from src.core.database import Base; Base.metadata.sorted_tables"
# -> NoReferencedTableError, reproducing the production crash exactly

# with the fix restored (git stash pop):
.venv/Scripts/python.exe -c "import src.modules.adherence_review.tasks; from src.core.database import Base; Base.metadata.sorted_tables"
# -> no error
```

This is what `tests/test_core/test_models_registry.py` (Step 7) actually
checks — not `configure_mappers()`.

### Step 2 — Fix the Alembic metadata gap (Defect 4) — DONE

`alembic/env.py` now imports `src.core.models_registry`. Verified
`Base.metadata` registers all 23 tables, including `adherence_reviews` and
`doctor_profiles`, in a clean process. A full `--autogenerate` dry run against
a live database (empty diff expected) is still worth doing once a DB is
reachable, but the metadata-population half of the risk is confirmed fixed.

### Step 3 — New migration for the constraint union (Defect 2) — DONE

`alembic/versions/0028_alerts_adherence_review_check_fix.py`, `down_revision =
"0027_merge_catalog_legacy"`. Writes the five-value union with the `NOT VALID`
/ `VALIDATE` two-step. `downgrade()` restores the four-value set Step 0 found
in production (not `0023`'s original set), so it is reversible against the
state it was actually applied to. Head graph re-verified: single head,
`0028_alerts_review_check_fix`, no dangling `down_revision` references.

### Step 4 — Narrow the exception handling (Defect 3) — DONE

`AdherenceReviewService._persist_one` now inspects `err.orig.sqlstate` and
`err.orig.constraint_name`; only `23505` on `uq_adherence_reviews_patient_date`
returns the idempotent-replay `True`. Anything else re-raises.
`run_nightly_review`'s loop catches that re-raise per candidate, logs it,
increments a new `stats['failed']` counter, and `continue`s to the next
patient — Phase C stays per-patient (module docstring) instead of one bad
write aborting the whole night.

`tests/test_services/test_adherence_review_orchestrator.py` updated: the
existing replay test now constructs a realistic `UniqueViolationError`-shaped
`.orig` (`sqlstate="23505"`, matching `constraint_name`) instead of a bare
`Exception("dup")`, which the old broad catch could not tell apart from a
real failure. Three new tests added and passing: a CHECK-constraint
violation is counted as `failed` and not `replayed`; a `23505` on a
*different* constraint is also not treated as a replay; and one patient's
failure does not stop the rest of the night's candidates from being
processed.

### Step 5 — Extend the other task module (Defect 5) — DONE

`src/modules/agents/tasks.py` now imports `src.core.models_registry` too.
Verified against the real file with `Base.metadata.sorted_tables` the same
way as Step 1 (not `configure_mappers()` — see that section's correction).

### Step 6 — Remove the duplication that caused all of this — DONE

`src/core/models_registry.py` imports all seven `src/modules/*/models.py`
modules once. `alembic/env.py`, `src/modules/adherence_review/tasks.py`, and
`src/modules/agents/tasks.py` all import that single module instead of
hand-listing model modules. `docs/structure.md` updated to list the new file.

### Step 7 — Tests that would have caught it — DONE (2 of 3 run and pass locally; 1 needs a live DB)

`tests/test_core/test_models_registry.py` — no database required, runs and
passes locally:

1. `test_registry_completeness` — globs `src/modules/*/models.py`, parses
   `src/core/models_registry.py`'s imports via `ast`, fails if any model
   module is missing from the registry.
2. `test_task_module_resolves_all_foreign_keys_in_isolation`, parametrised
   over every `src/modules/*/tasks.py` found by glob (currently
   `adherence_review.tasks` and `agents.tasks`) — spawns a clean subprocess
   that imports only that one module and forces
   `Base.metadata.sorted_tables`, **not** `configure_mappers()` (see Step
   1's correction for why). Manually confirmed to fail with
   `NoReferencedTableError` against both real files with the fix reverted,
   and pass with it restored.

`tests/test_services/test_alert_check_constraints.py` — parametrised
integration test inserting an `Alert` through `AlertRepository.create_alert`
for every `triggered_by_type`/`alert_type` combination the CHECK constraints
must accept (`ADHERENCE_REVIEW`, `ADVERSE_EVENT`, and the three pre-existing
sources), matching the `AsyncSessionLocal` pattern the rest of the suite
uses (e.g. `tests/test_api/test_alerts.py`). **Could not be run in this
environment** — no Postgres instance was reachable locally
(`ConnectionRefusedError` on `localhost:5432`, confirmed pre-existing and
unrelated to this change: `tests/test_services/test_adherence_review_indicators.py`,
which also needs a live database, fails the same way on a clean checkout of
the pre-fix commit). Run it once a real database is reachable, before
trusting Defect 2's fix.

### Step 8 — Deploy

```bash
docker compose build worker beat && docker compose up -d worker beat
```

Then run `alembic upgrade head` for the Step 3 revision.

### Step 9 — Trigger a run without waiting for 05:00

An admin-only endpoint already exists for exactly this
(`src/modules/adherence_review/router.py:59`):

```
POST /api/v1/admin/adherence-reviews/run
```

It enqueues the same task Beat fires and returns `202 Accepted`. Then read the
outcome:

```bash
docker logs remindrx_worker --since 5m 2>&1 | grep -i "adherence review scan"
```

The expected line is
`Adherence review scan for <date>: {'candidates': N, 'reviewed': N, 'silenced': ..., 'llm_calls': ...}`.

### Step 10 — Answer the original question

Only once a run completes does the `candidates` figure become meaningful. Compare
it against the raw indicator numbers to determine whether a quiet result is
correct behaviour or a threshold that needs tuning — in particular
`adherence_review_min_doses=5`, which silences any patient with fewer than five
**due** doses in the seven-day window regardless of how poor their adherence is.

The due-dose filter matters here: a dose still `PENDING` inside its 60-minute
grace period counts toward neither numerator nor denominator, and the window is a
closed calendar range `[D-7, D)` in `Asia/Ho_Chi_Minh`, so the current day's
doses are never included.

### Step 11 — Decide on backfill

Two nights (30 and 31 August) produced no reviews. `run_nightly_review()` takes
`review_date` as a parameter, so replaying them is possible, but the escalation
ladder counts consecutive nights — they must be replayed in order, 30 before 31,
or `days_in_severity` will be wrong. Skipping the backfill is also defensible:
the cost is two days of missing history, and a skipped run degrades the ladder
conservatively (it delays escalation rather than accelerating it).

---

## 5. Documentation drift found while scanning

`docs/structure.md` and `.claude/rules/structure.md` enumerate the vertical
slices under `src/modules/` but omit `adherence_review/`, which exists, owns a
table, and has routers registered in `src/api/v1_router.py`. `docs/api-contract.md`
and `docs/schema.md` already document the feature correctly. Fold the structure
fix into the same commit.
