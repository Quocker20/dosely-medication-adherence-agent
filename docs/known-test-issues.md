# Known pre-existing test issues

Found while verifying the graded-adherence-review work (Stages 1–4,
`docs/graded-adherence-implementation.md`). None of these are caused by that
work — confirmed by running the affected files in isolation both before and
after the adherence changes, with identical results either way. Three were
fixed along the way since they were cheap and isolated; this file tracks what
is still open.

## Fixed already (for reference — not action items)

- **`tests/conftest.py`: `disable_response_cache` fixture had no
  `@pytest.fixture` decorator.** It sat directly below `disable_rate_limit`
  with no blank line and no decorator of its own, so Python parsed it as a
  second top-level function pytest never registered — the entire suite ran
  with the real read-through response cache live. Any test issuing two GETs
  to the same cached endpoint around a raw-DB write (bypassing the
  service-layer cache invalidation those writes normally go through) could
  read back stale data. Fixed by adding the missing decorator.
- **`dashboard/repository.py`'s `adherence_band` LOW filter uses strict `<`
  at the 50% boundary**, and `test_roster_filters_by_adherence_band` seeded
  its "low" patient at exactly 50%. Verified via `git show` against the
  pre-session commit that this assertion was never true — not something the
  adherence-band zero-dose fix or Stage 1–4 introduced. Since Stage 4's
  `AdherenceReviewService.compute_severity` deliberately mirrors the same
  strict-`<` convention for its own bands, the fix was to move the test's
  fixture to an unambiguous ~33% rather than change the boundary semantics.
- **`PatientService.update_routine` awaits
  `auth_repository.clear_need_onboarding(...)`** (added when `main` merged
  in the onboarding-gate rename), but five test fixtures across
  `test_autoschedule_triggers.py` and `test_patient_routine.py` still built
  `auth_repository=MagicMock()` — awaiting a `MagicMock` call raises
  `TypeError: object MagicMock can't be used in 'await' expression`. Fixed by
  switching those two fixture-builder functions to `AsyncMock()`.

## Still open

### 1. `tests/test_api/test_patient_app.py` — entirely orphaned (6 tests)

References a `client` fixture and imports from `src.services.store` that do
not exist anywhere in the current codebase (`tests/conftest.py` even wraps
the `store` import in `try/except ImportError`, defaulting to `None`). This
file predates the current FastAPI dependency-injected/real-Postgres test
architecture — it looks like a leftover from an earlier in-memory-store
prototype phase and was never migrated or deleted.

**Decision needed, not a fix I can make unilaterally:** delete the file, or
rewrite its 6 cases against the current `client`/`AsyncSessionLocal`
fixtures used by every other `test_api/*.py` file. The scenarios it covers
(dose-action idempotency, SOS idempotency, severe-survey alert, adherence
summary reflecting a dose action) are real and already covered elsewhere in
`tests/test_api/test_alerts.py` and `tests/test_services/
test_grouped_notifications_and_batch_actions.py` — so deleting may be the
lower-risk option, but that's a call for whoever owns test coverage
decisions, not something to do in passing.

### 2. Shared-Postgres/cache cross-test pollution — only reproduces in the full suite

The suite writes real, committed rows to a shared Postgres container (and,
now that fix #1 above actually enables it, a real short-TTL response cache)
with no transactional rollback between test modules. Each file cleans up its
own fixed phone numbers/keys before and after itself (see `_purge_test_users`
in `test_dashboard.py` for the pattern), but that only protects a file
against itself — a fixed key or phone number reused by a *different* file,
or a cached response still inside its TTL window when the next file runs,
can leak state across files depending on run order.

Two confirmed instances, both passing in isolation and failing only when the
complete suite runs end to end:

- `test_alerts.py::test_doctor_sees_health_surveys_of_prescribed_patients_only`
  — `UniqueViolationError` on `uq_medications_source_record`
  (`source_name='TEST'`, `source_record_key='TEST-SLICE7-MED'`), a fixed key
  also used elsewhere.
- `test_auth.py::test_doctor_change_password_clears_need_onboarding` —
  surfaced only after fix #1 (the cache was previously always bypassed due
  to the missing decorator, which accidentally hid this). 5/5 passing alone
  and as a whole file; fails only in the full run.

`test_medications.py::test_medication_list_and_detail_returns_active_only`
was on the original failure list and is **no longer failing** after fix #1 —
it was very likely a symptom of the same dead `disable_response_cache`
fixture, not a real assertion bug, so it isn't listed here as still open.

This is a structural gap in the suite's isolation strategy, not a one-line
fix: options are (a) give every test file's fixed keys/phone numbers a
unique suffix (cheap, doesn't fix the underlying pattern, just avoids
collision), or (b) wrap each test in its own transaction that rolls back
instead of committing (bigger change, touches every file using
`AsyncSessionLocal` directly, but is the actual fix). Expect more instances
to surface over time as the suite grows — don't assume the two above are
exhaustive.

### 3. `tests/test_services/test_alert_service.py` — two tests fail on a mocked patient-name join

`test_agent_detected_alert_keeps_its_own_trigger_type_and_severity` and
`test_plain_sos_still_writes_a_critical_button_press` both fail with

```
TypeError: 'types.SimpleNamespace' object is not subscriptable
```

at `src/modules/adherence/service.py:759`, inside `_with_patient_name`:
`response.patient_name = patient_row[0].name if patient_row is not None else
None`. The code expects a `Row`-like object it can index (`patient_row[0]`);
the test's mocked `db.execute(...).first()` (or equivalent) returns a bare
`SimpleNamespace`, which isn't subscriptable. Not a real production bug —
`AsyncSession.execute(...).first()` really does return a `Row`, so this is
the test double drifting from what SQLAlchemy actually hands back, not
`_with_patient_name` itself being wrong.

Found while verifying the nightly-adherence-review fix
(`docs/adherence-review-fix-plan.md`): confirmed pre-existing and unrelated
by running this file in an isolated `git worktree` checked out at the commit
before that fix, with the same `.env` — both tests fail identically there,
with zero files from the fix present.

**Fix needed, not done here:** give the mocked `db.execute` a return whose
`.first()` (or whichever accessor `_with_patient_name` actually calls) is
subscriptable/attribute-accessible the way a real `Row` is — a `SimpleNamespace`
wrapped in a 1-tuple, or a small `Row`-like stand-in, matching whatever
pattern the rest of the suite already uses for a mocked single-row `SELECT`.

## How to reproduce

```bash
# Orphaned file -- fails standalone, no interaction with other tests needed
pytest tests/test_api/test_patient_app.py -v

# Cross-test pollution -- only reproduces with the full suite; a subset may
# pass even when it includes the two files above, since it depends on which
# other files ran first and populated the shared state.
pytest -q --ignore=test_schedule.py

# Mocked patient-name join -- fails standalone, no DB or other tests needed
pytest tests/test_services/test_alert_service.py -v
```
