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
| POST | /patients/{patient_id}/prescriptions | Required (DOCTOR) | Path Param (patient_id: UUID) + CreatePrescriptionRequest | 201 Created / PrescriptionDetailResponse |
| GET | /patients/{patient_id}/prescriptions | Required (PATIENT/DOCTOR/CAREGIVER) | Path Param (patient_id: UUID) + Query Params (status, page, size) | 200 OK / PageResponse[PrescriptionDetailResponse] |
| GET | /prescriptions/{prescription_id} | Required (PATIENT/DOCTOR/CAREGIVER) | Path Param (prescription_id: UUID) | 200 OK / PrescriptionDetailResponse |
| PUT | /prescriptions/{prescription_id} | Required (DOCTOR) | Path Param (prescription_id: UUID) + UpdatePrescriptionRequest | 200 OK / PrescriptionDetailResponse |
| POST | /prescriptions/{prescription_id}/approve | Required (DOCTOR) | Path Param (prescription_id: UUID) | 200 OK / PrescriptionDetailResponse |
| POST | /prescriptions/{prescription_id}/cancel | Required (DOCTOR) | Path Param (prescription_id: UUID) + CancelPrescriptionRequest | 200 OK / PrescriptionDetailResponse |
| POST | /prescriptions/{prescription_id}/items | Required (DOCTOR) | Path Param (prescription_id: UUID) + CreatePrescriptionItemRequest | 201 Created / PrescriptionItemDetailResponse |
| PUT | /prescriptions/{prescription_id}/items/{item_id} | Required (DOCTOR) | Path Params (prescription_id: UUID, item_id: UUID) + UpdatePrescriptionItemRequest | 200 OK / PrescriptionItemDetailResponse |
| DELETE | /prescriptions/{prescription_id}/items/{item_id} | Required (DOCTOR) | Path Params (prescription_id: UUID, item_id: UUID) | 200 OK / MessageResponse |

### SLICE 6: SCHEDULES & AI AGENTS
| HTTP Method | Endpoint Path | Auth Constraints | Request Payload | Expected Response |
| :--- | :--- | :--- | :--- | :--- |
| POST | /patients/{patient_id}/schedules/generate | Required (DOCTOR/SYSTEM) | Path Param (patient_id: UUID) + GenerateScheduleRequest | 202 Accepted / AgentRunAsyncResponse |
| GET | /patients/{patient_id}/schedules | Required (PATIENT/DOCTOR/CAREGIVER) | Path Param (patient_id: UUID) + Query Params (date) | 200 OK / ActiveScheduleResponse |
| POST | /patients/{patient_id}/schedules/reschedule | Required (PATIENT/SYSTEM) | Path Param (patient_id: UUID) + RescheduleRequest | 202 Accepted / AgentRunAsyncResponse |
| GET | /agent-runs/{agent_run_id} | Required (PATIENT/DOCTOR/ADMIN) | Path Param (agent_run_id: UUID) | 200 OK / AgentRunStatusResponse |

### SLICE 7: ADHERENCE LOGGING & SAFETY ALERTS
| HTTP Method | Endpoint Path | Auth Constraints | Request Payload | Expected Response |
| :--- | :--- | :--- | :--- | :--- |
| POST | /scheduled-doses/{scheduled_dose_id}/actions | Required (PATIENT) | Path Param (scheduled_dose_id: UUID) + RecordDoseActionRequest (Header: Idempotency-Key) | 201 Created / AdherenceLogDetailResponse |
| GET | /patients/{patient_id}/adherence | Required (PATIENT/DOCTOR/CAREGIVER) | Path Param (patient_id: UUID) + Query Params (from, to) | 200 OK / AdherenceSummaryResponse |
| GET | /patients/{patient_id}/adherence/logs | Required (PATIENT/DOCTOR/CAREGIVER) | Path Param (patient_id: UUID) + Query Params (from, to, page, size) | 200 OK / PageResponse[AdherenceLogDetailResponse] |
| POST | /patients/{patient_id}/health-surveys | Required (PATIENT) | Path Param (patient_id: UUID) + SubmitHealthSurveyRequest | 201 Created / HealthSurveyDetailResponse |
| POST | /patients/{patient_id}/sos | Required (PATIENT) | Path Param (patient_id: UUID) + TriggerSosRequest (Header: Idempotency-Key) | 201 Created / AlertDetailResponse |
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

## 3. GLOBAL STATUS & EXCEPTION RESPONSE INTERFACE
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