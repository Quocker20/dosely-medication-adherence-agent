-- =============================================================================
-- PostgreSQL Database Schema (24 Tables)
-- =============================================================================

-- Enable extension cho UUID
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- Trigram search (phone/name partial-match lookups). Added by migration 0002_slice3.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Generic updated_at maintenance. Fires on any UPDATE (plain or INSERT ...
-- ON CONFLICT DO UPDATE), ORM-issued or raw SQL alike -- attach it per table
-- instead of trusting every writer to set updated_at by hand. NOT attached to
-- users: its last_login_at write (see refresh_tokens / auth flows) is a login
-- event, not a profile edit, and must not bump updated_at.
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- 1. Identity & Access
-- =============================================================================

-- 1. users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role VARCHAR(30) NOT NULL
        CONSTRAINT ck_users_role CHECK (role IN ('PATIENT','DOCTOR','ADMIN','CAREGIVER')),
    phone VARCHAR(20) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    need_onboarding BOOLEAN NOT NULL DEFAULT TRUE,
    password_changed_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL
        CONSTRAINT ck_users_status CHECK (status IN ('ACTIVE','INACTIVE','BLOCKED')),
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for users table optimization (Login & Auth)
CREATE INDEX idx_users_phone_status ON users(phone, status);
-- Partial-match phone search. Added by migration 0002_slice3.
CREATE INDEX idx_users_phone_trgm ON users USING gin (phone gin_trgm_ops);

-- 2. patient_profiles
CREATE TABLE patient_profiles (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL
        CONSTRAINT ck_patient_profiles_name_not_blank CHECK (length(btrim(name)) > 0),
    dob DATE
        CONSTRAINT ck_patient_profiles_dob_sane
        CHECK (dob IS NULL OR (dob > DATE '1900-01-01' AND dob <= CURRENT_DATE)),
    sex VARCHAR(20)
        CONSTRAINT ck_patient_profiles_sex CHECK (sex IS NULL OR sex IN ('MALE','FEMALE','OTHER')),
    timezone VARCHAR(50) NOT NULL
        CONSTRAINT ck_patient_profiles_tz_not_blank CHECK (length(btrim(timezone)) > 0),
    privacy_consent_status VARCHAR(20)
        CONSTRAINT ck_patient_profiles_consent
        CHECK (privacy_consent_status IS NULL OR privacy_consent_status IN ('PENDING','GRANTED','REVOKED')),
    emergency_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_patient_profiles_set_updated_at
    BEFORE UPDATE ON patient_profiles
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- list_patients orders by created_at DESC with OFFSET/LIMIT. Added by migration 0003_access_idx.
CREATE INDEX idx_patient_profiles_created_at ON patient_profiles(created_at DESC);
-- Partial-match name search. Added by migration 0002_slice3.
CREATE INDEX idx_patient_profiles_name_trgm ON patient_profiles USING gin (name gin_trgm_ops);

-- 3. doctor_profiles
-- license_no carries two UNIQUE constraints on the live DB: the inline column
-- UNIQUE below (auto-named doctor_profiles_license_no_key) plus the explicit
-- uq_doctor_profiles_license_no further down -- a pre-existing redundancy from
-- before this file was last cleaned up, not introduced by any migration.
-- Functionally harmless (both enforce the same rule); kept here only to match
-- the live schema exactly. Candidate for a future migration to drop one.
CREATE TABLE doctor_profiles (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    license_no VARCHAR(100) NOT NULL UNIQUE,
    specialty VARCHAR(150),
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_doctor_profiles_license_no UNIQUE (license_no)
);

-- Index for list_doctors pagination
CREATE INDEX idx_doctor_profiles_created_at ON doctor_profiles(created_at DESC);

-- 4. caregiver_links
CREATE TABLE caregiver_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patient_profiles(user_id) ON DELETE CASCADE,
    caregiver_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    relationship VARCHAR(50),
    channels JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_caregiver_links_patient_caregiver UNIQUE (patient_id, caregiver_user_id)
);

-- 5. refresh_tokens
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    device_info TEXT,
    ip_address INET,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for refresh_tokens optimization (Change Password & Logout)
CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id);

-- 6. user_devices (For FCM Tokens)
CREATE TABLE user_devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    fcm_token VARCHAR(255) NOT NULL UNIQUE,
    device_name VARCHAR(100),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_user_devices_user_active ON user_devices(user_id, is_active);
CREATE INDEX idx_refresh_tokens_user_active ON refresh_tokens(user_id) WHERE revoked_at IS NULL;
CREATE INDEX idx_refresh_tokens_active_hash ON refresh_tokens(token_hash) WHERE revoked_at IS NULL;


-- =============================================================================
-- 2. Prescriptions & Medication Management
-- =============================================================================

-- 5. medications
CREATE TABLE medications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL
        CONSTRAINT ck_medications_name_not_blank CHECK (length(btrim(name)) > 0),
    composition TEXT,
    manufacturer VARCHAR(255),
    uses TEXT,
    side_effects TEXT,
    image_url TEXT,
    source_name VARCHAR(100) NOT NULL
        CONSTRAINT ck_medications_source_not_blank CHECK (length(btrim(source_name)) > 0),
    source_ref TEXT,
    source_record_key VARCHAR(255),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Added by migration 0002_slice3.
-- De-dupes catalog rows synced from the same external source record.
CREATE UNIQUE INDEX uq_medications_source_record
    ON medications(source_name, source_record_key) WHERE source_record_key IS NOT NULL;
-- Backs the active-catalog listing/search, index-only on (name, id).
CREATE INDEX idx_medications_active_name ON medications(name, id) WHERE is_active;
-- Partial-match name search.
CREATE INDEX idx_medications_name_trgm ON medications USING gin (name gin_trgm_ops);

-- 6. patient_routines
CREATE TABLE patient_routines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL UNIQUE REFERENCES patient_profiles(user_id) ON DELETE CASCADE,
    wake_time TIME,
    breakfast_time TIME,
    lunch_time TIME,
    dinner_time TIME,
    sleep_time TIME,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_patient_routines_set_updated_at
    BEFORE UPDATE ON patient_routines
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 7. prescriptions
CREATE TABLE prescriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patient_profiles(user_id) ON DELETE CASCADE,
    doctor_id UUID REFERENCES doctor_profiles(user_id) ON DELETE SET NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT'
        CONSTRAINT ck_prescriptions_status CHECK (status IN ('DRAFT','APPROVED','CANCELLED')),
    diagnosis_note TEXT,
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- list_patients(doctor_id) / get_patient roster access resolve through
-- EXISTS (doctor_id = ? AND patient_id = ?); carrying patient_id in the index
-- turns that probe into an index-only scan. Supersedes the single-column
-- idx_prescriptions_doctor_id (dropped). Added by migration 0003_access_idx.
CREATE INDEX idx_prescriptions_doctor_patient ON prescriptions(doctor_id, patient_id);
-- Slice 5: GET /patients/{patient_id}/prescriptions filters patient_id,
-- orders by created_at DESC, paginates. Added by migration 0006_slice5_idx.
CREATE INDEX idx_prescriptions_patient_created ON prescriptions(patient_id, created_at DESC);

-- 8. prescription_items
-- medication_id carries no FK: display_name is a frozen snapshot of
-- Medication.name taken at write time, so an item must survive the
-- referenced medications row being edited or deleted. FK dropped by
-- migration 0007_drop_pi_med_fk.
CREATE TABLE prescription_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prescription_id UUID NOT NULL REFERENCES prescriptions(id) ON DELETE CASCADE,
    medication_id UUID,
    display_name VARCHAR(255) NOT NULL,
    dose_unit VARCHAR(30) NOT NULL,
    morning_dose NUMERIC(10,3),
    noon_dose NUMERIC(10,3),
    evening_dose NUMERIC(10,3),
    bedtime_dose NUMERIC(10,3),
    route VARCHAR(30) NOT NULL DEFAULT 'ORAL',
    meal_relation VARCHAR(30),
    minimum_interval_minutes INTEGER,
    start_date DATE NOT NULL,
    end_date DATE,
    instructions TEXT,
    -- Doctor-set on high-risk medications; narrows the missed-dose-streak
    -- fast-path alert to only these items instead of every medication.
    -- Snapshotted onto scheduled_doses.is_critical at generation time.
    -- Added by migration 0021_prescription_item_is_critical.
    is_critical BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Postgres never auto-indexes a FK column. Backs item lookups by prescription
-- (single and batched IN-clause) and the ON DELETE CASCADE from prescriptions.
-- Added by migration 0006_slice5_idx.
CREATE INDEX idx_prescription_items_prescription_id ON prescription_items(prescription_id);

-- 9. scheduled_doses
CREATE TABLE scheduled_doses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prescription_item_id UUID NOT NULL REFERENCES prescription_items(id) ON DELETE CASCADE,
    patient_id UUID NOT NULL REFERENCES patient_profiles(user_id) ON DELETE CASCADE,
    original_scheduled_at TIMESTAMPTZ NOT NULL,
    current_scheduled_at TIMESTAMPTZ NOT NULL,
    -- Generation-time snapshot used by patient clients. Nullable only for
    -- schedules created before migration 0011.
    dose_slot VARCHAR(20)
        CONSTRAINT ck_scheduled_doses_dose_slot
        CHECK (dose_slot IS NULL OR dose_slot IN ('MORNING','NOON','EVENING','BEDTIME')),
    medication_id UUID,
    dose_value NUMERIC(10,3)
        CONSTRAINT ck_scheduled_doses_dose_value CHECK (dose_value IS NULL OR dose_value > 0),
    dose_unit VARCHAR(30),
    meal_relation VARCHAR(30)
        CONSTRAINT ck_scheduled_doses_meal_relation
        CHECK (meal_relation IS NULL OR meal_relation IN ('BEFORE_MEAL','AFTER_MEAL','WITH_MEAL')),
    -- Groups sibling doses into one consolidated push notification /
    -- synchronized snooze. NULL for ungrouped doses and rows generated
    -- before migration 0013_dose_notify_group.
    notification_group_id UUID,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING','TAKEN','SKIPPED','MISSED')),
    snooze_count INTEGER NOT NULL DEFAULT 0 CHECK (snooze_count >= 0),
    -- Immutable snapshot of PrescriptionItem.is_critical at generation time,
    -- same pattern as dose_slot/medication_id/dose_value above -- cannot
    -- drift from the item since items are DRAFT-locked once doses exist.
    -- Added by migration 0021_prescription_item_is_critical.
    is_critical BOOLEAN NOT NULL DEFAULT FALSE,
    taken_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_scheduled_doses_taken_at CHECK (status <> 'TAKEN' OR taken_at IS NOT NULL)
);

CREATE TRIGGER trg_scheduled_doses_set_updated_at
    BEFORE UPDATE ON scheduled_doses
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Idempotency for schedule generation: a re-run (retry, duplicate Celery
-- delivery) can ON CONFLICT DO NOTHING per (item, original time) instead of
-- duplicating rows. Leading column also serves ON DELETE CASCADE from
-- prescription_items. Added by migration 0008_slice6_sched.
CREATE UNIQUE INDEX uq_scheduled_doses_item_original
    ON scheduled_doses(prescription_item_id, original_scheduled_at);
-- GET /patients/{id}/schedules?date=... filters patient + time range, orders
-- by time; also backs the reschedule delete predicate and ON DELETE CASCADE
-- from patient_profiles. Added by migration 0008_slice6_sched.
CREATE INDEX idx_scheduled_doses_patient_time
    ON scheduled_doses(patient_id, current_scheduled_at);
-- Partial index for the cross-patient "doses due soon" notification scan.
-- Added by migration 0008_slice6_sched.
CREATE INDEX idx_scheduled_doses_pending_due
    ON scheduled_doses(current_scheduled_at) WHERE status = 'PENDING';
-- Backs the narrowed missed-dose-streak fast-path scan: most recent doses
-- per patient that are flagged critical. Stays proportional to actual
-- doctor usage of is_critical rather than table size (partial on it).
-- Added by migration 0021_prescription_item_is_critical.
CREATE INDEX idx_scheduled_doses_critical_patient_time
    ON scheduled_doses(patient_id, current_scheduled_at DESC) WHERE is_critical;
-- Backs the nightly graded-adherence-review scan, which ranges across every
-- patient at once (unlike idx_scheduled_doses_patient_time, which leads with
-- patient_id and cannot serve a patient-agnostic time range). INCLUDE keeps
-- the six aggregate queries index-only. Added by migration
-- 0024_scheduled_doses_window_scan_index.
CREATE INDEX idx_scheduled_doses_window_scan
    ON scheduled_doses(current_scheduled_at, patient_id, status)
    INCLUDE (dose_slot, medication_id, is_critical, snooze_count,
             original_scheduled_at, taken_at);

-- 10. adherence_logs
CREATE TABLE adherence_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scheduled_dose_id UUID REFERENCES scheduled_doses(id) ON DELETE CASCADE,
    patient_id UUID NOT NULL REFERENCES patient_profiles(user_id) ON DELETE CASCADE,
    action VARCHAR(20) NOT NULL
        CONSTRAINT ck_adherence_logs_action CHECK (action IN ('TAKEN','SNOOZE','SKIPPED')),
    performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    action_source VARCHAR(30) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    idempotency_key VARCHAR(100) UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Postgres never auto-indexes a FK column. Backs ON DELETE CASCADE from
-- scheduled_doses. Added by migration 0009_slice7_adherence.
CREATE INDEX idx_adherence_logs_scheduled_dose_id ON adherence_logs(scheduled_dose_id);
-- GET /patients/{patient_id}/adherence(/logs)?from&to filters patient_id +
-- performed_at range, orders by performed_at DESC. Also backs ON DELETE
-- CASCADE from patient_profiles. Added by migration 0009_slice7_adherence.
CREATE INDEX idx_adherence_logs_patient_performed
    ON adherence_logs(patient_id, performed_at DESC);


-- =============================================================================
-- 3. Health & Monitoring (Surveys, Symptoms, Alerts)
-- =============================================================================

-- 11. health_surveys
CREATE TABLE health_surveys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patient_profiles(user_id) ON DELETE CASCADE,
    survey_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL,
    answers_json JSONB NOT NULL,
    submitted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- One survey per patient per day. Closes the double-submit race in
    -- HealthSurveyService.submit_health_survey at the DB layer (a
    -- check-then-insert in the service can't do this atomically). Added by
    -- migration 0018_health_survey_query_indexes, after deduping any
    -- pre-existing duplicate rows.
    CONSTRAINT uq_health_surveys_patient_date UNIQUE (patient_id, survey_date)
);

-- Dashboard's last_survey_date (DashboardPatientListResponse) needs
-- MAX(survey_date) per patient; also backs ON DELETE CASCADE from
-- patient_profiles. Added by migration 0009_slice7_adherence.
CREATE INDEX idx_health_surveys_patient_date
    ON health_surveys(patient_id, survey_date DESC);
-- GET /health-surveys (DOCTOR/ADMIN, platform-wide) filters survey_date
-- range and orders newest-first; the (patient_id, ...) index above doesn't
-- help an unscoped list. Added by migration 0018_health_survey_query_indexes.
CREATE INDEX idx_health_surveys_date_id
    ON health_surveys(survey_date DESC, id DESC);

-- 12. symptom_reports
CREATE TABLE symptom_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patient_profiles(user_id) ON DELETE CASCADE,
    survey_id UUID REFERENCES health_surveys(id) ON DELETE SET NULL,
    symptom_code VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL
        CONSTRAINT ck_symptom_reports_severity CHECK (severity IN ('MILD','MODERATE','SEVERE')),
    description TEXT,
    reported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source VARCHAR(20) NOT NULL
);

-- Postgres never auto-indexes a FK column. Backs ON DELETE CASCADE from
-- patient_profiles and per-patient symptom history lookups. Added by
-- migration 0009_slice7_adherence.
CREATE INDEX idx_symptom_reports_patient_reported
    ON symptom_reports(patient_id, reported_at DESC);
-- Backs ON DELETE SET NULL from health_surveys (fetching a survey's
-- symptom_reports). Added by migration 0009_slice7_adherence.
CREATE INDEX idx_symptom_reports_survey_id ON symptom_reports(survey_id);
-- GET /health-surveys?severity= semi-joins this table by severity; without
-- this it's a seq scan. Added by migration 0018_health_survey_query_indexes.
CREATE INDEX idx_symptom_reports_severity_survey
    ON symptom_reports(severity, survey_id);

-- 13. alerts
CREATE TABLE alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patient_profiles(user_id) ON DELETE CASCADE,
    assigned_doctor_id UUID REFERENCES doctor_profiles(user_id) ON DELETE SET NULL,
    -- ADHERENCE_REVIEW added by migration 0023_alerts_adherence_review_trigger
    -- for DOCTOR_WARNING/DOCTOR_ALERT rows raised by the nightly
    -- graded-severity review.
    triggered_by_type VARCHAR(30) NOT NULL
        CONSTRAINT ck_alerts_triggered_by_type
        CHECK (triggered_by_type IN
            ('SOS_BUTTON','SEVERE_SYMPTOM','MISSED_DOSES','ADHERENCE_REVIEW')),
    triggered_by_id UUID,
    alert_type VARCHAR(30) NOT NULL
        CONSTRAINT ck_alerts_alert_type CHECK (alert_type IN ('RED_ALERT','WARNING')),
    severity VARCHAR(20) NOT NULL
        CONSTRAINT ck_alerts_severity CHECK (severity IN ('CRITICAL','HIGH','MEDIUM')),
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN'
        CONSTRAINT ck_alerts_status CHECK (status IN ('OPEN','ACKNOWLEDGED','RESOLVED')),
    message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Header-supplied Idempotency-Key (POST /patients/{id}/sos): a
    -- retried/duplicate-delivered SOS tap must not page a doctor with two
    -- CRITICAL alerts. Multiple NULLs are allowed under UNIQUE (non-SOS
    -- alert sources leave this NULL). Added by migration 0010_slice7_alert_idem.
    idempotency_key VARCHAR(100) UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_alerts_set_updated_at
    BEFORE UPDATE ON alerts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- GET /patients/{patient_id}/sos and cascade delete from patient_profiles.
-- Added by migration 0009_slice7_adherence.
CREATE INDEX idx_alerts_patient_created ON alerts(patient_id, created_at DESC);
-- GET /alerts?status=&patientId= doctor dashboard list, ordered by recency.
-- Added by migration 0009_slice7_adherence.
CREATE INDEX idx_alerts_status_created ON alerts(status, created_at DESC);
-- Postgres never auto-indexes a FK column; backs ON DELETE SET NULL from
-- doctor_profiles. Added by migration 0009_slice7_adherence.
CREATE INDEX idx_alerts_assigned_doctor_id ON alerts(assigned_doctor_id);

-- 13a. adherence_reviews
-- One row per patient per night, written ONLY when severity is not NONE (an
-- adherent patient generates no row -- storing one for every patient every
-- night would add ~365 rows/patient/year that are never read). Rules decide
-- `severity` deterministically; the LLM only ever classifies `remedy_class`
-- from a closed list and cannot revise severity. Added by migration
-- 0022_adherence_reviews.
CREATE TABLE adherence_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patient_profiles(user_id) ON DELETE CASCADE,
    review_date DATE NOT NULL,
    window_start DATE NOT NULL,
    window_end DATE NOT NULL,

    severity VARCHAR(20) NOT NULL
        CONSTRAINT ck_adherence_reviews_severity
        CHECK (severity IN ('MILD','MODERATE','SEVERE')),
    -- Running counter carried forward from the prior night's row (reset to 1
    -- on any severity change, or on a gap in review history) -- NOT
    -- recomputed by counting rows, so a skipped nightly run degrades the
    -- escalation ladder instead of corrupting it.
    days_in_severity INTEGER NOT NULL DEFAULT 1
        CONSTRAINT ck_adherence_reviews_days CHECK (days_in_severity >= 1),

    remedy_class VARCHAR(40)
        CONSTRAINT ck_adherence_reviews_remedy
        CHECK (remedy_class IS NULL OR remedy_class IN (
            'RESCHEDULE_TIMING','SUSPECTED_SIDE_EFFECT','DELIBERATE_REFUSAL',
            'DISENGAGEMENT','EXTERNAL_DISRUPTION','UNCLEAR')),

    action_taken VARCHAR(30) NOT NULL
        CONSTRAINT ck_adherence_reviews_action
        CHECK (action_taken IN
            ('NONE','PATIENT_NOTIFICATION','DOCTOR_WARNING','DOCTOR_ALERT')),

    -- The exact numbers that produced `severity`, frozen for audit -- an
    -- alert must be reconstructable even after later dose actions change the
    -- underlying scheduled_doses rows.
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

-- Idempotency guard AND the primary defense against a double-fired nightly
-- job writing two alerts for one patient on one night: the service inserts
-- this row before any Alert/NotificationDelivery, so a concurrent second run
-- collides here first. Added by migration 0022_adherence_reviews.
CREATE UNIQUE INDEX uq_adherence_reviews_patient_date
    ON adherence_reviews(patient_id, review_date);
-- Escalation lookup: "the most recent review for each of these patients",
-- fetched as one DISTINCT ON query for the whole nightly batch rather than
-- one query per patient. Added by migration 0022_adherence_reviews.
CREATE INDEX idx_adherence_reviews_patient_date_desc
    ON adherence_reviews(patient_id, review_date DESC);


-- =============================================================================
-- 4. OCR & RAG Knowledge Base
-- =============================================================================

-- 14. ocr_jobs
CREATE TABLE ocr_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patient_profiles(user_id) ON DELETE CASCADE,
    image_object_key TEXT NOT NULL,
    engine VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    raw_text TEXT,
    normalized_text TEXT,
    confidence NUMERIC(5,4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 15. knowledge_documents
CREATE TABLE knowledge_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name VARCHAR(100) NOT NULL,
    source_ref TEXT NOT NULL,
    title VARCHAR(500),
    version VARCHAR(50),
    published_at DATE,
    checksum VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL
);

-- 16. knowledge_chunks
CREATE TABLE knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    medication_id UUID REFERENCES medications(id) ON DELETE SET NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding_ref TEXT,
    metadata JSONB
);

-- 17. rag_queries
CREATE TABLE rag_queries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID REFERENCES patient_profiles(user_id) ON DELETE SET NULL,
    ocr_job_id UUID REFERENCES ocr_jobs(id) ON DELETE SET NULL,
    query_text TEXT NOT NULL,
    answer_text TEXT,
    status VARCHAR(20) NOT NULL,
    model_version VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 18. rag_citations
CREATE TABLE rag_citations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rag_query_id UUID NOT NULL REFERENCES rag_queries(id) ON DELETE CASCADE,
    chunk_id UUID NOT NULL REFERENCES knowledge_chunks(id) ON DELETE CASCADE,
    rank SMALLINT NOT NULL,
    score NUMERIC(8,6)
);


-- =============================================================================
-- 5. AI Agent Runs
-- =============================================================================

-- 19. agent_runs
CREATE TABLE agent_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_type VARCHAR(30) NOT NULL
        CONSTRAINT ck_agent_runs_agent_type
        CHECK (agent_type IN ('PLANNING_AGENT','RESCHEDULING_AGENT')),
    patient_id UUID NOT NULL REFERENCES patient_profiles(user_id) ON DELETE CASCADE,
    prescription_id UUID REFERENCES prescriptions(id) ON DELETE SET NULL,
    trigger_type VARCHAR(30) NOT NULL
        CONSTRAINT ck_agent_runs_trigger_type
        CHECK (trigger_type IN ('PRESCRIPTION_APPROVED','ROUTINE_UPDATED','MANUAL')),
    model_version VARCHAR(100),
    graph_version VARCHAR(50) NOT NULL,
    -- NEEDS_REVIEW added by migration 0012_agent_review: lets a deterministic
    -- planning conflict finish without forcing a hard FAILED.
    status VARCHAR(20) NOT NULL
        CONSTRAINT ck_agent_runs_status CHECK (status IN ('RUNNING','COMPLETED','FAILED','NEEDS_REVIEW')),
    latency_ms INTEGER
        CONSTRAINT ck_agent_runs_latency CHECK (latency_ms IS NULL OR latency_ms >= 0),
    error_code VARCHAR(100),
    -- Lý do dừng ở dạng đọc được, thêm bởi migration 0017_agent_run_error_message.
    -- error_code chỉ giữ tên class exception nên không đủ để bác sĩ biết sửa gì.
    error_message TEXT,
    generated_dose_count INTEGER
        CONSTRAINT ck_agent_runs_dose_count CHECK (generated_dose_count IS NULL OR generated_dose_count >= 0),
    -- Structured Planning Agent audit fields. Added by migration
    -- 0014_planning_audit.
    prompt_version VARCHAR(50),
    input_hash VARCHAR(64),
    output_hash VARCHAR(64),
    candidate_source VARCHAR(64),
    -- Atomic worker claim for exactly-once pickup. Added by migration
    -- 0015_agent_run_claim.
    started_at TIMESTAMPTZ,
    claim_token UUID,
    claim_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Latest-run-for-patient / dashboard history; ON DELETE CASCADE from
-- patient_profiles. Added by migration 0008_slice6_sched.
CREATE INDEX idx_agent_runs_patient_created ON agent_runs(patient_id, created_at DESC);
-- Postgres never auto-indexes a FK column; backs ON DELETE SET NULL from
-- prescriptions. Added by migration 0008_slice6_sched.
CREATE INDEX idx_agent_runs_prescription_id ON agent_runs(prescription_id);
-- Enforces one in-flight run per patient at the DB layer: a second
-- concurrent generate/reschedule call fails the INSERT with IntegrityError,
-- which the service turns into 409 Conflict. Added by migration
-- 0008_slice6_sched.
CREATE UNIQUE INDEX uq_agent_runs_one_running
    ON agent_runs(patient_id) WHERE status = 'RUNNING';


-- =============================================================================
-- 6. Notification
-- =============================================================================

-- 20. notification_deliveries
CREATE TABLE notification_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scheduled_dose_id UUID REFERENCES scheduled_doses(id) ON DELETE SET NULL,
    alert_id UUID REFERENCES alerts(id) ON DELETE SET NULL,
    recipient_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel VARCHAR(20) NOT NULL,
    template_code VARCHAR(50) NOT NULL,
    title VARCHAR(255),
    body TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    provider_message_id VARCHAR(255),
    status VARCHAR(20) NOT NULL,
    attempt_no SMALLINT NOT NULL DEFAULT 1,
    scheduled_at TIMESTAMPTZ NOT NULL,
    sent_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    idempotency_key VARCHAR(100) UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_notif_deliveries_recipient_scheduled ON notification_deliveries(recipient_user_id, scheduled_at);

-- notification_dose_items (Junction Table)
CREATE TABLE notification_dose_items (
    notification_delivery_id UUID NOT NULL REFERENCES notification_deliveries(id) ON DELETE CASCADE,
    scheduled_dose_id UUID NOT NULL REFERENCES scheduled_doses(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_notification_dose_items PRIMARY KEY (notification_delivery_id, scheduled_dose_id)
);

CREATE INDEX idx_notif_dose_items_dose_id ON notification_dose_items(scheduled_dose_id);


-- =============================================================================
-- 7. Audit
-- =============================================================================

-- 21. audit_logs
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID,
    old_values JSONB,
    new_values JSONB,
    changed_fields TEXT[],
    ip_address INET,
    device_info TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for audit_logs optimization
CREATE INDEX idx_audit_logs_actor_user_id ON audit_logs(actor_user_id);
CREATE INDEX idx_audit_logs_entity_type_created ON audit_logs(entity_type, created_at DESC);

-- =============================================================================
-- 8. Chat & AI Communication
-- =============================================================================

-- 22. conversations
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID,
    title VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    last_message_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 23. messages
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID,
    role VARCHAR(20) NOT NULL,
    provider VARCHAR(50),
    model_name VARCHAR(100),
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_amount NUMERIC(12,6),
    content TEXT NOT NULL,
    currency VARCHAR(10) DEFAULT 'USD',
    latency_ms INTEGER,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- This canonical bootstrap already contains every migration through the
-- merged head 0016_merge_heads (both the notification_grouping/user_devices
-- branch and the agent_review/dose_notify_group/planning_audit/agent_run_claim
-- branch). Stamping fresh databases lets a future `alembic upgrade head`
-- start from the next revision instead of replaying DDL that is already
-- present.
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL PRIMARY KEY
);
DELETE FROM alembic_version;
INSERT INTO alembic_version(version_num) VALUES ('0016_merge_heads');


