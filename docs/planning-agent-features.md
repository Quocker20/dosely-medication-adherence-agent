# Planning Agent — Tính năng hiện có

> Nguồn: `src/agents/planning_graph.py`, `src/modules/agents/service.py`, `src/modules/agents/planner.py`, `src/modules/agents/grouping.py`, `src/core/config.py`  
> Cập nhật: 2026-09-01

## 1. Tổng quan

Planning Agent là **LangGraph tách biệt** với Chat Agent (`src/agents/planning_graph.py:13`), chạy **bất đồng bộ qua Celery** (`src/modules/agents/service.py:80`, `src/modules/agents/tasks.py:79`).

- Client gọi `POST /patients/{id}/schedules/generate` hoặc `POST /patients/{id}/schedules/reschedule` → backend trả `202 Accepted + agent_run_id` ngay.
- Worker thực thi, client poll `GET /agent-runs/{id}`.
- Cùng một graph cho cả **Planning** và **Rescheduling**, phân biệt bằng flag `is_reschedule` (`src/agents/planning_state.py:25`).

Nguyên tắc: **Deterministic core, AI-assisted planning** — LLM chỉ đề xuất, validator bằng code là cổng cuối trước khi persist.

## 2. Pipeline 3-phase

Định nghĩa tại `src/agents/planning_graph.py:14-49`:

```
Phase 1 - Snapshot (read không lock):
  planning_input_gate_node → planning_normalize_node

Phase 2 - Draft (pure rule, không network):
  planning_generate_candidate_node (expand_schedule deterministic)

Phase 3 - Commit (1 transaction, có lock):
  planning_lock_and_revalidate_node → planning_apply_grouping_node (pass-through) → planning_persist_node → planning_audit_node
```
> **Update 2026-09-01 — đã bỏ gom nhóm (pure rule):** `planning_generate_candidate_node` không còn gọi LLM, `planning_apply_grouping_node` luôn pass-through `naive_rows_fresh`. Mỗi cữ một thông báo riêng.

| Node | File | Chức năng |
|------|------|-----------|
| `planning_input_gate_node` | `src/agents/nodes/planning_input_gate_node.py:13` | Đọc `patient_context` + `APPROVED items` không lấy lock, fail nếu không có item → `PlanningNeedsReviewError` |
| `planning_normalize_node` | `src/agents/nodes/planning_normalize_node.py:21` | Chuyển ORM → `PlannableItem` + `RoutineTimes`, check `validate_frequency_guardrails` |
| `planning_generate_candidate_node` | `src/agents/nodes/planning_generate_candidate_node.py:1` | `expand_schedule()` thuần, **pure rule** — không LLM |
| `planning_lock_and_revalidate_node` | `src/agents/nodes/planning_lock_and_revalidate_node.py:23` | Re-read `for_update=True`, rebuild toàn bộ schedule bằng code |
| `planning_apply_grouping_node` | `src/agents/nodes/planning_apply_grouping_node.py:1` | Pass-through (đã bỏ gom nhóm) |
| `planning_persist_node` | `src/agents/nodes/planning_persist_node.py:11` | `bulk_insert_doses()`, nếu reschedule thì `delete_future_pending` trước |
| `planning_audit_node` | `src/agents/nodes/planning_audit_node.py:12` | Tạo `input_hash`/`output_hash` HMAC, không log PHI |

## 3. Deterministic Core — `src/modules/agents/planner.py:1`

### 3.1 Expand Schedule

`expand_schedule()` (`src/modules/agents/planner.py:399`) — hàm thuần, không DB/IO:

- 4 slot cố định (`src/modules/agents/planner.py:17`):
  - `morning_dose → breakfast`
  - `noon_dose → lunch`
  - `evening_dose → dinner`
  - `bedtime_dose → sleep (-30 phút)`
- Offset theo `meal_relation`: `BEFORE_MEAL=-30`, `AFTER_MEAL=+30`, `WITH_MEAL=0` (`src/modules/agents/planner.py:31`)
- Rolling window `[today, today + schedule_horizon_days]` (`default 14` — `src/core/config.py:136`) và `max_treatment_days=180` (`src/core/config.py:107`)
- `interval_days` (uống cách ngày) phase-locked vào `start_date` (`src/modules/agents/planner.py:214`)
- Xử lý `sleep` sau nửa đêm: `sleep < 12:00` → tính sang ngày hôm sau (`src/modules/agents/planner.py:248`)

### 3.2 Validators (cổng cuối, không phải LLM)

| Validator | File:line | Mô tả |
|-----------|-----------|-------|
| `validate_prescription_inputs` | `src/modules/agents/planner.py:154` | Reject item không có slot, dose ≤0, interval ≤0 |
| `validate_frequency_guardrails` | `src/modules/agents/planner.py:174` | `doses/day ≤ max_frequency_per_day=4` (`src/core/config.py:106`) |
| `_validate_min_gap` | `src/modules/agents/planner.py:278` | Các slot trong ngày cách nhau ≥ `min_dose_gap_minutes` (default 0) |
| `_validate_cross_day_gaps` | `src/modules/agents/planner.py:297` | Các liều liên tiếp của cùng item cách nhau ≥ `minimum_interval_minutes` |
| `validate_candidate_boundaries` | `src/modules/agents/planner.py:316` | Reschedule không vi phạm gap với retained doses |
| `reconcile_reschedule_candidates` | `src/modules/agents/planner.py:352` | Chỉ replace `PENDING future`, giữ `TAKEN/SKIPPED/MISSED/in-progress` |

Fail → `PlanningNeedsReviewError` (và subclass `MissingRoutineAnchorError`, `ScheduleConstraintError`, `InvalidPrescriptionTimingError`, `FrequencyGuardrailError`) → giữ lịch cũ, trả `NEEDS_REVIEW` (`src/modules/agents/service.py:629`).

## 4. Gom nhóm thông báo — đã bỏ (pure rule)

> Đã bỏ LLM grouping. `planning_generate_candidate_node` + `planning_apply_grouping_node` hiện pure deterministic — mỗi cữ một `notification_group_id=None`. Lý do: validator `apply_dose_grouping()` `src/modules/agents/grouping.py:76` bắt **cùng exact timestamp + meal_relation** nên LLM chỉ chọn index thừa, không thêm giá trị, nhưng tốn `15s timeout` + stale-hash fallback. Nếu sau này cần gom trong window `30p`, hãy implement grouping pure-rule `groupby(current_scheduled_at, meal_relation)` thay vì gọi LLM.

## 5. Rescheduling — chỉ dời giờ

- `lock_reschedule_window()` + `get_active_overrides()` (`src/agents/nodes/planning_lock_and_revalidate_node.py:44`)
- `reconcile_reschedule_candidates()` (`src/modules/agents/planner.py:352`): giữ authoritative rows, chỉ replace `PENDING future`
- Không đổi `dose/frequency/route/treatment_duration` — vi phạm là bug guardrail
- Hỗ trợ `DayAnchorOverrides` per-day (`src/modules/agents/planner.py:72`): `RoutineOverride` cho từng `anchor/day` trong window `[today, today+horizon]`

## 6. Trigger

`SchedulingService` (`src/modules/agents/service.py:80`):

| Trigger | Endpoint / Caller | File:line | Role |
|---------|-------------------|-----------|------|
| Manual generate | `POST /patients/{id}/schedules/generate` | `src/modules/agents/service.py:109` | Doctor (phải có prescription của mình) |
| Manual reschedule | `POST /patients/{id}/schedules/reschedule` | `src/modules/agents/service.py:142` | Patient (self) |
| Routine deviation (batch) | `report_routine_deviations()` | `src/modules/agents/service.py:182` | Patient — upsert nhiều `RoutineOverride` + tạo run trong 1 transaction |
| Cancel override | `cancel_routine_override()` | `src/modules/agents/service.py:285` | Patient — xóa override, fallback về routine cố định |
| Autoschedule approve | `request_autoschedule(PRESCRIPTION_APPROVED)` | `src/modules/agents/service.py:350` | Worker — `prescription_autoschedule_enabled=true` (`src/core/config.py:126`) |
| Autoschedule routine | `request_autoschedule(ROUTINE_UPDATED)` | `src/modules/agents/service.py:350` | Worker — khi patient đổi `patient_routines` |

## 7. Concurrency & Audit

- **Single-flight**: `uq_agent_runs_one_running` — 1 run/patient, `IntegrityError → 409 Conflict` (`src/modules/agents/service.py:136`)
- **Lease + claim_token**: `claim_run()` + `renew_claim()` với `planning_run_lease_seconds=180s` (`src/core/config.py:120`, `src/modules/agents/service.py:545`)
- **Persist**: `delete_future_pending` nếu reschedule + `bulk_insert_doses()` (`src/agents/nodes/planning_persist_node.py:17`)
- **Audit** (`src/agents/nodes/planning_audit_node.py:12`):
  - `input_hash = HMAC(schedule_rows, jwt_secret, include_groups=false)`
  - `output_hash = HMAC(schedule_rows, jwt_secret, include_groups=true)` (`src/modules/agents/grouping.py:49`)
  - `candidate_source`: `deterministic | llm_grouped | deterministic_fallback_*` (`src/agents/planning_state.py:13`)
  - `llm_model_version`, `prompt_version`, `latency_ms`, `error_code` lưu vào `agent_runs`
- **Side-effect**: publish `schedule.updated` qua WebSocket + `invalidate_prefix("dash:patients")` (`src/modules/agents/service.py:665`)

## 8. Đọc lịch

| Method | File:line | Mô tả |
|--------|-----------|-------|
| `get_schedule(patient_id, target_date)` | `src/modules/agents/service.py:402` | Lọc theo timezone patient, `[00:00, 00:00+1d)` UTC |
| `get_next_dose_for_patient()` | `src/modules/agents/service.py:444` | Trả `UPCOMING | NO_SCHEDULE | NO_UPCOMING` |
| `get_today_schedule_for_patient()` | `src/modules/agents/service.py:485` | Dùng `now.UTC → patient timezone` |
| `get_run_status(agent_run_id)` | `src/modules/agents/service.py:511` | Poll trạng thái run |

## 9. Config liên quan

`src/core/config.py:104-136`:

| Key | Default | Mô tả |
|-----|---------|-------|
| `max_frequency_per_day` | `4` | Guardrail số cữ/ngày |
| `max_treatment_days` | `180` | Trần treatment |
| `min_dose_gap_minutes` | `0` | Fallback khi item không set `minimum_interval_minutes` |
| `schedule_horizon_days` | `14` | Rolling window sinh lịch |
| `planning_agent_timeout_ms` | `15000` | Timeout LLM grouping |
| `planning_run_lease_seconds` | `180` | Lease claim |
| `planning_grouping_enabled` | `false` | Bật/tắt LLM grouping |
| `notification_group_window_minutes` | `30` | Window gom nhóm |
| `prescription_autoschedule_enabled` | `true` | Tự trigger sau approve |
