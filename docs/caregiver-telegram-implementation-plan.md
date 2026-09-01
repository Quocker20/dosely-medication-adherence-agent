# Caregiver Notifications via Telegram Bot — Implementation Plan

Status: approved design, not yet implemented.
Branch: `feat/caregiver-tele`, branched from `main` at `603cd5c`.
Alembic head on `main`: `0029_routine_overrides` — the two migrations below chain
onto it as `0030` and `0031`.

> **Supersedes the Zalo OA design.** An earlier version of this feature was built
> against Zalo Official Account CS messaging (branch `feat/caregiver`, commit
> `13195a7`, fully implemented and green against a fake client). It is abandoned
> at the platform layer only: Zalo gates the messaging API behind **business
> verification** — an OA can only send `message/cs` once verified against a
> business registration certificate, trademark, or trade name, none of which a
> student project has. The unverified tier explicitly cannot use messaging,
> chatbot, or broadcast at all. Telegram has no equivalent gate. Every
> non-platform decision from that build (caregiver-as-record, binding flow
> shape, delivery-log reuse, trigger set, race handling) carries over and is
> restated here; the concrete lessons that build produced are in the appendix.

---

## 0. Why Telegram, and what it deletes

### The blocker it removes

| | Zalo OA | Telegram Bot |
|---|---|---|
| Account to send from | Official Account, **business verification required** (business licence / trademark / trade name), 14-day deadline | Bot created by messaging `@BotFather` from any personal account, instant |
| Cost | free tier is 8 msgs / 48h of last interaction, then ~55đ each | free, no per-message cost |
| Credentials | `app_id` + `app_secret` + OAuth `refresh_token` that **rotates on every use** | one static bot token, no refresh, no expiry |

### The constraint it removes — this is the bigger design change

Zalo's CS channel only accepts a send **within 7 days of the user's last
interaction**. That single rule shaped half the old design. Telegram has no such
window: once a user presses START on a bot, the bot may message them
indefinitely. The only way to become unreachable is the user **blocking the
bot**, which Telegram reports explicitly and permanently as HTTP `403`.

Deleted outright as a result:

- **`CG_KEEPALIVE` (the old T4 trigger)** — it existed for exactly one reason:
  nudge a quiet caregiver before the 7-day window shut, because past it there
  was no way back in. With no window, nothing needs protecting. Gone.
- **`STALE` link status** — "bound but window shut" is not a state that exists.
  Replaced by `BLOCKED`, which is a *real*, *detectable* state (from a `403`),
  not a timer.
- **`SKIPPED_WINDOW_CLOSED` delivery status** and the window-open guard in
  `queue_message`.
- **The window-open condition on the weekly report claim** — T2's predicate is
  now purely a cadence check.
- Config `zalo_cs_window_days`, `caregiver_keepalive_after_days`,
  `zalo_oa_id`, `zalo_app_id`, `zalo_app_secret`, `zalo_refresh_token`
  (six settings down to four).
- `core/zalo.py`'s entire access-token refresh machinery — the Redis-cached
  token, the SETNX refresh lock guarding a rotating refresh token, the
  early-expiry TTL. Telegram puts a static token in the URL path of every call.

### Facts this plan is built on

Verified against [core.telegram.org/bots/api](https://core.telegram.org/bots/api),
not inferred:

- Base URL: `https://api.telegram.org/bot<token>/METHOD_NAME`
- `sendMessage` requires `chat_id` and `text`. Message text cap is 4096
  characters (Telegram's general message limit) — our templates are one or two
  lines, so this is never near.
- Success: `{"ok": true, "result": {...}}`. Failure: `{"ok": false,
  "error_code": N, "description": "...", "parameters": {"retry_after": N}}`.
- Webhook auth: `setWebhook` accepts a `secret_token` (1–256 chars); Telegram
  then sends header **`X-Telegram-Bot-Api-Secret-Token`** carrying that value on
  every delivery. *(This is documented and exact — unlike the Zalo build, where
  the signature construction was a best guess flagged as unverified in code.)*
- Webhook URL must be HTTPS on port 443, 80, 88, or 8443.
- Deep link: `https://t.me/<bot_username>?start=<payload>`, payload ≤ 64 chars,
  delivered to the bot as a message with text `/start <payload>`.
- Rate limits: ~1 message/second per chat, ~30/second globally. `429` carries an
  exact `retry_after` in seconds.

---

## 1. Target data model

### 1.1 `caregiver_links` (reshaped, same table)

```
id                            UUID PK
patient_id                    UUID NOT NULL FK -> patient_profiles(user_id) ON DELETE CASCADE
phone                         VARCHAR(20) NOT NULL     -- doctor contact only; never addresses a send
relationship                  VARCHAR(50) NULL
link_code                     VARCHAR(8)  NULL         -- one-time binding code, cleared on bind
telegram_chat_id              BIGINT      NULL         -- NULL => undeliverable
telegram_bound_at             TIMESTAMPTZ NULL
telegram_last_interaction_at  TIMESTAMPTZ NULL         -- diagnostics only (see 1.3)
last_report_sent_at           TIMESTAMPTZ NULL         -- T2 cadence anchor
last_message_sent_at          TIMESTAMPTZ NULL         -- display only (see 1.3)
status                        VARCHAR(20) NOT NULL DEFAULT 'PENDING_BINDING'
created_at                    TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

Dropped from today's table: `caregiver_user_id` (+ its FK to `users`),
`channels`, `uq_caregiver_links_patient_caregiver`. No `name` column — one phone
can be linked to several patients and two links would otherwise disagree about
the same person's name.

`telegram_chat_id` is **BIGINT, not VARCHAR** — Telegram chat ids are integers
and have exceeded 32 bits since 2021, so `INTEGER` would silently truncate.

`status`: `PENDING_BINDING` → `ACTIVE` (bound) → `BLOCKED` (caregiver blocked the
bot; set automatically from a `403` on send) or `INACTIVE` (manual disable). A
`BLOCKED` link returns to `ACTIVE` if that chat_id ever messages the bot again
(unblocking is a thing users do). Enforced by a CHECK constraint.

### 1.2 Indexes

Each backs one specific query in this plan. None is speculative.

| Index | Backs |
|---|---|
| `UNIQUE (patient_id, phone)` | duplicate guard on create; list-by-patient rides the leading column |
| `UNIQUE (link_code) WHERE link_code IS NOT NULL` | webhook binding lookup; also makes a concurrent code collision impossible |
| `(telegram_chat_id) WHERE telegram_chat_id IS NOT NULL` | webhook interaction refresh and `403`-driven block marking — one caregiver may hold several links, all updated in one statement |
| `(last_report_sent_at) WHERE telegram_chat_id IS NOT NULL` | the nightly due-report claim scan (stage 9) |

The two partial predicates matter: during rollout most rows are unbound and can
never be sent to, and a non-partial index would make the nightly scan read them
anyway.

Note the report index is a **single column** here, where the Zalo design needed a
composite `(last_report_sent_at, telegram_last_interaction_at)` — because the
window condition is gone from the claim predicate.

### 1.3 Two columns that are deliberately not load-bearing

`telegram_last_interaction_at` and `last_message_sent_at` are written but no
claim query depends on either.

- `last_report_sent_at` **is** load-bearing — it is the T2 cadence anchor and is
  written by the same statement that claims a link, so it cannot drift.
- `telegram_last_interaction_at` is the only signal short of a failed send that
  tells anyone whether a binding is live. The webhook has to run on every update
  regardless (to catch `/start`), so writing it is free.
- `last_message_sent_at` exists for the caregiver-list UI ("last notified").

Both are kept knowingly, not by inertia. If a future reader wonders why they are
not indexed: nothing queries them.

### 1.4 `notification_deliveries` (extended, not duplicated)

The table already is a send log: `channel`, `template_code`,
`provider_message_id`, `status`, `attempt_no`, `idempotency_key UNIQUE`,
`sent_at`. A second table would mean maintaining two copies of the same retry
state machine.

```
recipient_user_id   UUID -> becomes NULLABLE
caregiver_link_id   UUID NULL REFERENCES caregiver_links(id) ON DELETE CASCADE   -- new
status              VARCHAR(20) -> VARCHAR(30)
CHECK (num_nonnulls(recipient_user_id, caregiver_link_id) = 1)
```

`channel` is always `TELEGRAM` for caregiver rows.

Statuses used: `QUEUED` → `SENDING` → `SENT`, or terminal `FAILED` /
`BLOCKED_BY_USER` / `SKIPPED_NO_BINDING`.

**Why `ON DELETE CASCADE` and not `SET NULL`** — this is not a style choice.
`caregiver_link_id` participates in the XOR CHECK above. Unlike `alert_id` /
`scheduled_dose_id`, whose sibling `recipient_user_id` stays non-null for every
row referencing them, a caregiver delivery row has `recipient_user_id = NULL`
already. `SET NULL` would leave *both* columns null and the row would violate its
own CHECK the instant the link is deleted — Postgres raises it from the FK's own
implicit UPDATE, which is a confusing place to debug from. This was hit for real
during the Zalo build. Cascading is also semantically right: a caregiver's
delivery history has no meaning once the link is gone.

**Why widen `status` to 30** — the longest status here is `SKIPPED_NO_BINDING` at
19 characters, which does fit in 20. That is one character of headroom, and the
Zalo build hit exactly this wall at runtime (`SKIPPED_WINDOW_CLOSED`, 21 chars,
`StringDataRightTruncationError` on first insert). Widening a `VARCHAR` is a
metadata-only ALTER with no table rewrite. Cheap insurance against the next
status name.

---

## 2. Triggers

Three, down from five.

| Code | Fires when | Message (1 line + footer) |
|---|---|---|
| `CG_ALERT_RED` | an `alerts` row with `alert_type = 'RED_ALERT'` is created | "Bác {tên} vừa có cảnh báo cần chú ý. Bác sĩ đã được thông báo." Wording branches on `triggered_by_type`. No medication names. |
| `CG_REPORT` | nightly, ≥ `caregiver_report_interval_days` since this link's last report | "Tuần qua bác {tên} uống thuốc đúng giờ {n}%." Escalated wording below the existing thresholds. |
| `CG_ALERT_RESOLVED` | doctor resolves an alert this pipeline sent `CG_ALERT_RED` for | "Cảnh báo của bác {tên} đã được bác sĩ xử lý." |

Every message carries a short footer telling the caregiver they can reply `/stop`
to the bot to stop receiving messages. On Zalo the footer was load-bearing (it
was the window-reset mechanism); here it is purely a courtesy and an opt-out
affordance, which is a better reason to have one.

### 2.1 `CG_ALERT_RED`'s predicate is `alert_type`, not `severity`

Re-verified against current `main`. The severities are not what one would guess:

| Source | `triggered_by_type` | `alert_type` | `severity` | Site |
|---|---|---|---|---|
| SOS button / agent-detected | `SOS_BUTTON` / `SEVERE_SYMPTOM` | `RED_ALERT` | `CRITICAL` | `adherence/service.py:703` |
| Health-survey severe symptom | `SEVERE_SYMPTOM` | `RED_ALERT` | **`HIGH`** | `adherence/service.py:524` |
| 3 missed critical doses | `MISSED_DOSES` | `RED_ALERT` | **`HIGH`** | `agents/service.py:783` |
| Review → DOCTOR_ALERT | `ADHERENCE_REVIEW` | `RED_ALERT` | **`HIGH`** | `adherence_review/service.py:532` |
| Review → DOCTOR_WARNING | `ADHERENCE_REVIEW` | `WARNING` | `MEDIUM` | `adherence_review/service.py:541` |
| Daily adverse-event digest | `ADVERSE_EVENT` | `SUSPECTED_ADVERSE_EVENT` | `MEDIUM` | `agents/tasks.py:184` |

Filtering on `severity == 'CRITICAL'` would silently drop the missed-critical
chain and the low-adherence escalation — the two cases this feature exists for.
`alert_type == 'RED_ALERT'` captures exactly the right four and excludes the
doctor-only `WARNING` and the nightly digest.

### 2.2 Thresholds and timing reuse existing settings

No new tuning constants. `CG_REPORT`'s wording escalates on the existing
`adherence_moderate_threshold` (70.0) and `adherence_severe_threshold` (50.0), so
the caregiver's number can never disagree with what the doctor's dashboard shows.
Dispatch is clamped to `adherence_review_patient_send_from`/`_to` (08:00–20:00),
the same quiet-hours window the patient path already respects.

---

## 3. Stages

Each stage is independently committable and leaves the test suite green.

---

### Stage 0 — Sync the database

**The working database is at `0028_alerts_review_check_fix`; `main`'s code is at
`0029_routine_overrides`.** Run `alembic upgrade head` before anything else, or
stage 1's migration chains onto a revision the DB has never applied.

Verify: `alembic current` returns `0029_routine_overrides`, and
`\d routine_overrides` shows the table `main` added.

---

### Stage 1 — Migration A: reshape `caregiver_links`

**Files:** `alembic/versions/0030_caregiver_links_telegram.py`
(revision id `0030_caregiver_telegram`, 22 chars — **must stay ≤32**, see the
appendix).

**Steps**

1. `DELETE FROM caregiver_links` — the table holds only fake seed data, and every
   surviving row would carry a `caregiver_user_id` that no longer means anything.
   Deleting is the data step; there is nothing to backfill.
2. Drop constraint `uq_caregiver_links_patient_caregiver`, then drop column
   `caregiver_user_id` (removes FK `caregiver_links_caregiver_user_id_fkey` with
   it). Drop column `channels`.
3. Add the new columns from §1.1, all nullable except `phone` and `status`.
   `phone` can be added `NOT NULL` without a default only because the table was
   just emptied.
4. Add the CHECK constraint on `status`
   (`PENDING_BINDING`/`ACTIVE`/`BLOCKED`/`INACTIVE`).
5. Build all four indexes from §1.2 `CONCURRENTLY` inside
   `op.get_context().autocommit_block()`, then attach **only**
   `uq_caregiver_links_patient_phone` as a constraint via
   `ADD CONSTRAINT ... UNIQUE USING INDEX`.

**The trap in step 5, pre-solved:** `uq_caregiver_links_link_code` is a *partial*
index (`WHERE link_code IS NOT NULL`). Postgres **rejects**
`ADD CONSTRAINT ... UNIQUE USING INDEX` on a partial index with
`WrongObjectTypeError: is a partial index`. Leave it as a plain unique index —
the uniqueness guarantee is identical, only the constraint-catalog entry and its
name in error messages are absent. The downgrade must then use
`op.drop_index(...)` for it, not `op.drop_constraint(...)`.

**Concurrency:** `CREATE INDEX CONCURRENTLY` cannot run inside a transaction; the
`autocommit_block()` is what makes it legal. Note the sharp edge this creates on
failure: entering the block **commits the ambient transaction**, so a statement
that fails *after* the block leaves the concurrent indexes committed while the
migration itself rolls back and the version stamp never advances. Recovery is
manual DDL. Keep everything that can fail *before* the autocommit block.

**Downgrade:** recreate `caregiver_user_id` nullable, its FK, and the old unique
constraint, then set `NOT NULL` (safe — the table is empty). Deleted rows are not
restorable; say so in the docstring rather than implying otherwise.

**Verify:** `upgrade head` → `\d caregiver_links` shows four indexes and the CHECK
→ `downgrade -1` → shape matches `main` → `upgrade head` again.

---

### Stage 2 — Migration B: caregiver rows in `notification_deliveries`

**Files:** `alembic/versions/0031_notification_caregiver_recipient.py`
(revision id `0031_notif_cg_recipient`, 22 chars).

**Steps**

1. `ALTER COLUMN recipient_user_id DROP NOT NULL`.
2. `ALTER COLUMN status TYPE VARCHAR(30)` (see §1.4 for why).
3. Add `caregiver_link_id UUID NULL REFERENCES caregiver_links(id) ON DELETE
   CASCADE` (§1.4 for why CASCADE). Note this is a `UUID` — it references
   `caregiver_links.id`, not the `BIGINT` `telegram_chat_id`.
4. Add `CHECK (num_nonnulls(recipient_user_id, caregiver_link_id) = 1)` as
   `NOT VALID` first, then `VALIDATE CONSTRAINT` inside the autocommit block.
5. Add index `(caregiver_link_id, created_at DESC) WHERE caregiver_link_id IS NOT
   NULL` `CONCURRENTLY`.

**Why `NOT VALID` then `VALIDATE`:** adding a validated CHECK holds an
`ACCESS EXCLUSIVE` lock while it scans every existing row.
`notification_deliveries` is the highest-volume table in this schema. `NOT VALID`
takes that lock only briefly; `VALIDATE` then scans under
`SHARE UPDATE EXCLUSIVE`, which blocks neither reads nor writes. Every existing
row already satisfies the constraint (all have a `recipient_user_id`), so
validation cannot fail.

**Verify:** insert a row with both columns null and one with both set — both
rejected. `downgrade -1` / `upgrade head` round-trip. Confirm the FK reads
`ON DELETE CASCADE` in `\d notification_deliveries`, and that deleting a
caregiver link with deliveries attached succeeds rather than raising the CHECK.

---

### Stage 3 — New `caregivers` module: model and repository

**Files:** `src/modules/caregivers/{__init__,models,repository,schemas}.py`;
remove `CaregiverLink` from `src/modules/patients/models.py`; register in
`src/core/models_registry.py`.

**Steps**

1. Move `CaregiverLink` into `src/modules/caregivers/models.py` with the reshaped
   columns. Keep the `relationship_label` attribute name mapped to the
   `relationship` column — the plain name collides with SQLAlchemy's own
   `relationship()`.
2. **Update `NotificationDelivery` in `src/modules/adherence/models.py` in this
   same stage** — add `caregiver_link_id`, make `recipient_user_id` nullable,
   widen `status` to `String(30)`. The migration and the ORM model are two
   separate edits; a migration-only change passes `alembic upgrade head` happily
   and then fails at the first insert with `TypeError: 'caregiver_link_id' is an
   invalid keyword argument`. This exact miss cost a debugging cycle in the Zalo
   build.
3. `CaregiverRepository`, statement-only, no commit/rollback:
   - `list_by_patient(patient_id)` — one SELECT, rides `(patient_id, phone)`.
   - `create_link(patient_id, phone, relationship, link_code)`.
   - `get_link(link_id, patient_id)` / `get_link_by_id(link_id)` / `delete_link`.
   - `bind_by_code(link_code, telegram_chat_id, now)` — CAS, stage 6.
   - `touch_interaction(telegram_chat_id, occurred_at)` — stage 6.
   - `mark_blocked(telegram_chat_id)` / `mark_unblocked(telegram_chat_id)`.
   - `list_deliverable_for_patient(patient_id)` and
     `list_deliverable_for_patients(patient_ids)` — bound, `ACTIVE` links.
   - `claim_due_reports(now, interval_days)` — stage 9.
4. Register the model module in `models_registry` so Celery tasks resolve FK
   targets — the `NoReferencedTableError` failure mode documented in that file.

**N+1 watch:** `list_by_patient` must return everything the response DTO needs.
Because every displayed field lives on the row itself, rendering the caregiver
list is one query regardless of link count. Do **not** add a `selectinload` to
`notification_deliveries` here — the denormalized columns exist precisely so that
relationship is never traversed on a read path.

---

### Stage 4 — Strip caregiver read access

**Files:** `src/modules/patients/repository.py`,
`src/modules/adherence/repository.py`,
`src/modules/adherence_review/repository.py`,
`src/modules/agents/repository.py`,
`src/modules/prescriptions/repository.py`, plus three routers.

**Steps**

1. Delete `_has_active_caregiver_filter` from all five repositories (verified all
   five still present on current `main`) and drop the disjunct from each
   `_access_filter`. Each reduces to
   `or_(patient_id_col == actor_id, _has_prescribed_filter())`.
2. Remove `"CAREGIVER"` from `require_roles(...)` in `adherence/router.py:65`,
   `adherence_review/router.py:19`, `agents/router.py:46`.
3. Remove the now-dead `CaregiverLink` imports from those repositories.
4. Update docstrings describing access as "self / doctor-prescribed /
   active-caregiver" — including the prescription PDF export's, which inherits
   `get_prescription`'s rule.

**Behavioural impact — the largest in this plan.** Six read surfaces narrow:
routine, adherence summary and logs, health surveys, schedules, adherence
reviews, prescriptions and the prescription PDF. Out-of-scope behaviour is
unchanged (empty page on lists, 404 on details) — only the set of qualifying
actors shrinks.

**Tests to rewrite, not delete:** invert the caregiver assertions in
`tests/test_api/test_adherence_reviews.py` and `tests/test_api/test_prescriptions.py`
so the removal stays covered rather than untested — a caregiver-phone account must
now fail to authenticate at all. Drop the `caregiver_repository=MagicMock()`
kwarg from `test_patient_routine.py` and `test_autoschedule_triggers.py`.

**Verify:** full pytest run. Any test still asserting caregiver read access is a
real regression signal, not a test to silence.

---

### Stage 5 — Telegram client and config

**Files:** `src/core/telegram.py`, `src/core/config.py`.

**Steps**

1. Config — four new settings plus one reused:
   ```
   telegram_enabled: bool = False
   telegram_bot_token: str = ""
   telegram_webhook_secret: str = ""
   telegram_bot_username: str = ""          # for building t.me deep links
   telegram_api_base_url: str = "https://api.telegram.org"
   caregiver_report_interval_days: int = 7
   ```
2. `src/core/telegram.py` — a `TelegramClient` protocol plus `HttpTelegramClient`
   and `FakeTelegramClient`. It belongs in `core/` for the same reason `redis.py`
   does: it is low-level transport, and putting it in the module would force any
   future caller to import a domain slice to send a message.
   - `send_message(chat_id: int, text: str) -> str` returns the provider message
     id (`result.message_id`).
   - Error classification, driven by Telegram's documented response shape:

     | Condition | Raise | Retry? |
     |---|---|---|
     | `error_code == 403` (blocked/kicked) | `TelegramBlockedError` | never — also marks the link `BLOCKED` |
     | `error_code == 400` (chat not found / bad request) | `TelegramPermanentError` | never |
     | `error_code == 429` | `TelegramRateLimitError(retry_after=N)` | yes, after **exactly** `parameters.retry_after` seconds |
     | HTTP 5xx, timeout, connection reset | `TelegramTransientError` | yes, backoff ladder |

     The `429` case is a genuine improvement over the Zalo design: Telegram
     supplies the exact wait, so the retry honours it instead of guessing.
   - **No token refresh, no Redis lock, no TTL cache.** The bot token is static
     and goes in the URL path of every call.
3. `get_telegram_client()` factory: when `telegram_enabled` is `False` (the
   default) it returns a `FakeTelegramClient` singleton and **never constructs**
   `HttpTelegramClient`, so an empty token can never be used to attempt a real
   call.

`httpx` is already a dependency (`requirements.txt:42`) — no new packages.

**Rate limiting, honestly scoped:** Telegram allows ~1 msg/sec per chat and ~30/sec
globally. Sends are dispatched one Celery task per delivery, which naturally
spaces them, and this project's caregiver volume is far below either ceiling. No
limiter is implemented. If fan-out ever grows enough to matter, the place to add
one is the task's `rate_limit` option — noted here so the next reader does not
have to infer that it was considered.

---

### Stage 6 — Webhook receiver and binding flow

**Files:** `src/modules/caregivers/webhook_router.py`, `src/main.py`,
plus `handle_webhook_update` in `src/modules/caregivers/service.py`.

**The binding flow**

1. Patient adds a caregiver by phone. Backend mints a 6-char `link_code` from an
   unambiguous alphabet (no `0/O`, no `1/I/L` — a human reads it aloud).
2. App shows a tappable deep link `https://t.me/<bot_username>?start=<link_code>`
   (plus the same link as a QR for cross-device). This is a **one-tap** flow,
   materially better than Zalo's "type this code into a chat": Telegram delivers
   the payload automatically as `/start <link_code>` when the caregiver presses
   START.
3. `POST /webhooks/telegram` receives the update. Signature verified **before any
   DB access** by comparing header `X-Telegram-Bot-Api-Secret-Token` against
   `telegram_webhook_secret` with `hmac.compare_digest` (constant-time; a plain
   `==` on a secret is a timing oracle). Mismatch or missing → `401`, no write,
   and do not log the body.
4. Text `/start <code>` matching a live `link_code` → atomic bind. Bot replies
   confirming, so the caregiver gets feedback.
5. `/stop` → set that chat's links `INACTIVE` and confirm. This is the opt-out
   the footer advertises.
6. Any other update from a known `chat_id` → refresh
   `telegram_last_interaction_at`, and if the link was `BLOCKED`, restore it to
   `ACTIVE` (the user unblocked and messaged again).

**Mounting:** at the app root in `main.py` alongside `dashboard_ws_router`, not
under `/api/v1` — Telegram calls it directly and it is not part of the
authenticated API surface.

**Race — binding.** Two updates carrying the same code must not both bind. Use a
compare-and-set update, never read-then-write:

```sql
UPDATE caregiver_links
   SET telegram_chat_id = :chat_id, telegram_bound_at = :now,
       telegram_last_interaction_at = :now, status = 'ACTIVE', link_code = NULL
 WHERE link_code = :code AND telegram_chat_id IS NULL
RETURNING id
```

Zero rows returned means someone else bound it first — reply with the
already-bound confirmation rather than an error, and do not distinguish that from
an unknown code (a bind response must not leak which codes are real). This
mirrors `AdherenceLogRepository.apply_dose_action_cas`.

**Race — duplicate/out-of-order deliveries.** Telegram retries a webhook that does
not return `2xx` and does not guarantee ordering. The interaction touch must
therefore never move the timestamp backwards:

```sql
UPDATE caregiver_links
   SET telegram_last_interaction_at = GREATEST(
           COALESCE(telegram_last_interaction_at, :ts), :ts)
 WHERE telegram_chat_id = :chat_id
```

No `patient_id` in the WHERE — one caregiver may hold several links and they all
share one Telegram account. This is one statement over the `telegram_chat_id`
partial index, not a loop.

**Always return 200 on a well-formed authenticated update**, including ones this
feature ignores. Telegram retries non-2xx, and an endpoint that errors on routine
chatter turns one update into a retry storm.

**Autobegin trap:** the handler reads before it writes. Any `SELECT` issued before
an explicit `async with self._db.begin():` autobegins a transaction that the
explicit `begin()` then refuses with `InvalidRequestError: A transaction is
already begun`. Follow `prescriptions/service.py::_resolve_or_create_patient`:
after any read preceding an explicit block,
`if self._db.in_transaction(): await self._db.commit()`.

---

### Stage 7 — Caregiver CRUD

**Files:** `src/modules/caregivers/{service,router,schemas}.py`; remove the three
handlers from `src/modules/patients/router.py`, the four caregiver methods and
`_resolve_or_create_caregiver` from `patients/service.py`, `CaregiverRepository`
from `patients/repository.py`, and the two caregiver DTOs from
`patients/schemas.py`; register in `src/api/v1_router.py`.

**Steps**

1. Keep the URLs exactly as they are —
   `POST/GET/DELETE /patients/{patient_id}/caregivers[/{id}]` — so the Android
   client's paths do not move. Only the handlers relocate.
2. `create_caregiver_link`: validate phone, generate `link_code`, insert. Catch
   `IntegrityError` on `(patient_id, phone)` → 409.
   **Delete `_resolve_or_create_caregiver` and everything downstream:** temp-PIN
   generation, `create_user`, the placeholder `patient_profiles` row with
   `name="NULL"`. A caregiver has no account.
3. Response DTO drops `caregiver_user_id`, `temp_password`, `channels`; adds
   `phone`, `link_code` (only while unbound), `telegram_deep_link` (built from
   `telegram_bot_username` + `link_code`, so the client never assembles it),
   `status`, `telegram_bound_at`, `last_message_sent_at`.
4. RBAC unchanged from today: create is PATIENT-self-only; list and delete are
   PATIENT-self or ADMIN. The existing deviation-from-contract docstrings stay
   accurate.

**Pydantic trap, pre-solved:** do **not** give the `relationship` response field a
`validation_alias="relationship_label"`. Constructing the model with
`relationship=link.relationship_label` — a keyword matching the *field* name, not
the alias — then silently yields `None`, because Pydantic v2 accepts only the
alias as a constructor kwarg unless `populate_by_name=True` is also set, and drops
unknown kwargs by default rather than erroring. The response is always built
explicitly in `_to_response`, never via `model_validate` on the ORM object, so the
alias buys nothing. Omit it.

---

### Stage 8 — Send pipeline

**Files:** `src/modules/caregivers/{templates,sender,delivery_repository,tasks}.py`,
`src/core/celery_app.py`.

**Steps**

1. `templates.py` — pure functions, no I/O, no LLM. Vietnamese text in, string
   out. One function per template code plus the shared `/stop` footer. Being pure
   makes wording testable without a database.
2. `delivery_repository.py` — statement-only access to `notification_deliveries`
   scoped to `caregiver_link_id` rows, so it never collides with
   `NotificationRepository`'s patient-push path on the same table.
   `claim_for_sending` is an atomic `QUEUED → SENDING` CAS bumping `attempt_no`;
   a second worker on the same id gets rowcount 0 and must not send.
3. `sender.py::queue_message(link, template_code, body, idempotency_key)`:
   - Guard: `telegram_chat_id IS NULL` or `status != 'ACTIVE'` → write a
     `SKIPPED_NO_BINDING` row and return `None`. Recorded rather than dropped —
     this is what the "caregiver unreachable" surfacing reads.
   - Otherwise insert a `QUEUED` row with `idempotency_key`, catching
     `IntegrityError` → already queued, return `None`.
   - **No window check.** There is no window.
   - Enqueue the Celery task **after** the transaction commits; enqueueing inside
     lets a worker pick up an id not yet visible in its own session.
4. `tasks.py::send_caregiver_message(delivery_id)`:
   - Claim (`QUEUED → SENDING`); not claimable → return, not an error.
   - **Commit the reads before the write branches** — `get_by_id` and
     `get_link_by_id` autobegin a transaction that the next explicit `begin()`
     would reject. Same autobegin trap as stage 6; it bit this exact function in
     the Zalo build.
   - Call `send_message` **outside any transaction**. Holding one across an HTTP
     call pins a connection for the duration of a third-party timeout.
   - `TelegramBlockedError` → mark delivery `BLOCKED_BY_USER` **and** the link
     `BLOCKED`. The system self-heals its own view of reachability — no Zalo
     equivalent existed.
   - `TelegramPermanentError` → `FAILED`, no retry.
   - `TelegramRateLimitError` → reset to `QUEUED`, retry with `countdown =
     retry_after`.
   - `TelegramTransientError` → reset to `QUEUED`, retry on the 30s/2m/8m ladder
     with jitter, `max_retries=3`.
   - Own engine per invocation with `NullPool`, matching
     `adherence_review/tasks.py` — asyncpg connections bind to the loop that
     opened them and `asyncio.run` builds a fresh loop per call.
5. Register `src.modules.caregivers.tasks` in `celery_app`'s `include` list.

**Known limit, accepted:** `sendMessage` takes no idempotency key. A crash between
a successful send and the `SENT` write duplicates on retry. At-least-once is the
right trade for a one-line notification; the `SENDING` marker narrows the window
to a single HTTP call. Document it in the module docstring rather than implying
exactly-once.

**Fail-open, always:** dispatch happens after the clinical write has committed and
never raises into it. A Telegram outage costs a caregiver message, never an
`Alert` or a dose action — the same rule `publish_dashboard_event` follows.

---

### Stage 9 — Trigger wiring

**Files:** `src/modules/adherence/service.py`, `src/modules/agents/service.py`,
`src/modules/adherence_review/service.py`, `src/core/celery_app.py`.

#### 9a — `CG_ALERT_RED`

A fail-open `notify_caregivers_of_alert(db, patient_id, alert)` helper, called
after commit at each single-alert site, guarding on
`alert.alert_type == 'RED_ALERT'`:

- `adherence/service.py:703` (SOS) — beside the existing
  `publish_dashboard_event("alert.opened", ...)`.
- `adherence/service.py:524` (health-survey severe symptom) — this site has **no**
  dashboard publish today; add the caregiver dispatch after the transaction
  regardless. Capture the returned alert into a variable first (currently
  discarded).
- `agents/service.py:783` (missed-critical streak) — likewise capture the alert;
  currently discarded.

Imported lazily inside the function, matching `send_notification_task`'s existing
lazy-import pattern, to avoid a module-load-time dependency between `adherence`
and `caregivers`.

**N+1 in the review path:** `run_nightly_review` creates alerts inside a loop over
candidates. One task per alert there means one query pair per alert per night.
Instead, change `_persist_one`'s return from `bool` to
`tuple[bool, Optional[tuple[patient_id, alert_id, triggered_by_type]]]`, collect
the non-`None` entries across the whole loop, and call
`notify_caregivers_of_alert_batch` **once** after it — resolving all links in one
`IN`-list query joined to one batched name lookup. Two queries total regardless of
how many alerts fired.

#### 9b — `CG_REPORT`

A separate Beat task `caregivers.send_reports`, scheduled at
`adherence_review_patient_send_from + 1` (09:00 with defaults) — inside the
existing patient quiet-hours window and comfortably after `scan-adherence-review`
(05:00).

It is **not** folded into `run_nightly_review`, for a substantive reason: that
scan only writes `adherence_reviews` rows for patients that *breach* a threshold,
so a fully compliant patient has no row and their caregiver would never get the
weekly "everything is fine" number.

Drive from `caregiver_links`, never from patients — three queries total,
independent of how many links are due:

1. One claim statement selects and marks due links atomically, returning
   `(link_id, patient_id, telegram_chat_id)`.
2. One `IN`-list query resolves patient names from `patient_profiles`.
3. One scoped aggregate computes adherence for that id set: the same shape as
   `AdherenceIndicatorRepository.get_severity_indicators` but with
   `ScheduledDose.patient_id.in_(:ids)` added. The existing method deliberately
   scans the whole population — right for the nightly review, wrong here, since
   caregiver-linked patients are a small subset. The `IN`-list rides the
   window-scan index from migration `0024`.

Then call `queue_message` per link from already-materialized data. No further
queries.

**Race — double run.** Beat can double-fire and two workers can pick up the same
tick. Claim before sending, in one conditional UPDATE:

```sql
UPDATE caregiver_links
   SET last_report_sent_at = :now, last_message_sent_at = :now
 WHERE telegram_chat_id IS NOT NULL
   AND status = 'ACTIVE'
   AND (last_report_sent_at IS NULL OR last_report_sent_at < :report_cutoff)
RETURNING id, patient_id, telegram_chat_id
```

This is the claim idiom this codebase already uses — a conditional UPDATE whose
own `WHERE` *is* the claim, as in `AgentRunRepository.claim_run` and
`AdherenceLogRepository.apply_dose_action_cas`. **This repo has no
`FOR UPDATE SKIP LOCKED` anywhere; do not introduce it here.**

It is exclusive without explicit locking: a second worker running the identical
statement blocks on the row locks the first holds, and when the first commits,
Postgres re-evaluates the qual against the *new* row version (EvalPlanQual) —
`last_report_sent_at` is now current, the predicate no longer matches, and the
second claims zero rows. Whichever worker gets the rows is the one that sends.

The deterministic `idempotency_key` (`cg:{link_id}:CG_REPORT:{run_date}`) is the
second line of defence at the delivery layer, covering a worker that claims rows
then dies before enqueueing.

**No full scan:** the `WHERE` matches the partial index
`(last_report_sent_at) WHERE telegram_chat_id IS NOT NULL`. Confirm with
`EXPLAIN (ANALYZE, BUFFERS)` once there is realistic data.

Note there is no second keepalive pass, and therefore none of the Zalo design's
ordering hazard between two passes writing `last_message_sent_at` over
overlapping candidates.

#### 9c — `CG_ALERT_RESOLVED`

In `AlertService.resolve_alert`, after commit, beside the existing
`publish_dashboard_event("alert.updated", ...)`. Send only if a `CG_ALERT_RED`
delivery row exists for this `alert_id` — one indexed lookup on
`(caregiver_link_id, created_at)` filtered by `alert_id`. Never send a resolution
for an alert the caregiver never heard about.

---

### Stage 10 — Tests

**Files:** `tests/test_services/test_caregiver_telegram.py`,
`tests/test_api/test_caregiver_links.py`,
`tests/test_api/test_caregiver_webhook.py`.

Against `FakeTelegramClient`, no network:

- Template selection per `triggered_by_type`; patient name interpolated.
- `alert_type='WARNING'` and the adverse-event digest produce **no** caregiver
  message; `MISSED_DOSES` (severity `HIGH`, not `CRITICAL`) **does** — the
  precise case a severity-based predicate would have dropped.
- `SKIPPED_NO_BINDING` for an unbound link; a bound `ACTIVE` link sends.
- Idempotency: `queue_message` twice with the same key → one row, one send.
- Retry classification: `429` retries honouring `retry_after`; transient retries
  on the ladder; `403` marks the delivery `BLOCKED_BY_USER` **and** the link
  `BLOCKED` without retrying; `400` marks `FAILED` without retrying.
- A `BLOCKED` link is skipped by the next send, and a later inbound update from
  that chat restores it to `ACTIVE`.
- Claim concurrency: two `send_reports` passes over the same due set →
  exactly one delivery row per link (run both with `asyncio.gather`).
- Duplicate/out-of-order webhook updates do not move
  `telegram_last_interaction_at` backwards.
- Binding: correct code binds and clears `link_code`; replaying the same update
  does not double-bind; a wrong or missing `X-Telegram-Bot-Api-Secret-Token` is
  rejected `401` with no row touched.
- `/stop` sets links `INACTIVE`.
- Access removal: a former-caregiver phone cannot authenticate; an unrelated
  doctor gets an empty page on reviews/adherence/surveys/schedules and 404 on
  prescription detail and the PDF export.

**Baseline note:** `main` currently has pre-existing test failures unrelated to
this work (LLM/agent/eval suites needing credentials this environment lacks).
Before starting, capture a baseline run; after each stage, compare against it
rather than against green. Any *new* name in the failure list is a real
regression.

Postman: caregiver CRUD, plus a request that posts a correctly-signed webhook
body so binding is exercisable without a live bot.

---

## 4. Configuration for the real run

Two values from `@BotFather`, one you choose:

```bash
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=<from @BotFather /newbot>
TELEGRAM_BOT_USERNAME=<the bot's @username, without the @>
TELEGRAM_WEBHOOK_SECRET=<any random 32+ char string you generate>
```

Then register the webhook once:

```bash
curl -F "url=https://<your-host>/webhooks/telegram" \
     -F "secret_token=<TELEGRAM_WEBHOOK_SECRET>" \
     "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook"
```

The host must be HTTPS on port 443, 80, 88, or 8443. For local testing an ngrok
tunnel satisfies this. Getting the token needs nothing but a Telegram account —
no business, no verification, no waiting period.

Also restart the `worker` and `beat` containers so Celery picks up
`caregivers.tasks` and the new Beat entry.

---

## 5. Deferred, deliberately

- **Android client** — `CaregiverScreen.kt`, `PatientDtos.kt`, the outbox
  `CREATE_CAREGIVER`/`DELETE_CAREGIVER` payloads and three test files all
  reference the old DTO shape (`caregiver_user_id`, `temp_password`, `channels`)
  and will not match this backend. Backend-only scope, as before.
- **Two missing `alert.opened` publishes** (health-survey severe symptom,
  missed-dose streak). A real gap — the doctor dashboard has no realtime signal
  for either, and `schema.md` §8.3 claims otherwise — but out of scope here. This
  plan touches both call sites for the caregiver dispatch, so it is a two-line
  addition if wanted.
- **Rich message formatting** — Telegram supports Markdown/HTML and inline
  keyboards (e.g. an "I've seen this" button). Plain text only for now; the
  minimal-content decision from the Zalo design still holds.

---

## Appendix — lessons carried from the Zalo build

Concrete, verified failures from the previous implementation. They are
platform-independent and are pre-solved in the stages above rather than left to
be rediscovered.

1. **A partial index cannot become a named UNIQUE constraint.**
   `ADD CONSTRAINT ... UNIQUE USING INDEX` on a `WHERE`-qualified index raises
   `WrongObjectTypeError`. Leave it a plain unique index and use `drop_index` in
   the downgrade. (Stage 1.)
2. **`ON DELETE SET NULL` conflicts with an XOR CHECK the column participates
   in.** The FK's implicit UPDATE violates the CHECK on delete — an error raised
   from a statement you did not write. Use CASCADE. (Stage 2.)
3. **A migration and its ORM model are two separate edits.** `alembic upgrade
   head` succeeding proves nothing about the Python side; the mismatch surfaces
   as `TypeError: '<column>' is an invalid keyword argument` at the first insert.
   Only a live-DB test catches it. (Stage 3.)
4. **Check `VARCHAR` widths against your longest literal before writing it.**
   `SKIPPED_WINDOW_CLOSED` (21) into `VARCHAR(20)` is a runtime
   `StringDataRightTruncationError`, not a startup error. (Stage 2.)
5. **Pydantic v2 `validation_alias` silently drops the field name.** With an
   alias set and `populate_by_name` unset, passing the field's own name as a
   kwarg yields `None` rather than an error. (Stage 7.)
6. **The autobegin trap is real and recurs.** Any `SELECT` before an explicit
   `session.begin()` autobegins a transaction the explicit block then refuses.
   It bit both the webhook handler and the send task. (Stages 6 and 8.)
7. **Alembic revision ids must be ≤32 characters** — `alembic_version.version_num`
   is `VARCHAR(32)`, and with `autocommit_block()` in play the overflow fails
   *after* the DDL commits, leaving applied schema with no version stamp. Check
   `len()` before naming, not after running.
8. **Entering `autocommit_block()` commits the ambient transaction.** Anything
   that can fail should run before it, or a mid-migration failure leaves
   committed indexes behind a rolled-back version stamp.
9. **`docker exec` without `-i` does not attach stdin**, so a heredoc silently
   feeds nothing. Copy SQL into the container and use `psql -f`, and set
   `MSYS_NO_PATHCONV=1` on Git Bash so `docker cp` does not mangle the container
   path.
