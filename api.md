# RemindRx API Documentation

Generated from the current implementation in `src/modules/*/router.py` + `schemas.py` (not from the design-time contract — this reflects what is actually coded and running).

## 1. General

- Base URL (local dev): `http://localhost:8000/api/v1`
- Content-Type: `application/json` (all endpoints below; no multipart endpoints implemented yet)
- Auth: `Authorization: Bearer <access_token>` (JWT), except `POST /auth/login`, `POST /auth/refresh`, `POST /chat`, `POST /chat/voice`
- Every response is wrapped in a single envelope:

```json
{
  "success": true,
  "code": 200,
  "message": "Success",
  "data": { },
  "errors": null
}
```

On failure, `success: false`, `data: null`, `errors` carries validation/detail info.

### Pagination envelope (`data` field for list endpoints)

```json
{
  "content": [ ],
  "page_no": 1,
  "page_size": 10,
  "total_elements": 150,
  "total_pages": 15,
  "last": false
}
```

### Common status codes

| Code | Meaning |
| --- | --- |
| 200 / 201 | Success |
| 202 | Async job accepted (agent runs) |
| 400 | Malformed / validation error |
| 401 | Missing/invalid/expired token |
| 403 | Authenticated but wrong role/scope |
| 404 | Entity not found or out-of-scope (scoped as 404, not 403) |
| 409 | Conflict (duplicate Idempotency-Key, version lock) |
| 422 | Domain rule violation (e.g. editing a non-DRAFT prescription) |
| 429 | Rate limit exceeded |
| 500 / 502 / 503 | Server / upstream failure |

---

## 2. Authentication (`/auth`) — no auth required unless noted

### POST /auth/login
Login via phone + 6-digit PIN.

Request body:
```json
{
  "phone": "0901234567",
  "password": "123456"
}
```

Response `data` (`AuthTokenResponse`):
```json
{
  "access_token": "eyJhbGciOi...",
  "refresh_token": "eyJhbGciOi...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "is_first_login": false,
  "user": {
    "id": "b3f1...uuid",
    "phone": "0901234567",
    "role": "PATIENT",
    "status": "ACTIVE"
  }
}
```

### POST /auth/change-password
Auth required. Sets `is_first_login = false`.

Request body:
```json
{
  "current_password": "123456",
  "new_password": "654321"
}
```
Both fields: exactly 6 digits (`^\d{6}$`).

Response `data`: `null` (message only, e.g. `"Password changed successfully"`).

### POST /auth/refresh
Request body:
```json
{ "refresh_token": "eyJhbGciOi..." }
```
Response `data`: same shape as `AuthTokenResponse` above.

### POST /auth/logout
Auth required.

Request body:
```json
{ "refresh_token": "eyJhbGciOi..." }
```
Response `data`: `null`.

---

## 3. Admin & Doctor Management (`/admin`) — role: ADMIN

### POST /admin/doctors → 201
Request body (`CreateDoctorRequest`):
```json
{
  "phone": "+84901112233",
  "name": "Dr. Nguyen Van A",
  "license_no": "VN-LIC-00123",
  "specialty": "Cardiology"
}
```

Response `data` (`CreateDoctorResponse`):
```json
{
  "doctor": {
    "user_id": "uuid",
    "phone": "+84901112233",
    "role": "DOCTOR",
    "status": "ACTIVE",
    "name": "Dr. Nguyen Van A",
    "license_no": "VN-LIC-00123",
    "specialty": "Cardiology",
    "created_at": "2026-08-14T10:00:00Z"
  },
  "temp_password": "482913"
}
```
`temp_password` is shown once — admin must relay it; doctor is forced to change PIN on first login.

### GET /admin/doctors
Query: `page` (default 1), `size` (default 10, max 100), `search` (name/phone/license_no).

Response `data`: `PageResponse<DoctorDetailResponse>` (see doctor object shape above, without `temp_password`).

### GET /admin/doctors/{doctor_id}
Path: `doctor_id: UUID`. Response `data`: `DoctorDetailResponse`.

### PUT /admin/doctors/{doctor_id}
Request body (`UpdateDoctorRequest`, all optional):
```json
{
  "name": "Dr. Nguyen Van A",
  "specialty": "Internal Medicine",
  "status": "INACTIVE"
}
```
`status` pattern: `ACTIVE|INACTIVE`. Response `data`: `DoctorDetailResponse`.

### DELETE /admin/doctors/{doctor_id}
Deactivates the account. Response `data`: `null` (message only).

### GET /admin/audit-logs
Query: `page`, `size`, `actorId` (UUID), `entityType`.

Response `data`: `PageResponse<AuditLogListResponse>`, each item:
```json
{
  "id": "uuid",
  "actor_user_id": "uuid",
  "action": "UPDATE_DOCTOR",
  "entity_type": "DOCTOR",
  "entity_id": "uuid",
  "old_values": { "status": "ACTIVE" },
  "new_values": { "status": "INACTIVE" },
  "ip_address": "127.0.0.1",
  "created_at": "2026-08-14T10:00:00Z"
}
```

---

## 4. Doctor & Patient Clinical Management

### POST /doctors/patients → 201 — role: DOCTOR
Request body (`CreatePatientByDoctorRequest`):
```json
{
  "phone": "+84907654321",
  "name": "Tran Thi B",
  "dob": "1950-05-20",
  "sex": "FEMALE",
  "timezone": "Asia/Ho_Chi_Minh",
  "emergency_note": "Penicillin allergy"
}
```
Response `data` (`CreatePatientResponse`):
```json
{
  "patient": {
    "user_id": "uuid",
    "phone": "+84907654321",
    "role": "PATIENT",
    "status": "ACTIVE",
    "name": "Tran Thi B",
    "dob": "1950-05-20",
    "sex": "FEMALE",
    "timezone": "Asia/Ho_Chi_Minh",
    "privacy_consent_status": null,
    "emergency_note": "Penicillin allergy",
    "created_at": "2026-08-14T10:00:00Z",
    "updated_at": "2026-08-14T10:00:00Z"
  },
  "temp_password": "738201"
}
```

### GET /doctors/patients — role: DOCTOR
Only returns patients the requesting doctor has prescribed for.
Query: `page` (≤1000), `size` (≤100), `search` (min length 2).
Response `data`: `PageResponse<PatientDetailResponse>`.

### GET /doctors/patients/{patient_id} — role: DOCTOR or ADMIN
Doctor sees only their own scoped patients; out-of-scope → 404. Response `data`: `PatientDetailResponse`.

### GET /medications — any authenticated role
Query: `page`, `size`, `search` (min length 2).
Response `data`: `PageResponse<MedicationDetailResponse>`, item shape:
```json
{
  "id": "uuid",
  "name": "Paracetamol 500mg",
  "composition": "Paracetamol 500mg",
  "manufacturer": "XYZ Pharma",
  "uses": "Pain relief, fever",
  "side_effects": "Nausea",
  "image_url": "https://...",
  "source_name": "DrugBank",
  "is_active": true
}
```

### GET /medications/{medication_id} — any authenticated role
Response `data`: `MedicationDetailResponse` (shape above).

---

## 5. Patient Profile, Routine & Caregiver Links (`/patients`)

### POST /patients/me/profile — role: PATIENT (self)
Self-onboarding on first login.

Request body (`PatientOnboardingRequest`):
```json
{
  "name": "Tran Thi B",
  "dob": "1950-05-20",
  "sex": "FEMALE",
  "timezone": "Asia/Ho_Chi_Minh",
  "emergency_note": "Penicillin allergy",
  "routine": {
    "wake_time": "06:30:00",
    "breakfast_time": "07:00:00",
    "lunch_time": "12:00:00",
    "dinner_time": "18:00:00",
    "sleep_time": "22:00:00"
  }
}
```
Response `data` (`PatientProfileDetailResponse`):
```json
{
  "profile": { "...": "PatientDetailResponse shape" },
  "routine": {
    "id": "uuid",
    "patient_id": "uuid",
    "wake_time": "06:30:00",
    "breakfast_time": "07:00:00",
    "lunch_time": "12:00:00",
    "dinner_time": "18:00:00",
    "sleep_time": "22:00:00",
    "updated_at": "2026-08-14T10:00:00Z"
  }
}
```

### GET /patients/{patient_id}/routine — any authenticated user
Access resolved server-side (self / doctor-prescribed / active caregiver). Response `data`: `PatientRoutineResponse` (shape above).

### PUT /patients/{patient_id}/routine — role: PATIENT (self)
Request body (`UpdateRoutineRequest`, all fields optional `HH:MM:SS`):
```json
{ "wake_time": "07:00:00", "sleep_time": "22:30:00" }
```
Response `data`: `PatientRoutineResponse`.

### POST /patients/{patient_id}/caregivers → 201 — role: PATIENT (self)
Find-or-create caregiver account by phone.

Request body (`CreateCaregiverLinkRequest`):
```json
{
  "caregiver_phone": "+84909998888",
  "relationship": "Con gái",
  "channels": ["APP_NOTIFICATION", "SMS"]
}
```
Response `data` (`CaregiverLinkDetailResponse`):
```json
{
  "id": "uuid",
  "patient_id": "uuid",
  "caregiver_user_id": "uuid",
  "relationship": "Con gái",
  "channels": ["APP_NOTIFICATION", "SMS"],
  "status": "ACTIVE",
  "created_at": "2026-08-14T10:00:00Z",
  "temp_password": "915302"
}
```
`temp_password` is only non-null when this call just created a new caregiver account.

### GET /patients/{patient_id}/caregivers — role: PATIENT (self) or ADMIN
Response `data`: `List<CaregiverLinkDetailResponse>` (not paginated).

### DELETE /patients/{patient_id}/caregivers/{caregiver_link_id} — role: PATIENT (self) or ADMIN
Hard delete. Response `data`: `{ "message": "Caregiver link removed successfully" }`.

---

## 6. Prescriptions & Prescription Items

### POST /prescriptions → 201 — role: DOCTOR
Creates a DRAFT prescription atomically with its items. Patient identified by **phone**, not a path param — find-or-create.

Request body (`CreatePrescriptionRequest`):
```json
{
  "phone": "+84907654321",
  "diagnosis_note": "Hypertension follow-up",
  "items": [
    {
      "medication_id": "uuid",
      "dose_unit": "tablet",
      "morning_dose": 1,
      "noon_dose": null,
      "evening_dose": 1,
      "bedtime_dose": null,
      "route": "ORAL",
      "meal_relation": "AFTER_MEAL",
      "minimum_interval_minutes": 480,
      "start_date": "2026-08-14",
      "end_date": "2026-09-14",
      "instructions": "Take with water"
    }
  ]
}
```
Response `data` (`CreatePrescriptionResponse`):
```json
{
  "prescription": {
    "id": "uuid",
    "patient_id": "uuid",
    "doctor_id": "uuid",
    "status": "DRAFT",
    "diagnosis_note": "Hypertension follow-up",
    "approved_at": null,
    "created_at": "2026-08-14T10:00:00Z",
    "items": [
      {
        "id": "uuid",
        "prescription_id": "uuid",
        "medication_id": "uuid",
        "display_name": "Amlodipine 5mg",
        "dose_unit": "tablet",
        "morning_dose": 1,
        "noon_dose": null,
        "evening_dose": 1,
        "bedtime_dose": null,
        "route": "ORAL",
        "meal_relation": "AFTER_MEAL",
        "minimum_interval_minutes": 480,
        "start_date": "2026-08-14",
        "end_date": "2026-09-14",
        "instructions": "Take with water",
        "created_at": "2026-08-14T10:00:00Z"
      }
    ]
  },
  "temp_password": "204981"
}
```
`temp_password` is non-null only if this call just provisioned a new patient account.

### GET /patients/{patient_id}/prescriptions — any authenticated user
Query: `status` (`DRAFT|APPROVED|CANCELLED`), `page` (≤1000), `size` (≤100).
Response `data`: `PageResponse<PrescriptionDetailResponse>`.

### GET /prescriptions/{prescription_id} — any authenticated user
Response `data`: `PrescriptionDetailResponse` (shape above).

### PUT /prescriptions/{prescription_id} — role: DOCTOR (own prescription, must be DRAFT)
Request body:
```json
{ "diagnosis_note": "Updated diagnosis text" }
```
Response `data`: `PrescriptionDetailResponse`.

### POST /prescriptions/{prescription_id}/approve — role: DOCTOR (own, must be DRAFT)
No body. Locks the prescription (`status → APPROVED`). Response `data`: `PrescriptionDetailResponse`.

### POST /prescriptions/{prescription_id}/cancel — role: DOCTOR (own, DRAFT or APPROVED)
Request body:
```json
{ "cancel_reason": "Patient reported adverse reaction" }
```
Response `data`: `PrescriptionDetailResponse` (`status: "CANCELLED"`).

### POST /prescriptions/{prescription_id}/items → 201 — role: DOCTOR (own, prescription must be DRAFT)
Request body (`CreatePrescriptionItemRequest` — same shape as one item above, `medication_id` required; `display_name` is server-derived, not client input).
Response `data`: `PrescriptionItemDetailResponse`.
422 if prescription is no longer DRAFT.

### PUT /prescriptions/{prescription_id}/items/{item_id} — role: DOCTOR (own, DRAFT only)
Request body: same shape as `CreatePrescriptionItemRequest`.
Response `data`: `PrescriptionItemDetailResponse`.

### DELETE /prescriptions/{prescription_id}/items/{item_id} — role: DOCTOR (own, DRAFT only)
Hard delete. Response `data`: `{ "message": "Prescription item removed successfully" }`.

---

## 7. Schedules & AI Agents

### POST /patients/{patient_id}/schedules/generate → 202 — role: DOCTOR (scoped)
Triggers the async Planning Agent (Celery worker).

Request body (`GenerateScheduleRequest`):
```json
{ "reason": "New prescription approved" }
```
Response `data` (`AgentRunAsyncResponse`):
```json
{
  "agent_run_id": "uuid",
  "status": "PENDING",
  "message": "Schedule generation started"
}
```

### GET /patients/{patient_id}/schedules — role: PATIENT/DOCTOR/CAREGIVER
Query: `date` (defaults to today, local calendar date).
Response `data` (`ActiveScheduleResponse`):
```json
{
  "patient_id": "uuid",
  "date": "2026-08-14",
  "doses": [
    {
      "scheduled_dose_id": "uuid",
      "medication_name": "Amlodipine 5mg",
      "current_scheduled_at": "2026-08-14T07:00:00+07:00",
      "status": "PENDING",
      "snooze_count": 0
    }
  ]
}
```

### POST /patients/{patient_id}/schedules/reschedule → 202 — role: PATIENT (self)
Wipes future PENDING doses and regenerates from the current routine.

Request body (`RescheduleRequest`):
```json
{ "reason": "Changed sleep schedule" }
```
Response `data`: `AgentRunAsyncResponse` (shape above).

### GET /agent-runs/{agent_run_id} — role: PATIENT/DOCTOR/ADMIN
Response `data` (`AgentRunStatusResponse`):
```json
{
  "id": "uuid",
  "agent_type": "PLANNING",
  "patient_id": "uuid",
  "prescription_id": "uuid",
  "trigger_type": "DOCTOR_APPROVAL",
  "graph_version": "v1",
  "status": "SUCCEEDED",
  "latency_ms": 842,
  "error_code": null,
  "generated_dose_count": 28,
  "created_at": "2026-08-14T10:00:00Z"
}
```

---

## 8. Patient Chat AI (`/chat`) — no auth required (patient_id passed explicitly)

> Newest addition — voice/text conversational agent (LangGraph), wired to the same agent tools as dose actions / SOS.

### POST /chat
Text chat with the AI agent.

Request body (`ChatRequest`):
```json
{
  "message": "Tôi vừa uống thuốc huyết áp rồi",
  "patient_id": "uuid-or-id-string"
}
```
`message`: 1–5000 chars.

Response body (`ChatResponse`, **not** wrapped in the `APIResponse` envelope — returned directly):
```json
{ "response": "Đã ghi nhận bạn uống thuốc lúc 07:05. Cảm ơn bạn!" }
```
500 on internal agent failure (`detail: <error string>`).

### POST /chat/voice
Voice chat: audio in, transcript + text + optional TTS audio out.

Request: `multipart/form-data`
| Field | Type | Notes |
| --- | --- | --- |
| `patient_id` | string (form field) | required |
| `audio` | file | required, e.g. `.webm`/`.wav` |

Response body (`VoiceChatResponse`, returned directly, not envelope-wrapped):
```json
{
  "transcript": "Tôi vừa uống thuốc huyết áp rồi",
  "response": "Đã ghi nhận bạn uống thuốc lúc 07:05. Cảm ơn bạn!",
  "audio_base64": "SUQzBAAAAAAAI1RTU0U..."
}
```
`audio_base64` is `null` if TTS synthesis fails (fail-open — text response still returned).

Errors:
- `422` — empty/undetected transcript (`"Không nhận được nội dung giọng nói, vui lòng nói lại."`)
- `502` — upstream speech service (STT) failure
- `500` — internal agent failure

---

## 9. Adherence Logging & Safety Alerts

### POST /scheduled-doses/{scheduled_dose_id}/actions → 201 — role: PATIENT (own dose)
Header: `Idempotency-Key` (required — a retried request replays the original result instead of double-logging).

Request body (`RecordDoseActionRequest`):
```json
{
  "action": "TAKEN",
  "action_source": "PATIENT_MOBILE_APP",
  "payload": {}
}
```
`action`: `TAKEN | SNOOZE | SKIPPED`.

Response `data` (`AdherenceLogDetailResponse`):
```json
{
  "id": "uuid",
  "scheduled_dose_id": "uuid",
  "patient_id": "uuid",
  "action": "TAKEN",
  "performed_at": "2026-08-14T07:05:00+07:00",
  "action_source": "PATIENT_MOBILE_APP",
  "payload": {},
  "idempotency_key": "6f2a1c3e-..."
}
```
409 on a duplicate `Idempotency-Key` used with a conflicting body.

### GET /patients/{patient_id}/adherence — role: PATIENT/DOCTOR/CAREGIVER
Query: `from`, `to` (dates, required).
Response `data` (`AdherenceSummaryResponse`):
```json
{
  "patient_id": "uuid",
  "from_date": "2026-08-01",
  "to_date": "2026-08-14",
  "adherence_rate": 0.92,
  "total_doses": 84,
  "taken_doses": 77,
  "skipped_doses": 4,
  "missed_doses": 3
}
```

### GET /patients/{patient_id}/adherence/logs — role: PATIENT/DOCTOR/CAREGIVER
Query: `from`, `to` (required), `page` (≤1000), `size` (≤100).
Response `data`: `PageResponse<AdherenceLogDetailResponse>`.

### POST /patients/{patient_id}/health-surveys → 201 — role: PATIENT (self)
A `SEVERE` symptom auto-raises a safety Alert in the same transaction.

Request body (`SubmitHealthSurveyRequest`):
```json
{
  "survey_date": "2026-08-14",
  "answers_json": { "sleep_quality": "good", "appetite": "normal" },
  "symptoms": [
    { "symptom_code": "DIZZINESS", "severity": "MODERATE", "description": "Sáng dậy hơi choáng" }
  ]
}
```
`severity`: `MILD | MODERATE | SEVERE`.

Response `data` (`HealthSurveyDetailResponse`):
```json
{
  "id": "uuid",
  "patient_id": "uuid",
  "survey_date": "2026-08-14",
  "status": "SUBMITTED",
  "submitted_at": "2026-08-14T10:00:00Z"
}
```

### POST /patients/{patient_id}/sos → 201 — role: PATIENT (self)
Header: `Idempotency-Key` (required — prevents a retried tap from paging a doctor twice).

Request body (`TriggerSosRequest`):
```json
{
  "message": "Chóng mặt nặng, cần trợ giúp",
  "metadata": { "lat": 10.762622, "lng": 106.660172 }
}
```
Response `data` (`AlertDetailResponse`):
```json
{
  "id": "uuid",
  "patient_id": "uuid",
  "assigned_doctor_id": null,
  "triggered_by_type": "PATIENT",
  "alert_type": "SOS",
  "severity": "CRITICAL",
  "status": "OPEN",
  "message": "Chóng mặt nặng, cần trợ giúp",
  "created_at": "2026-08-14T10:00:00Z"
}
```

### GET /alerts — role: DOCTOR/ADMIN
Query: `status` (`OPEN|ACKNOWLEDGED|RESOLVED`), `patientId` (UUID), `page` (≤1000), `size` (≤100).
Response `data`: `PageResponse<AlertDetailResponse>`.

### POST /alerts/{alert_id}/acknowledge — role: DOCTOR
No body. Assigns the acknowledging doctor. Response `data`: `AlertDetailResponse` (`status: "ACKNOWLEDGED"`).

### POST /alerts/{alert_id}/resolve — role: DOCTOR
Request body:
```json
{ "resolution_note": "Contacted patient by phone, stable now." }
```
Response `data`: `AlertDetailResponse` (`status: "RESOLVED"`).

---

## 10. Not yet implemented

The design contract (`docs/api-contract.md`, Slice 8) also specifies OCR/RAG/dashboard-realtime endpoints — no corresponding module (`ocr`, `dashboard`) exists in `src/modules/` yet:

- `POST /patients/{patient_id}/drug-label-ocr`
- `GET /ocr-jobs/{ocr_job_id}`
- `GET /dashboard/patients`
- `GET /dashboard/patients/{patient_id}`
- `WS /ws/dashboard`, `STREAM /ws/dashboard/events`

---

## 11. Known deviations from `docs/api-contract.md`

- `POST /prescriptions` uses `phone` in the request body (find-or-create) instead of a `patient_id` path param.
- `POST/GET/DELETE /patients/{patient_id}/caregivers` are DOCTOR-excluded (patient/admin only) — caregiver management is kept out of doctor scope.
- `CreatePatientResponse` / `CreatePrescriptionResponse` / `CaregiverLinkDetailResponse` all carry a one-time `temp_password` field not listed in the original contract, needed because these flows can provision a login-capable account inline.
