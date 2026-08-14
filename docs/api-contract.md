# RemindRx - API CONTRACT DOCUMENTATION (API-CONTRACT.MD)
## Core Communication Interface Between Frontend & Backend

---

## 1. GENERAL CONFIGURATION & SYSTEM GLOBALS
* Local Development Base URL: http://localhost:8000/api/v1
* Default Content-Type: application/json (Except multipart/form-data for file uploads)
* Authentication Scheme: Bearer Token (JWT) transmitted via HTTP Header "Authorization: Bearer <token>"
* Unless explicitly marked as bare, HTTP bodies use `{ "success": boolean, "code": integer, "message": string, "data": any|null }`. Android repositories must require both `success == true` and non-null `data` for data-bearing endpoints.

### Global Pagination Envelope (PageResponse)
All list-retrieval endpoints utilizing pagination must return data wrapped inside the following metadata structure:
```json
{
  "content": [],
  "page_no": 1,
  "page_size": 10,
  "total_elements": 150,
  "total_pages": 15,
  "last": false
}
```

---

## 2. DETAILED ENDPOINT REGISTRY

### SLICE 1: AUTHENTICATION
| HTTP Method | Endpoint Path | Auth Constraints | Request Payload | Expected Response |
| :--- | :--- | :--- | :--- | :--- |
| POST | /auth/login | Public | `{ "phone": string, "password": 6-digit PIN }` | 200 / envelope `data`: `access_token`, `refresh_token`, `token_type`, `expires_in`, `is_first_login`, `user` |
| POST | /auth/change-password | Required (Authenticated) | `{ "current_password": 6-digit PIN, "new_password": 6-digit PIN }` | 200 / envelope `data: null`; human message is in envelope `message` |
| POST | /auth/refresh | Public | `{ "refresh_token": string }` | 200 / envelope `data`: a rotated `AuthTokenResponse` pair |
| POST | /auth/logout | Required (Authenticated) | Bearer + `{ "refresh_token": string }` | 200 / envelope `data: null`; human message is in envelope `message` |

### SLICE 2: ADMIN & DOCTOR MANAGEMENT
| HTTP Method | Endpoint Path | Auth Constraints | Request Payload | Expected Response |
| :--- | :--- | :--- | :--- | :--- |
| POST | /admin/doctors | Required (ADMIN) | CreateDoctorRequest | 201 Created / CreateDoctorResponse |
| GET | /admin/doctors | Required (ADMIN) | Query Params (page, size, search) | 200 OK / PageResponse[DoctorDetailResponse] |
| GET | /admin/doctors/{doctor_id} | Required (ADMIN) | Path Param (doctor_id: UUID) | 200 OK / DoctorDetailResponse |
| PUT | /admin/doctors/{doctor_id} | Required (ADMIN) | Path Param (doctor_id: UUID) + UpdateDoctorRequest | 200 OK / DoctorDetailResponse |
| DELETE | /admin/doctors/{doctor_id} | Required (ADMIN) | Path Param (doctor_id: UUID) | 200 OK / MessageResponse |
| GET | /admin/audit-logs | Required (ADMIN) | Query Params (page, size, actorId, entityType) | 200 OK / PageResponse[AuditLogListResponse] |

### SLICE 3: DOCTOR & PATIENT CLINICAL MANAGEMENT
| HTTP Method | Endpoint Path | Auth Constraints | Request Payload | Expected Response |
| :--- | :--- | :--- | :--- | :--- |
| POST | /doctors/patients | Required (DOCTOR) | CreatePatientByDoctorRequest | 201 Created / PatientDetailResponse |
| GET | /doctors/patients | Required (DOCTOR) | Query Params (page, size, search) | 200 OK / PageResponse[PatientDetailResponse] |
| GET | /doctors/patients/{patient_id} | Required (DOCTOR/ADMIN) | Path Param (patient_id: UUID) | 200 OK / PatientDetailResponse |
| GET | /medications | Required (Authenticated) | Query Params (page, size, search) | 200 OK / PageResponse[MedicationDetailResponse] |
| GET | /medications/{medication_id} | Required (Authenticated) | Path Param (medication_id: UUID) | 200 OK / MedicationDetailResponse |

### SLICE 4: PATIENT PROFILE, ROUTINE & CAREGIVER LINKS
| HTTP Method | Endpoint Path | Auth Constraints | Request Payload | Expected Response |
| :--- | :--- | :--- | :--- | :--- |
| POST | /patients/me/profile | Required (PATIENT) | Legacy full-profile onboarding for other clients. The Android patient app MUST NOT call this endpoint. | 200 OK / PatientProfileDetailResponse |
| GET | /patients/{patient_id}/routine | Required (PATIENT/DOCTOR/CAREGIVER) | Path Param (patient_id: UUID) | 200 OK / PatientRoutineResponse |
| PUT | /patients/{patient_id}/routine | Required (PATIENT self) | Idempotent create-or-update. Path Param (patient_id: UUID) + UpdateRoutineRequest (`wake_time`, `breakfast_time`, `lunch_time`, `dinner_time`, `sleep_time`, each nullable `HH:mm`) | 200 OK / PatientRoutineResponse |
| POST | /patients/{patient_id}/caregivers | Required (PATIENT self) | Path Param + `{ "caregiver_phone": string, "relationship": string?, "channels": ["APP_NOTIFICATION"] }` | 201 Created / CaregiverLinkDetailResponse; `temp_password` is one-time and nullable |
| GET | /patients/{patient_id}/caregivers | Required (PATIENT self/ADMIN) | Path Param (patient_id: UUID) | 200 OK / List[CaregiverLinkDetailResponse] |
| DELETE | /patients/{patient_id}/caregivers/{caregiver_link_id} | Required (PATIENT/ADMIN) | Path Params (patient_id: UUID, caregiver_link_id: UUID) | 200 OK / MessageResponse |

### SLICE 5: PRESCRIPTIONS & PRESCRIPTION ITEMS
| HTTP Method | Endpoint Path | Auth Constraints | Request Payload | Expected Response |
| :--- | :--- | :--- | :--- | :--- |
| POST | /prescriptions | Required (DOCTOR) | CreatePrescriptionRequest (phone-based find-or-create patient, atomic with items) | 201 Created / CreatePrescriptionResponse |
| GET | /patients/{patient_id}/prescriptions | Required (PATIENT/DOCTOR/CAREGIVER) | Path Param (patient_id: UUID) + Query Params (status, page, size) | 200 OK / PageResponse[PrescriptionDetailResponse] |
| GET | /prescriptions/{prescription_id} | Required (PATIENT/DOCTOR/CAREGIVER) | Path Param (prescription_id: UUID) | 200 OK / PrescriptionDetailResponse |
| PUT | /prescriptions/{prescription_id} | Required (DOCTOR) | Path Param (prescription_id: UUID) + UpdatePrescriptionRequest | 200 OK / PrescriptionDetailResponse |
| POST | /prescriptions/{prescription_id}/approve | Required (DOCTOR) | Path Param (prescription_id: UUID) | 200 OK / PrescriptionDetailResponse |
| POST | /prescriptions/{prescription_id}/cancel | Required (DOCTOR) | Path Param (prescription_id: UUID) + CancelPrescriptionRequest | 200 OK / PrescriptionDetailResponse |
| POST | /prescriptions/{prescription_id}/items | Required (DOCTOR); prescription MUST be status DRAFT | Path Param (prescription_id: UUID) + CreatePrescriptionItemRequest (medication_id required; display_name auto-snapshotted from Medication.name server-side, not client input) | 201 Created / PrescriptionItemDetailResponse |
| PUT | /prescriptions/{prescription_id}/items/{item_id} | Required (DOCTOR); prescription MUST be status DRAFT | Path Params (prescription_id: UUID, item_id: UUID) + UpdatePrescriptionItemRequest (medication_id required; display_name re-snapshotted from Medication.name) | 200 OK / PrescriptionItemDetailResponse |
| DELETE | /prescriptions/{prescription_id}/items/{item_id} | Required (DOCTOR); prescription MUST be status DRAFT | Path Params (prescription_id: UUID, item_id: UUID) | 200 OK / MessageResponse |

### SLICE 6: SCHEDULES & AI AGENTS
| HTTP Method | Endpoint Path | Auth Constraints | Request Payload | Expected Response |
| :--- | :--- | :--- | :--- | :--- |
| POST | /patients/{patient_id}/schedules/generate | Required (DOCTOR/SYSTEM) | Path Param (patient_id: UUID) + GenerateScheduleRequest | 202 Accepted / AgentRunAsyncResponse |
| GET | /patients/{patient_id}/schedules | Required (PATIENT/DOCTOR/CAREGIVER) | Path Param + optional local-date Query Param `date` | 200 OK / ActiveScheduleResponse; each dose includes `scheduled_dose_id`, `prescription_item_id`, `medication_id`, `medication_name`, `current_scheduled_at`, `dose_slot`, `dose_value`, `dose_unit`, `meal_relation`, `status`, `snooze_count` (snapshot fields nullable for legacy rows) |
| POST | /patients/{patient_id}/schedules/reschedule | Required (PATIENT/SYSTEM) | Path Param (patient_id: UUID) + RescheduleRequest (`reason` optional) | 202 Accepted / AgentRunAsyncResponse (`agent_run_id`, `status`, `message`) |
| GET | /agent-runs/{agent_run_id} | Required (PATIENT/DOCTOR/ADMIN) | Path Param (agent_run_id: UUID) | 200 OK / AgentRunStatusResponse |
| POST | /chat | Required (PATIENT) | `{ "message": string }`; patient identity comes only from JWT `sub` | 200 OK / bare ChatResponse (not ApiEnvelope) |
| POST | /chat/voice | Required (PATIENT) | Multipart `audio`; patient identity comes only from JWT `sub` | 200 OK / bare VoiceChatResponse (not ApiEnvelope) |

### SLICE 7: ADHERENCE LOGGING & SAFETY ALERTS
| HTTP Method | Endpoint Path | Auth Constraints | Request Payload | Expected Response |
| :--- | :--- | :--- | :--- | :--- |
| POST | /scheduled-doses/{scheduled_dose_id}/actions | Required (PATIENT) | Path Param + Header `Idempotency-Key` + `RecordDoseActionRequest` (`action`: `TAKEN`/`SNOOZE`/`SKIPPED`, `action_source`, `payload`) | 201 Created / AdherenceLogDetailResponse (`performed_at`, `payload`, `idempotency_key`) |
| GET | /patients/{patient_id}/adherence | Required (PATIENT/DOCTOR/CAREGIVER) | Path Param + required inclusive local-date Query Params `from`, `to` (`YYYY-MM-DD`) | 200 OK / AdherenceSummaryResponse (`adherence_rate` is decimal percent plus dose counts) |
| GET | /patients/{patient_id}/adherence/logs | Required (PATIENT/DOCTOR/CAREGIVER) | Path Param + required inclusive Query Params `from`, `to`; optional `page`, `size` | 200 OK / PageResponse[AdherenceLogDetailResponse] |
| POST | /patients/{patient_id}/health-surveys | Required (PATIENT) | `SubmitHealthSurveyRequest`: `survey_date`, `answers_json`, `symptoms[]` (`symptom_code`, `severity`, optional `description`) | 201 Created / HealthSurveyDetailResponse |
| POST | /patients/{patient_id}/sos | Required (PATIENT) | Header `Idempotency-Key` + `TriggerSosRequest` (`message` optional, `metadata` object) | 201 Created / AlertDetailResponse (uses `status`, not `state`) |
| GET | /alerts | Required (DOCTOR/ADMIN) | Query Params (page, size, status, patientId) | 200 OK / PageResponse[AlertDetailResponse] |
| POST | /alerts/{alert_id}/acknowledge | Required (DOCTOR) | Path Param (alert_id: UUID) | 200 OK / AlertDetailResponse |
| POST | /alerts/{alert_id}/resolve | Required (DOCTOR) | Path Param (alert_id: UUID) + ResolveAlertRequest | 200 OK / AlertDetailResponse |

### SLICE 8: OCR, RAG KNOWLEDGE BASE & DASHBOARD REALTIME
| HTTP Method | Endpoint Path | Auth Constraints | Request Payload | Expected Response |
| :--- | :--- | :--- | :--- | :--- |
| POST | /patients/{patient_id}/drug-label-ocr | Required (PATIENT/DOCTOR) | Path Param (patient_id: UUID) + CreateOcrJobMultipartRequest | 202 Accepted / OcrJobAsyncResponse |
| GET | /ocr-jobs/{ocr_job_id} | Required (PATIENT/DOCTOR) | Path Param (ocr_job_id: UUID) | 200 OK / OcrJobDetailResponse |
| GET | /dashboard/patients | Required (DOCTOR/ADMIN) | Query Params (page, size, alertStatus, search) | 200 OK / PageResponse[DashboardPatientListResponse] |
| GET | /dashboard/patients/{patient_id} | Required (DOCTOR/ADMIN) | Path Param (patient_id: UUID) | 200 OK / DashboardPatientDetailResponse |
| WS | /ws/dashboard | Handshake Protocol | Initial Socket Connection Handshake (Query Token) | WebSocket Connection Established |
| STREAM | /ws/dashboard/events | Active Socket Connection | Stream events via WebSocket Connection | JSON Event Frame (WebSocketEventStream) |

---

## 3. ANDROID PATIENT WIRE RULES

* Onboarding only reads/writes the five routine timestamps through `GET/PUT /patients/{id}/routine`. `PUT` is a self-only, idempotent upsert so a doctor-created profile does not need `/patients/me/profile` first.
* After every successful routine `PUT`, call `POST .../schedules/reschedule`, then poll `GET /agent-runs/{id}` every 2 seconds for at most 60 seconds. A failed/timed-out run does not roll back the saved routine.
* A UI action `LATE` is a client concept: send wire action `TAKEN`, `action_source: "PATIENT_MOBILE_APP"`, and `payload.taken_late: true`. Any note is `payload.note`. `SNOOZE` and `SKIPPED` remain their wire actions.
* Adherence requests always send inclusive Monday-to-today `from`/`to` dates for the current week. `adherence_rate` is a floating-point percent and is rounded only for integer UI display.
* Survey mood is sent as `answers_json.mood`. A symptom uses a stable `symptom_code`, `severity` (`MILD`, `MODERATE`, `SEVERE`) and optional `description`. `NONE` means an empty `symptoms` list; only a real `SEVERE` symptom creates a red alert.
* SOS location consent is `metadata.share_location`; the response field is `status`. The Android app currently sends `false` because native GPS collection is out of scope.
* Access tokens are attached as Bearer credentials. On one 401, refresh once and replay once; refresh failure clears the local session. Logout revokes the refresh token before clearing local encrypted state.
* Backend timestamps are offsets/UTC. Android renders patient-facing dose and adherence times in `Asia/Ho_Chi_Minh` using an instant-preserving timezone conversion.

---

## 4. GLOBAL STATUS & EXCEPTION RESPONSE INTERFACE
* 200 OK / 201 Created: Business transactions completed successfully.
* 202 Accepted: Asynchronous job accepted for background processing (e.g., Planning Agent, Rescheduling Agent, OCR Worker).
* 400 Bad Request: Structural validation constraint breaches or malformed JSON payloads (handled via FastAPI RequestValidationError / Custom Exception Handlers).
* 401 Unauthorized: Lack of valid authentication credentials, expired Access Token, or unverified OTP signature.
* 403 Forbidden: Authenticated user lacks appropriate administrative or clinical privileges (e.g., Patient attempting Doctor-only endpoints).
* 404 Not Found: Requested database entity does not exist (e.g., non-existent prescription ID, patient profile, or medication entry).
* 409 Conflict: Concurrent modification state collisions, schedule version lock breaches, or duplicate Idempotency-Key executions.
* 422 Unprocessable Entity: Syntactically valid request failing domain rules (e.g., attempting to modify a locked/APPROVED prescription item).
* 429 Too Many Requests: Rate limit exceeded (e.g., requesting OTP verification codes more than 3 times within 15 minutes).
* 500 Internal Server Error: Unhandled backend application failures or underlying infrastructure database service downtime.
* 503 Service Unavailable: Downstream AI Agent worker, S3 storage gateway, or external SMS/Zalo OTP vendor temporarily offline.
