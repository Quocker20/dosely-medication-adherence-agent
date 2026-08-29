# RemindRx Android Outbox Replay Contract

Phase 1 records pending patient writes locally only after a connectivity failure
(`IOException`/timeout). HTTP validation and authorization errors are not queued.
Phase 2 must replay rows in `outbox_actions` without logging `payloadJson`,
because payloads can contain PHI such as symptoms, SOS text, routine times, or
caregiver contact data.

## Actions

- `RECORD_DOSE_ACTION`: replay `POST /scheduled-doses/{id}/actions` with the
  outbox row `id` as `Idempotency-Key`. Repeated keys must return the existing
  adherence log and must not append a duplicate.
- `CREATE_SOS`: replay `POST /patients/{id}/sos` with the outbox row `id` as
  `Idempotency-Key`. Repeated keys must return the existing alert and must not
  open a duplicate Red Alert.
- `SUBMIT_SURVEY`: replay `POST /patients/{id}/health-surveys`. The backend's
  `(patient_id, survey_date)` uniqueness makes retry naturally idempotent only
  when the existing survey is equivalent. If the backend returns a conflict for
  different content, keep the row pending/failed for review instead of marking
  it synced.
- `UPDATE_ROUTINE`: pending routine rows are coalesced on enqueue; only the
  latest pending routine for a patient remains. Replay the full `PUT
  /patients/{id}/routine`, then request reschedule from the server. Do not
  fabricate schedule changes locally.
- `CREATE_CAREGIVER`: replay `POST /patients/{id}/caregivers`. A duplicate
  patient/caregiver conflict can be treated as synced only when the requested
  phone/relationship/channels match the existing active link.
- `DELETE_CAREGIVER`: replay `DELETE /patients/{id}/caregivers/{link_id}`. A
  missing link can be treated as synced if it is already absent for the same
  patient.

## Safety Rules

- Never replay rows for a different logged-in `patientId`.
- Never let the client change prescription dose, frequency, route, or treatment
  duration; all schedule-changing work remains server-side behind the
  deterministic validator.
- SOS queued offline is not delivered. UI must continue to tell users to call
  `115` for emergencies until the server confirms the alert.
