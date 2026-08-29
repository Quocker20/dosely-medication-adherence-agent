# Frontend Implementation Plan — Graded Adherence Review

Backend done (Stage 1–7, `feat/adherence`). This doc scans every backend change touching the doctor portal and lays out the exact frontend diff, file by file, following the codebase's own conventions (barrel imports, `types/*.ts` mirrors `schemas.py` 1:1, Vietnamese inline comments explaining backend rationale, `utils/labels.ts` as the single place raw enum -> label/tone lives).

## 1. Backend surface scanned

Two independent features shipped, both touch the doctor portal, neither has any frontend code yet.

### 1.1 `is_critical` (Stage 2 — critical-dose fast path)

- `src/modules/prescriptions/schemas.py:52,141` — `PrescriptionItemBase.is_critical: bool = False`, also on `PrescriptionItemDetailResponse`. Doctor sets this per line item when creating/editing a prescription item.
- `src/modules/prescriptions/models.py:131` — `PrescriptionItem.is_critical`, migration `0021_dose_is_critical`.
- Snapshotted onto `scheduled_doses.is_critical` at planning time (`planner.py`), narrows `MissedDoseScanService` to only alert on 3-consecutive-miss streaks for items the doctor flagged critical.
- **Frontend has zero references to `is_critical`** (`isCritical`/`is_critical` grep on `web/src` = 0 hits). The field exists nowhere in `web/src/types/prescriptions.ts`, and `PrescriptionView.tsx`'s `emptyItem()` doesn't set it — so every item created through the doctor portal today sends the schema default `false`, permanently. There is no way to reach the critical-streak alert path through the UI at all right now.

### 1.2 Adherence review (Stages 1–7 — nightly graded-severity review)

- New table `adherence_reviews` (migration `0022`), one row/patient/night, only when `severity != NONE`.
- `src/modules/adherence_review/schemas.py` — `AdherenceReviewDetailResponse`: `severity`, `days_in_severity`, `remedy_class` (nullable), `action_taken`, `indicators` (raw dict), `llm_reasoning` (nullable), `llm_confidence` (nullable).
- `src/modules/adherence_review/enums.py` — `Severity` (NONE/MILD/MODERATE/SEVERE), `Action` (NONE/PATIENT_NOTIFICATION/DOCTOR_WARNING/DOCTOR_ALERT).
- `src/modules/adherence_review/llm.py:42-48` — `RemedyClass`: `RESCHEDULE_TIMING`, `SUSPECTED_SIDE_EFFECT`, `DELIBERATE_REFUSAL`, `DISENGAGEMENT`, `EXTERNAL_DISRUPTION`, `UNCLEAR`.
- `src/modules/adherence_review/router.py` — `GET /patients/{patient_id}/adherence-reviews` (PATIENT/DOCTOR/CAREGIVER, same access rule as adherence logs — out-of-scope returns empty page, not 404), `POST /admin/adherence-reviews/run` (ADMIN, manual trigger, 202).
- `docs/schema.md` §7.12 / `docs/api-contract.md` Slice 7 are the tracked contract copies — already in sync with the above (do not re-derive from `.claude/rules/*.md`, that dir is gitignored and stale).
- When `DOCTOR_WARNING`/`DOCTOR_ALERT` fires, `_persist_one` creates an `alerts` row with `triggered_by_type="ADHERENCE_REVIEW"` and `message=analysis.reasoning_doctor` (the LLM's doctor-facing text) — this already renders today in `AlertsView.tsx:86` (`{alert.message}`) with zero frontend change, just no visual distinction from a rule-authored alert.
- `ck_alerts_triggered_by_type` (migration `0023`) now accepts `ADHERENCE_REVIEW` alongside `SOS_BUTTON`/`SEVERE_SYMPTOM`/`MISSED_DOSES`. Frontend's `AlertTriggeredBy` union (`types/alerts.ts:6`) and `ALERT_TRIGGER` record (`utils/labels.ts:20`) were never updated — a review-triggered alert falls through `alertTriggerLabel()`'s `?? trigger` fallback and shows the raw string `"ADHERENCE_REVIEW"` to the doctor today.
- `WebSocketEventStream.event_type` gained `adherence.updated` and `health_survey.submitted` (per `docs/schema.md` §8.3); frontend's `PatientRealtimeEvent` union (`types/dashboard.ts:47-63`) only types `routine.updated`/`schedule.updated`. Not required for this feature (no review-specific WS event exists — a new review is only visible via `alert.opened` or the next poll), but is a pre-existing drift worth a one-line note, not a blocker.

Everything below is scoped strictly to what's needed to surface `is_critical` and adherence reviews; the `PatientRealtimeEvent` drift is out of scope.

## 2. File-by-file diff

### Step 1 — Types (`web/src/types/`)

**`web/src/types/prescriptions.ts`**
Add `is_critical` to both the outgoing and the response shape, matching how every other boolean/field pair in this file already mirrors `schemas.py` 1:1:

```ts
export interface PrescriptionItemIn {
  // ...existing fields
  is_critical: boolean;
}

export interface PrescriptionItemDetail {
  // ...existing fields
  is_critical: boolean;
}
```
Not optional — backend schema default is `False`, not `None`, so the request type should always carry a real boolean the same way `route` always carries a real string with a default.

**`web/src/types/adherence.ts`**
New interface, same file `AdherenceLog` already lives in (this is Slice 7, same as adherence logs — not a new slice, so no new file):

```ts
export type AdherenceReviewSeverity = "MILD" | "MODERATE" | "SEVERE";
export type AdherenceReviewAction = "NONE" | "PATIENT_NOTIFICATION" | "DOCTOR_WARNING" | "DOCTOR_ALERT";
export type RemedyClass =
  | "RESCHEDULE_TIMING"
  | "SUSPECTED_SIDE_EFFECT"
  | "DELIBERATE_REFUSAL"
  | "DISENGAGEMENT"
  | "EXTERNAL_DISRUPTION"
  | "UNCLEAR";

export interface AdherenceReviewDetail {
  id: string;
  patient_id: string;
  review_date: string;
  window_start: string;
  window_end: string;
  severity: AdherenceReviewSeverity;
  days_in_severity: number;
  remedy_class: RemedyClass | null;
  action_taken: AdherenceReviewAction;
  indicators: Record<string, unknown>;
  llm_reasoning: string | null;
  llm_confidence: string | null;
  created_at: string;
}
```
`severity` excludes `NONE` on purpose — the backend only ever writes a row when severity isn't NONE (`models.py:15`), so a client-side value of `NONE` would mean "this row shouldn't exist," not a real state to render.

**`web/src/types/alerts.ts`**
```ts
export type AlertTriggeredBy = "SOS_BUTTON" | "SEVERE_SYMPTOM" | "MISSED_DOSES" | "ADHERENCE_REVIEW";
```

### Step 2 — API client (`web/src/api/`)

**`web/src/api/adherence.ts`** — add one method, same shape as the two already there:
```ts
export const adherenceApi = {
  adherenceSummary: (...) => ...,
  adherenceLogs: (...) => ...,
  adherenceReviews: (patientId: string, page = 1, size = 10) =>
    request<PageResponse<AdherenceReviewDetail>>(`/patients/${patientId}/adherence-reviews`, {
      query: { page, size },
    }),
};
```
Import `AdherenceReviewDetail` alongside the existing `AdherenceLog`/`AdherenceSummary` import from `"../types"`. No new API file, no barrel change beyond that import — `adherenceApi` is already spread into `api` in `web/src/api/index.ts`.

No admin-side client method for `POST /admin/adherence-reviews/run` — nothing in the doctor portal calls admin-only endpoints today (`admin.ts` is doctor-account management only), and there's no UI surface asking for it. Skip unless requested.

### Step 3 — Labels (`web/src/utils/labels.ts`)

Extend the existing `ALERT_TRIGGER` record — do not create a parallel lookup:
```ts
export const ALERT_TRIGGER: Record<AlertTriggeredBy, string> = {
  SOS_BUTTON: "Bệnh nhân bấm SOS",
  SEVERE_SYMPTOM: "Triệu chứng nặng",
  MISSED_DOSES: "Chuỗi bỏ liều",
  ADHERENCE_REVIEW: "Đánh giá tuân thủ hàng đêm",
};
```

Add two new tables + view functions, same pattern as `ALERT_SEVERITY`/`alertSeverityView`:
```ts
export const REVIEW_SEVERITY: Record<AdherenceReviewSeverity, { label: string; tone: Tone }> = {
  MILD: { label: "Nhẹ", tone: "warn" },
  MODERATE: { label: "Trung bình", tone: "warn" },
  SEVERE: { label: "Nghiêm trọng", tone: "crit" },
};

export const REMEDY_CLASS: Record<RemedyClass, string> = {
  RESCHEDULE_TIMING: "Lệch múi giờ sinh hoạt",
  SUSPECTED_SIDE_EFFECT: "Nghi tác dụng phụ",
  DELIBERATE_REFUSAL: "Chủ động từ chối",
  DISENGAGEMENT: "Mất kết nối điều trị",
  EXTERNAL_DISRUPTION: "Gián đoạn ngoại cảnh",
  UNCLEAR: "Chưa rõ nguyên nhân",
};

export function reviewSeverityView(severity: string): { label: string; tone: Tone } {
  return REVIEW_SEVERITY[severity as AdherenceReviewSeverity] ?? { label: severity, tone: "warn" };
}

export function remedyClassLabel(remedyClass: string | null): string {
  if (!remedyClass) return "Chưa phân loại";
  return REMEDY_CLASS[remedyClass as RemedyClass] ?? remedyClass;
}
```
Import `AdherenceReviewSeverity`/`RemedyClass` from `"../types"` at the top of the file alongside the existing `AlertSeverity`/`AlertStatus`/`AlertTriggeredBy` import.

### Step 4 — Prescription form: critical checkbox (`web/src/pages/doctor/components/PrescriptionView.tsx`)

Three edits, all inside the existing structure — no new component:

1. `emptyItem()` (line 49-64) — add `is_critical: false,` to the returned object.
2. Inside the per-item `.rx-fields` block (around line 560, next to "Lưu ý cho bệnh nhân"), add one checkbox:
```tsx
<label className="checkbox-inline">
  <input
    type="checkbox"
    checked={item.is_critical}
    onChange={(event) => patchItem(index, { is_critical: event.target.checked })}
  />
  Thuốc nguy hiểm / quan trọng
</label>
```
Check whether `.checkbox-inline` (or equivalent) already exists in `shell.css` — if the codebase has no checkbox class yet, follow the `label`/`input` bare pattern already used everywhere else in this form (plain `<label><input/>Text</label>`, no wrapper div) rather than introducing a new class.
3. Add a one-line hint under the checkbox row, matching the `rail-note` tone already used elsewhere in this file: `"Đánh dấu thuốc này để hệ thống chỉ báo động khi bệnh nhân bỏ lỡ 3 liều liên tiếp của riêng thuốc này."` — this is the one piece of doctor-facing behavior this checkbox actually changes, and nothing else in the form explains it.

`GuardBanner` at the top of this file already lists HITL constraints (`GuardBanner title="HITL bắt buộc..."`) — no change needed there, `is_critical` doesn't add a new guardrail, it's a plain data field.

### Step 5 — Alert source distinction (`web/src/pages/doctor/components/AlertsView.tsx`)

`alertTriggerLabel()` already fixes the raw-string display once Step 3 lands — that alone is enough for correctness. Optionally (visual-only, matches this session's earlier mockup), branch on `alert.triggered_by_type === "ADHERENCE_REVIEW"` in the `alert-body` block (line 85-87) to render the message inside a distinct block rather than the plain `<p className="alert-sub">`, signaling "this text is LLM-authored reasoning" vs. a rule-authored message. This is presentation-only, safe to defer to a follow-up pass — Step 3 is the functional fix.

### Step 6 — Patient detail: review timeline (`web/src/pages/doctor/components/PatientDetailPage.tsx`)

This is the only genuinely new UI surface.

1. Add state: `const [reviews, setReviews] = useState<AdherenceReviewDetail[]>([]);` alongside `logs`/`alerts`/`surveys`.
2. In `refresh()` (line 89-117), add `api.adherenceReviews(patientId, 1, 10)` to the existing `Promise.all` batch (it's already read-only and already-scoped to this patient, same access rule as `adherenceLogs`/`healthSurveys` right next to it) and `setReviews(reviewsResult.content)`.
3. In the `"health"` tab block (line 211), the `.detail-two-col` currently holds exactly 2 cards ("Nhật ký tuân thủ", "Khảo sát & triệu chứng"). Add a third full-width card **above** that row (not inside the two-col grid — a timeline with per-entry reasoning text needs more width than a half-column), following the same `<article className="card"><div className="card-head"><h2>...</h2></div><div className="card-body ...">...</div></article>` shape used by every other card in this file:

```tsx
{tab === "health" && (
  <>
    <article className="card">
      <div className="card-head"><h2>Đánh giá tuân thủ hàng đêm</h2></div>
      <div className="card-body detail-list">
        {reviews.map((review) => {
          const severity = reviewSeverityView(review.severity);
          return (
            <div className="detail-row" key={review.id}>
              <span>
                <b className={severity.tone}>{severity.label}</b>
                <small>{formatDate(review.review_date)} · Ngày {review.days_in_severity} ở mức này</small>
              </span>
              <span>
                {remedyClassLabel(review.remedy_class)}
                {review.llm_reasoning && <small>{review.llm_reasoning}</small>}
              </span>
            </div>
          );
        })}
        {reviews.length === 0 && <EmptyState>Chưa có đánh giá tuân thủ nào.</EmptyState>}
      </div>
    </article>
    <div className="detail-two-col">
      {/* existing "Nhật ký tuân thủ" + "Khảo sát & triệu chứng" cards, unchanged */}
    </div>
  </>
)}
```
This reuses `.detail-row`/`.detail-list` exactly as the adjacent adherence-log card does — no new CSS class needed for the base layout. The only new visual idea (an "AI" marker distinguishing `llm_reasoning`/`remedy_class` from `severity`/`action_taken`) is optional polish, not required for the data to be correct and readable; if wanted, it's a single small `<span className="pill">AI</span>`-style chip next to the remedy label, styled from tokens already in `tokens.css` (no new color needed — reuse `--accent` rather than inventing a 7th semantic color, since `crit`/`warn`/`ok` are reserved for severity and must not be reused for authorship).

### Step 7 — Roster hint (`web/src/pages/doctor/components/PatientTable.tsx`) — optional, needs a backend decision first

Showing "this patient has an active escalating streak" on the roster needs `days_in_severity` per patient, but `GET /dashboard/patients` (`DashboardPatientListItem`, `types/dashboard.ts:6-12`) doesn't return it — only `open_alerts_count`. Two ways to get it, don't guess which without asking:
- extend `DashboardPatientListResponse` backend-side with a `latest_review_days_in_severity` field (touches `src/modules/dashboard/repository.py`/`schemas.py`, outside this plan's frontend-only scope), or
- skip it — `open_alerts_count` already goes up for a `DOCTOR_WARNING`/`DOCTOR_ALERT` review via the alert it creates, so the roster already reflects an active review indirectly, just without the streak-length detail.

Recommendation: skip for the first pass. Step 6 already surfaces the full streak history on the page a doctor opens when they act on the alert; the roster doesn't need to duplicate it before there's a concrete ask for it.

## 3. Build order

1. Types (Step 1) — nothing compiles against the new fields without this, do first.
2. API client (Step 2) — depends on Step 1's `AdherenceReviewDetail`.
3. Labels (Step 3) — depends on Step 1's new unions; unblocks both Step 5 (alert label) and Step 6 (severity/remedy display) immediately, and is a pure `chore` that removes today's live bug (raw `"ADHERENCE_REVIEW"` string shown to doctors) with no other prerequisite — do this one first if shipping incrementally.
4. Step 4 (critical checkbox) is independent of 1–3 except for its own Step-1 type change; can ship separately/first if `is_critical` is more urgent than the review UI.
5. Steps 5–6 depend on 1–3; do 6 before 5 since 6 is the primary deliverable and 5 is presentation polish on an already-functional alert card.
6. Step 7 deferred pending a decision on whether it's worth a backend field addition.

## 4. Verification

- `PrescriptionView.tsx`: create a prescription with one critical item, approve it, confirm `GET /prescriptions/{id}` echoes `is_critical: true` on that item (already covered by existing backend tests; frontend check is just "the checkbox round-trips").
- `PatientDetailPage.tsx`: for a patient with an existing `adherence_reviews` row (seed via `POST /admin/adherence-reviews/run` against a test patient with a bad-adherence week, per `router.py:56`), confirm the health tab renders severity/remedy/reasoning without a console error on `llm_reasoning: null`/`remedy_class: null` (silenced-patient rows, `_persist_one`, action_taken=NONE) — `remedyClassLabel(null)` must not throw.
- `AlertsView.tsx`: confirm an `ADHERENCE_REVIEW` alert shows "Đánh giá tuân thủ hàng đêm" instead of the raw enum string.
