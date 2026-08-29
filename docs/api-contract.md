# RemindRx - API CONTRACT DOCUMENTATION (API-CONTRACT.MD)
## Core Communication Interface Between Frontend & Backend

---

## 1. GENERAL CONFIGURATION & SYSTEM GLOBALS
* Local Development Base URL: http://localhost:8000/api/v1
* Default Content-Type: application/json (Except multipart/form-data for file uploads)
* Authentication Scheme: Bearer Token (JWT) transmitted via HTTP Header "Authorization: Bearer <token>"

### Global Pagination Envelope (PageResponse)
All list-retrieval endpoints utilizing pagination must return data wrapped inside the following metadata structure:
```json
{
  "content": [],
  "page_no": 0,
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
| POST | /auth/login | Public | LoginRequest | 200 OK / AuthTokenResponse |
| POST | /auth/change-password | Required (Authenticated) | ChangePasswordRequest | 200 OK / MessageResponse |
| POST | /auth/refresh | Public | RefreshTokenRequest | 200 OK / AuthTokenResponse |
| POST | /auth/logout | Required (Authenticated) | LogoutRequest | 200 OK / MessageResponse |

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
| POST | /patients/me/profile | Required (PATIENT) | PatientOnboardingRequest | 200 OK / PatientProfileDetailResponse |
| GET | /patients/{patient_id}/routine | Required (PATIENT/DOCTOR/CAREGIVER) | Path Param (patient_id: UUID) | 200 OK / PatientRoutineResponse |
| PUT | /patients/{patient_id}/routine | Required (PATIENT) | Path Param (patient_id: UUID) + UpdateRoutineRequest | 200 OK / PatientRoutineResponse |
| POST | /patients/{patient_id}/caregivers | Required (PATIENT/DOCTOR) | Path Param (patient_id: UUID) + CreateCaregiverLinkRequest | 201 Created / CaregiverLinkDetailResponse |
| GET | /patients/{patient_id}/caregivers | Required (PATIENT/DOCTOR/ADMIN) | Path Param (patient_id: UUID) | 200 OK / List[CaregiverLinkDetailResponse] |
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
| POST | /prescriptions/{prescription_id}/items | Required (DOCTOR); prescription MUST be status DRAFT | Path Param (prescription_id: UUID) + CreatePrescriptionItemRequest (medication_id required; display_name auto-snapshotted from Medication.name server-side, not client input; is_critical optional, default false) | 201 Created / PrescriptionItemDetailResponse |
| PUT | /prescriptions/{prescription_id}/items/{item_id} | Required (DOCTOR); prescription MUST be status DRAFT | Path Params (prescription_id: UUID, item_id: UUID) + UpdatePrescriptionItemRequest (medication_id required; display_name re-snapshotted from Medication.name; is_critical optional, default false) | 200 OK / PrescriptionItemDetailResponse |
| DELETE | /prescriptions/{prescription_id}/items/{item_id} | Required (DOCTOR); prescription MUST be status DRAFT | Path Params (prescription_id: UUID, item_id: UUID) | 200 OK / MessageResponse |

### SLICE 6: SCHEDULES & AI AGENTS
| HTTP Method | Endpoint Path | Auth Constraints | Request Payload | Expected Response |
| :--- | :--- | :--- | :--- | :--- |
| POST | /patients/{patient_id}/schedules/generate | Required (DOCTOR/SYSTEM) | Path Param (patient_id: UUID) + GenerateScheduleRequest | 202 Accepted / AgentRunAsyncResponse |
| GET | /patients/{patient_id}/schedules | Required (PATIENT/DOCTOR/CAREGIVER) | Path Param (patient_id: UUID) + Query Params (date) | 200 OK / ActiveScheduleResponse |
| GET | /patients/me/schedules/today | Required (PATIENT) | No caller-supplied identity/date; backend derives patient and local date from JWT/profile timezone | 200 OK / ActiveScheduleResponse |
| GET | /patients/me/schedules/next | Required (PATIENT) | No caller-supplied identity/date; returns UPCOMING, NO_SCHEDULE, or NO_UPCOMING | 200 OK / NextDoseResponse |
| POST | /patients/{patient_id}/schedules/reschedule | Required (PATIENT/SYSTEM) | Path Param (patient_id: UUID) + RescheduleRequest | 202 Accepted / AgentRunAsyncResponse |
| GET | /agent-runs/{agent_run_id} | Required (PATIENT/DOCTOR/ADMIN) | Path Param (agent_run_id: UUID) | 200 OK / AgentRunStatusResponse |
| POST | /chat | Required (PATIENT) | ChatRequest | 200 OK / ChatResponse |
| POST | /chat/voice | Required (PATIENT) | multipart/form-data (audio: UploadFile) | 200 OK / VoiceChatResponse |

**Chat AI notes.** Both endpoints act on the authenticated caller's own record: `patient_id` is read from the access token's `sub` and is never accepted from the request body or form. The agent's tools can record dose actions and raise alerts, so a caller-supplied id would be a write path into another patient's data. Both responses use the standard envelope like every other endpoint. `/chat/voice` returns `502` when the STT vendor fails and `422` when the audio yields an empty transcript; TTS failure is fail-open — the reply still returns `200` with `audio_base64: null`.

**Drug info lookup — not a separate endpoint.** The agent has one more capability reachable only through `POST /chat`/`/chat/voice`: the `search_drug_info` tool, called by the LLM mid-conversation when the patient asks about a medication. There is no dedicated HTTP route for it and none is planned — it is not part of the request/response contract above, only of the agent's internal tool-calling loop. Today it is a stub: every call returns a fixed Vietnamese fallback ("không tìm thấy thông tin đáng tin cậy, hỏi bác sĩ/dược sĩ") regardless of the query, because no retrieval pipeline exists yet (no Chroma collection, no embedding step, no citation data). Do not build a client against a `rag_result`/citation shape for this — none is produced.

### SLICE 7: ADHERENCE LOGGING & SAFETY ALERTS
| HTTP Method | Endpoint Path | Auth Constraints | Request Payload | Expected Response |
| :--- | :--- | :--- | :--- | :--- |
| POST | /scheduled-doses/{scheduled_dose_id}/actions | Required (PATIENT) | Path Param (scheduled_dose_id: UUID) + RecordDoseActionRequest (Header: Idempotency-Key) | 201 Created / AdherenceLogDetailResponse |
| GET | /patients/{patient_id}/adherence | Required (PATIENT/DOCTOR/CAREGIVER) | Path Param (patient_id: UUID) + Query Params (from, to) | 200 OK / AdherenceSummaryResponse |
| GET | /patients/{patient_id}/adherence/logs | Required (PATIENT/DOCTOR/CAREGIVER) | Path Param (patient_id: UUID) + Query Params (from, to, page, size) | 200 OK / PageResponse[AdherenceLogDetailResponse] |
| POST | /patients/{patient_id}/health-surveys | Required (PATIENT) | Path Param (patient_id: UUID) + SubmitHealthSurveyRequest | 201 Created / HealthSurveyDetailResponse |
| GET | /patients/{patient_id}/health-surveys | Required (PATIENT/DOCTOR/CAREGIVER) | Path Param (patient_id: UUID) + Query Params (from, to, page, size) | 200 OK / PageResponse[HealthSurveyListItemResponse] |
| GET | /health-surveys | Required (DOCTOR/ADMIN) | Query Params (from, to, patientId, severity, page, size) | 200 OK / PageResponse[HealthSurveyListItemResponse] |
| GET | /health-surveys/{survey_id} | Required (PATIENT/DOCTOR/CAREGIVER) | Path Param (survey_id: UUID) | 200 OK / HealthSurveyFullDetailResponse |
| POST | /patients/{patient_id}/sos | Required (PATIENT) | Path Param (patient_id: UUID) + TriggerSosRequest (Header: Idempotency-Key) | 201 Created / AlertDetailResponse |
| GET | /alerts | Required (DOCTOR/ADMIN) | Query Params (page, size, status, patientId) | 200 OK / PageResponse[AlertDetailResponse] |
| POST | /alerts/{alert_id}/acknowledge | Required (DOCTOR) | Path Param (alert_id: UUID) | 200 OK / AlertDetailResponse |
| POST | /alerts/{alert_id}/resolve | Required (DOCTOR) | Path Param (alert_id: UUID) + ResolveAlertRequest | 200 OK / AlertDetailResponse |
| GET | /patients/{patient_id}/adherence-reviews | Required (PATIENT/DOCTOR/CAREGIVER) | Path Param (patient_id: UUID) + Query Params (page, size) | 200 OK / PageResponse[AdherenceReviewDetailResponse] |
| POST | /admin/adherence-reviews/run | Required (ADMIN) | None | 202 Accepted / {task: "adherence_review.scan"} |

**Health survey notes.** `POST /patients/{id}/health-surveys` now returns **409 Conflict** on a second submission for the same `(patient_id, survey_date)` — `uq_health_surveys_patient_date` (migration `0018_health_survey_query_indexes`) enforces one survey per patient per day at the DB layer; a prior 201-on-every-retry behavior is gone. `GET /health-surveys` (list, no path param) is DOCTOR/ADMIN only: a DOCTOR sees only patients they've written at least one prescription for (same derivation as the dashboard roster — evaporates with the last prescription), an ADMIN sees the whole platform; out-of-scope narrows the result to an empty page, not 403. `GET /patients/{id}/health-surveys` and `GET /health-surveys/{survey_id}` reuse the adherence access rule (self / doctor-prescribed / active-caregiver); out-of-scope on the list returns an empty page, on the detail returns 404 (same as a nonexistent id — the endpoint must not be usable to probe which survey UUIDs are real). The list responses omit `answers_json` and the symptom list (summary only, `symptom_count`/`max_severity`); only the single-survey detail endpoint returns the full payload.

### SLICE 8: DASHBOARD REALTIME (Doctor Portal)
Backend-only slice — no agent involvement (the doctor dashboard reads adherence/alert data the same way any other client would). Implemented in `src/modules/dashboard/`.

| HTTP Method | Endpoint Path | Auth Constraints | Request Payload | Expected Response |
| :--- | :--- | :--- | :--- | :--- |
| GET | /dashboard/patients | Required (DOCTOR/ADMIN) | Query Params (page, size, alertStatus, search) | 200 OK / PageResponse[DashboardPatientListResponse] |
| GET | /dashboard/patients/{patient_id} | Required (DOCTOR/ADMIN) | Path Param (patient_id: UUID) | 200 OK / DashboardPatientDetailResponse |
| WS | /ws/dashboard | Required (DOCTOR/ADMIN) via `?token=<access_token>` | Query Param (token) | Socket accepted, then a stream of WebSocketEventStream frames |

**Scope.** A doctor sees only patients they have written at least one prescription for; an ADMIN sees all. The roster returns an empty page for an out-of-scope caller rather than 403, and `/dashboard/patients/{id}` returns **404** for both "no such patient" and "not your patient" — a distinct status would confirm which UUIDs exist. Rows are ordered by open alert count descending, so the patients needing attention are on page 1.

**Adherence figures** cover a rolling window ending now (`DASHBOARD_ADHERENCE_WINDOW_DAYS`, default 7), not a caller-supplied date range — use `GET /patients/{id}/adherence` for an explicit `[from, to]`. `open_alerts_count` counts `OPEN` **and** `ACKNOWLEDGED`: a doctor having seen an alert does not mean the patient's situation is closed. `active_prescriptions_count` counts only `APPROVED`.

**WS /ws/dashboard.** Note this path is **not** under `/api/v1`. The token travels as a query parameter because the browser WebSocket API cannot set an `Authorization` header; keep those tokens short-lived, since query strings reach proxy and browser-history logs far more readily than headers do. Authorisation happens before `accept()` — a missing, non-access, or non-DOCTOR/ADMIN token closes with code **1008** (policy violation) rather than opening a socket that immediately dies. Frames currently published: `alert.opened` (SOS or agent-detected alert raised) and `alert.updated` (acknowledged or resolved). Publishing is fail-open: a Redis outage costs the portal its liveness, never the underlying clinical write. There is no separate `/ws/dashboard/events` route — the events *are* this connection's frames; the earlier two-row listing described one endpoint as two.

**OCR removed from this contract.** The former `POST /patients/{id}/drug-label-ocr` + `GET /ocr-jobs/{id}` pair (image-of-label -> OCR -> RAG lookup) has no code behind it anywhere — no router, no `ocr_rag` module, no OCR engine wired, no Chroma collection to ground a result against. It was speculative and is dropped rather than left to imply a working feature. Re-add it here only once there is a real pipeline to document; until then, the only drug-lookup path is the `search_drug_info` chat tool described under Slice 6.

---

## 3. GLOBAL STATUS & EXCEPTION RESPONSE INTERFACE
* 200 OK / 201 Created: Business transactions completed successfully.
* 202 Accepted: Asynchronous job accepted for background processing (e.g., Planning Agent, Rescheduling Agent).
* 400 Bad Request: Structural validation constraint breaches or malformed JSON payloads (handled via FastAPI RequestValidationError / Custom Exception Handlers).
* 401 Unauthorized: Lack of valid authentication credentials, expired Access Token, or unverified OTP signature.
* 403 Forbidden: Authenticated user lacks appropriate administrative or clinical privileges (e.g., Patient attempting Doctor-only endpoints).
* 404 Not Found: Requested database entity does not exist (e.g., non-existent prescription ID, patient profile, or medication entry).
* 409 Conflict: Concurrent modification state collisions, schedule version lock breaches, or duplicate Idempotency-Key executions.
* 422 Unprocessable Entity: Syntactically valid request failing domain rules (e.g., attempting to modify a locked/APPROVED prescription item).
* 429 Too Many Requests: Rate limit exceeded (e.g., requesting OTP verification codes more than 3 times within 15 minutes).
* 500 Internal Server Error: Unhandled backend application failures or underlying infrastructure database service downtime.
* 503 Service Unavailable: Downstream AI Agent worker, S3 storage gateway, or external SMS/Zalo OTP vendor temporarily offline.
