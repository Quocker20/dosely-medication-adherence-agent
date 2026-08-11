# Slice 3 Plan — Doctor & Patient Clinical Management

## 0. Blockers found first (decide before code)

**B1. No doctor↔patient link exists in schema.** `database_v1_init.sql` has zero column tying a patient to a doctor. Only `prescriptions.doctor_id` (line 116) and `alerts.assigned_doctor_id` (line 202). But `GET /doctors/patients` = "patient roster of this doctor". Two options:

| Option | Roster query | Verdict |
|---|---|---|
| A. Add `patient_profiles.primary_doctor_id` FK | index scan one table | **recommend** |
| B. Derive from `prescriptions.doctor_id` | `DISTINCT` over prescriptions + join; new patient with no prescription invisible; table not built yet (Slice 5) | reject |

Take A. Matches progress line 2.3.2.1 "patient profile creation associated with a primary doctor".

**B2. Zero alembic migrations exist.** `alembic/versions/` empty — `users`, `doctor_profiles`, `audit_logs`, `refresh_tokens` live in models but no migration. DB currently built from raw `database_v1_init.sql`. Must fix before Slice 3 migration, else autogenerate emits CREATE for all existing tables. Fix: generate baseline `0001_baseline` from current models, `alembic stamp 0001` on the live DB, then Slice 3 migration stacks on it.

**B3. Phone collision policy.** Doctor creates patient with phone already registered (as CAREGIVER or another patient). v1 = reject `409`. No auto-link, no role upgrade. Explicit.

---

## 1. Files

```
src/modules/patients/           NEW
  __init__.py  models.py  schemas.py  repository.py  service.py  router.py
src/modules/prescriptions/      NEW (Medication only this slice)
  __init__.py  models.py  schemas.py  repository.py  service.py  router.py
alembic/versions/
  0001_baseline.py              (stamp only)
  0002_slice3_patients_medications.py
src/api/v1_router.py            EDIT (+2 routers)
tests/test_api/test_patients.py, test_medications.py   NEW
```

`Medication` goes in `prescriptions` module per `schema.md` §5.1 module path.

---

## 2. Models

### `PatientProfile` (`patients/models.py`)
Mirrors SQL lines 29–39 **plus** `primary_doctor_id`.

```python
user_id: PK, FK users.id ON DELETE CASCADE
primary_doctor_id: FK doctor_profiles.user_id ON DELETE SET NULL, nullable
name: String(255) NOT NULL
dob: Date | None
sex: String(20) | None
timezone: String(50) NOT NULL default 'Asia/Ho_Chi_Minh'
privacy_consent_status: String(20) | None
emergency_note: Text | None
created_at / updated_at: TIMESTAMPTZ, updated_at onupdate=NOW()
user: relationship(lazy="raise")
doctor: relationship(lazy="raise")
```

`lazy="raise"` on both — same as `AuditLog.actor`. Any accidental attribute access raises instead of silently firing N+1.

### `Medication` (`prescriptions/models.py`)
Mirrors SQL lines 84–98 exactly, no new columns.

---

## 3. Constraints (none exist today for these tables)

All in migration `0002`, all named explicitly so `IntegrityError.orig.constraint_name` is matchable in service (same pattern `AdminService.create_doctor` uses at service.py:102).

**patient_profiles**
| Name | Definition | Why |
|---|---|---|
| `ck_patient_profiles_sex` | `sex IS NULL OR sex IN ('MALE','FEMALE','OTHER')` | schema.md §3.1 enum; no enum type in DB |
| `ck_patient_profiles_consent` | `privacy_consent_status IS NULL OR IN ('PENDING','GRANTED','REVOKED')` | PHI gate |
| `ck_patient_profiles_name_not_blank` | `length(btrim(name)) > 0` | blocks whitespace name |
| `ck_patient_profiles_dob_sane` | `dob IS NULL OR (dob > DATE '1900-01-01' AND dob <= CURRENT_DATE)` | future DOB breaks dosing logic downstream |
| `ck_patient_profiles_tz_not_blank` | `length(btrim(timezone)) > 0` | scheduler (Slice 6) reads this |
| `fk_patient_profiles_primary_doctor` | FK → `doctor_profiles(user_id)` ON DELETE SET NULL | roster integrity, doctor delete must not orphan-delete PHI |

**medications**
| Name | Definition | Why |
|---|---|---|
| `uq_medications_source_record` | `UNIQUE (source_name, source_record_key) WHERE source_record_key IS NOT NULL` | idempotent re-ingest of drug dictionary; partial so NULL keys allowed |
| `ck_medications_name_not_blank` | `length(btrim(name)) > 0` | |
| `ck_medications_source_not_blank` | `length(btrim(source_name)) > 0` | citation traceability for RAG (Slice 8) |

**users** (gap, cheap to close here)
`ck_users_role` `role IN ('PATIENT','DOCTOR','ADMIN','CAREGIVER')`, `ck_users_status` `status IN ('ACTIVE','INACTIVE','BLOCKED')`. Prevents a typo'd role silently bypassing `require_roles`.

Validate-first pattern for the users checks on a live DB: `ADD CONSTRAINT ... NOT VALID` then `VALIDATE CONSTRAINT` — avoids long ACCESS EXCLUSIVE lock.

---

## 4. Indexes + query strategy

Current state: **zero** indexes on `patient_profiles`, **zero** on `medications`. Every listed query today = seq scan.

### 4.1 Roster — `GET /doctors/patients`
```sql
CREATE INDEX idx_patient_profiles_doctor_created
  ON patient_profiles (primary_doctor_id, created_at DESC);
```
Serves `WHERE primary_doctor_id = :me ORDER BY created_at DESC` with zero sort node. Leading col is the mandatory RBAC predicate so it is always usable.

### 4.2 Search — the real trap
`search` param uses `ILIKE '%term%'` (admin repo does this at repository.py:74). Leading wildcard = **btree unusable = full seq scan on PHI table**. Fix with trigram GIN:
```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_patient_profiles_name_trgm ON patient_profiles USING gin (name gin_trgm_ops);
CREATE INDEX idx_users_phone_trgm          ON users USING gin (phone gin_trgm_ops);
CREATE INDEX idx_medications_name_trgm     ON medications USING gin (name gin_trgm_ops);
```
Enforce `min_length=2` on `search` at the Query param — trigram index cannot serve a 1-char pattern, planner falls back to seq scan. Reject early instead.

Note: `idx_users_phone_trgm` also retro-fixes the existing `GET /admin/doctors?search=` seq scan.

### 4.3 Medication catalog — `GET /medications`
```sql
CREATE INDEX idx_medications_active_name ON medications (name, id) WHERE is_active;
```
Partial (catalog is mostly-active, index stays small), and `(name, id)` gives a deterministic total order — plain `ORDER BY name` with dup names makes rows skip/repeat across pages under OFFSET.

### 4.4 Pagination cost
Contract mandates `total_elements`, so keep the `func.count().over()` single-query trick from `DoctorRepository.list_doctors` — it avoids a second COUNT round trip. But the window still materializes every matched row. Two guards:
- Cap `size` at 100 (existing) **and** cap `page` (`le=1000`) — deep OFFSET reads and discards `page*size` rows.
- Medications unfiltered count is a constant across all users: cache `total_elements` in Redis (`med:count:active`, TTL 300s, `src/core/redis.py` already wired) and skip the window when no filter is applied.

### 4.5 Explicit non-goals
No `SELECT *` — column lists only. No `.all()` without `.limit()`. No ORM `relationship` traversal in response building.

---

## 5. Race conditions

| Race | Handling |
|---|---|
| Two doctors POST same patient phone concurrently | **No pre-check SELECT.** Insert and catch `IntegrityError` on `users_phone_key` → `409`. A `get_user_by_phone`-then-insert is TOCTOU and will double-insert under concurrency. Same reasoning as service.py:62. |
| Patient user row created, profile insert fails | Both inside one `async with self._db.begin():` → atomic, no orphan `users` row with no profile. |
| Doctor deactivated between token issue and patient create | FK `primary_doctor_id` only proves the row exists, not that it's ACTIVE. Add explicit doctor-status read inside the txn before insert. Residual risk: an already-issued access token stays valid until expiry (deactivate only revokes refresh tokens, service.py:315). Acceptable given short access TTL — flagging, not fixing, this slice. |
| Concurrent profile update lost-update | `SELECT ... FOR UPDATE` on the profile row inside the txn (matches `get_doctor_with_user(for_update=True)`). Not needed for this slice's read-only endpoints; the helper gets built now for Slice 4. |
| Duplicate medication ingest | `uq_medications_source_record` + `ON CONFLICT DO NOTHING` on the seeder. |

`ON DELETE CASCADE` from `users` to `patient_profiles` stays — but do **not** expose any hard-delete endpoint; deactivation is status-flip only, like `deactivate_doctor`.

---

## 6. Repository API (statement-only, no commit/rollback)

`PatientRepository`
- `create_patient_profile(user_id, primary_doctor_id, name, dob, sex, timezone, emergency_note) -> PatientProfile` — `add` + `flush`
- `get_patient_with_user(user_id, for_update=False) -> tuple[PatientProfile, User] | None` — one JOIN, no lazy load
- `list_patients_for_doctor(doctor_id | None, page, size, search) -> (rows, total)` — one JOIN + `count().over()`; `doctor_id=None` means ADMIN scope

`MedicationRepository`
- `list_medications(page, size, search, active_only=True)`
- `get_medication_by_id(id)`

---

## 7. Service + RBAC

`PatientService.create_patient(request, doctor_payload, ip)`
1. `validate_phone_number` (reuse `core.security`)
2. one txn: `create_user(role="PATIENT")` → `create_patient_profile(primary_doctor_id=doctor)` → `create_audit_log("CREATE_PATIENT","PATIENT_PROFILE")`
3. `IntegrityError` → map constraint name → 409
4. return `PatientDetailResponse` + `temp_password` (patient logs in by PIN too — same `_generate_temp_pin` flow as doctors; `is_first_login=True` already default)

**Access scoping is a WHERE clause, never a post-fetch filter** — never load PHI then discard it:
- `DOCTOR` → `primary_doctor_id = self`; miss → `404` (not `403`; a `403` leaks that the patient ID exists)
- `ADMIN` → unscoped

`MedicationService` — any authenticated role, `is_active` default true.

---

## 8. Endpoints

| Endpoint | Roles | Notes |
|---|---|---|
| `POST /doctors/patients` | DOCTOR | 201, returns detail + temp PIN |
| `GET /doctors/patients` | DOCTOR | page/size/search, scoped |
| `GET /doctors/patients/{id}` | DOCTOR/ADMIN | scoped, 404 on out-of-scope |
| `GET /medications` | any auth | page/size/search |
| `GET /medications/{id}` | any auth | |

All return `success_response(...)` envelope; routers parse/delegate only.

---

## 9. Verification

- `EXPLAIN (ANALYZE, BUFFERS)` each of the 5 queries after seeding ~10k patients / ~5k medications. Assert no `Seq Scan` on `patient_profiles` or `medications`, no `Sort` node on the roster query.
- Tests: RBAC cross-doctor isolation (doctor A cannot read doctor B's patient), duplicate-phone → 409, each CHECK constraint rejection, pagination boundary (`page` past last → empty + correct `total_elements`), and an N+1 guard test asserting `lazy="raise"` fires on relationship access.

---

## 10. Order of work

1. `0001_baseline` + `alembic stamp` (B2 — blocks everything)
2. models → `0002` migration (constraints + indexes + extension)
3. repositories → services → routers → `v1_router`
4. medication seeder (`ON CONFLICT DO NOTHING`)
5. EXPLAIN pass + tests
6. tick progress.md 2.3.x

---

Sign-off needed before start: **B1** (add `primary_doctor_id` to `patient_profiles` — schema change beyond `database_v1_init.sql`) and **B2** (baseline+stamp strategy, must match how live DB was actually provisioned). CLAUDE.md forbids models/migrations without explicit confirmation.
