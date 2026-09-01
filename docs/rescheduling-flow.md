# Luồng hoạt động Chatbot ↔ Planning Agent — Rescheduling

> Nguồn: `src/agents/graph.py`, `src/agents/nodes/rescheduling_node.py`, `src/agents/nodes/semantic_planner_node.py`, `src/agents/nodes/scope_guard_node.py`, `src/modules/agents/service.py`, `src/modules/agents/planner.py`, `src/agents/planning_graph.py`
> Cập nhật: 2026-09-02 — sync với develop (thêm `medication_catalog`, `semantic_output_reviewer`), pure-rule (đã bỏ LLM grouping)

---

## 1. Tổng quan — Hai graph tách biệt

```mermaid
graph TB
    User --> ChatSvc[ChatService.handle_text_chat<br/>src/modules/agents/service.py:816]
    ChatSvc --> ChatGraph[Chat Agent<br/>src/agents/graph.py:79<br/>sync, per-message]
    ChatGraph -->|report_meal_shift| ReschedNode[rescheduling_node<br/>src/agents/nodes/rescheduling_node.py:355]
    ReschedNode -->|report_routine_deviation tool| Backend[POST /patients/id/routine-overrides<br/>src/agents/tools/schedule_tools.py:56]
    Backend --> Svc[SchedulingService.report_routine_deviations<br/>src/modules/agents/service.py:182]
    Svc -->|AgentRun RESCHEDULING_AGENT| Celery[Celery send_task<br/>agents.generate_schedule]
    Celery --> PlanGraph[Planning Agent<br/>src/agents/planning_graph.py:13<br/>async, 3-phase]
    PlanGraph --> DB[(scheduled_doses<br/>PostgreSQL)]
    DB --> WS[WS schedule.updated<br/>src/modules/agents/service.py:665]
```

- **Chat Graph** sync, trả lời ngay; **Planning Graph** async qua Celery, poll `GET /agent-runs/{id}`.

---

## 2. Chat Graph — Điều hướng intent (sau merge develop)

```mermaid
graph TD
    Start([HumanMessage]) --> Safety[safety_guard_node<br/>src/agents/nodes/safety_guard_node.py<br/>2 lớp: keyword + LLM structured EmergencyAssessment]
    Safety -->|escalated/blocked| OutG[output_guard]
    Safety -->|pass| Scope[scope_guard_node<br/>src/agents/nodes/scope_guard_node.py]
    Scope -->|out_of_scope/abusive| OutG
    Scope --> Semantic[semantic_planner_node<br/>LLM-first<br/>src/agents/nodes/semantic_planner_node.py:40]
    Semantic -->|use_legacy_classifier| Legacy[classify_intent_node]
    Semantic -->|valid| Guard[plan_guard_node<br/>src/agents/nodes/plan_guard_node.py:63]
    Guard -->|write_not_composable<br/>hoặc invalid| Clarify[clarification_node]
    Guard -->|valid| Intent{intent}
    Intent -->|report_meal_shift| Resched[rescheduling]
    Intent -->|ask_drug_catalog| Catalog[medication_catalog]
    Intent -->|ask_drug_info| DrugRag[drug_rag]
    Intent -->|ask_schedule| TodaySched[today_schedule]
    Intent -->|ask_next_dose| NextDose
    Intent -->|general/other| AgentNode[agent ReAct]
    Resched --> OutG
    Catalog --> OutG
    DrugRag --> OutG
    TodaySched --> OutG
    NextDose --> OutG
    AgentNode --> OutG
    OutG --> Reviewer[semantic_output_reviewer<br/>src/agents/nodes/semantic_output_reviewer_node.py]
    Reviewer --> END
```

- `develop` thêm `medication_catalog` và `semantic_output_reviewer` (review output sau `output_guard`).
- `plan_guard` hiện chặn `write_not_composable` (fix bug #3).

---

## 3. Rescheduling Node — 4 nhánh kết quả

```mermaid
graph TD
    Entry[handle_reschedule_request<br/>text + patient_id + client_date<br/>src/agents/nodes/rescheduling_node.py:287] --> Extract[extract_routine_deviation<br/>LLM structured output<br/>RoutineDeviationExtraction<br/>src/agents/nodes/rescheduling_node.py:126]

    Extract -->|LLM exception| AskRepeat[needs_clarification<br/>_EXTRACTION_FAILED_MESSAGE]

    Extract --> Ev{event}
    Ev -->|out_of_scope| Refused[refused<br/>_REFUSAL_MESSAGE<br/>HITL - liên hệ bác sĩ]
    Ev -->|busy_window| Busy[_handle_busy_window<br/>src/agents/nodes/rescheduling_node.py:190]
    Ev -->|unclear<br/>hoặc new_time=null| Ask1[needs_clarification<br/>clarifying_question<br/>+ gợi ý recent_times]
    Ev -->|routine_deviation<br/>+ new_time HH:MM| Tool[report_routine_deviation<br/>tool invoke<br/>src/agents/tools/schedule_tools.py:56]

    Busy --> BusyCheck{parse busy_start/end<br/>+ client_date}
    BusyCheck -->|thiếu giờ/client_date| AskBusy[needs_clarification / failed]
    BusyCheck -->|ok| Fetch[fetch schedules<br/>asyncio.gather<br/>2 ngày nếu qua đêm<br/>src/agents/nodes/rescheduling_node.py:222]
    Fetch --> Filter[lọc doses PENDING<br/>trong window datetime<br/>window_start<=sched_dt<=window_end<br/>src/agents/nodes/rescheduling_node.py:239]
    Filter -->|không có cữ| NoDose[needs_clarification<br/>không có cữ trong khung]
    Filter -->|có cữ trùng| AskReplace[needs_clarification<br/>liệt kê cữ + hỏi giờ thay thế]

    Tool --> Backend{Backend POST<br/>/routine-overrides}
    Backend -->|BackendAPIError<br/>hoặc duplicate anchor| Failed[failed<br/>lịch không đổi]
    Backend -->|success| Rescheduled[rescheduled<br/>agent_run_id RUNNING<br/>Planning sẽ rải lại]

    AskRepeat --> Out
    Refused --> Out
    Ask1 --> Out
    AskBusy --> Out
    NoDose --> Out
    AskReplace --> Out
    Failed --> Out
    Rescheduled --> Out
```

### Schema `RoutineDeviationExtraction`

| field | type | ví dụ |
|-------|------|-------|
| `event` | `routine_deviation\|busy_window\|unclear\|out_of_scope` | `routine_deviation` |
| `anchor` | `breakfast/lunch/dinner/sleep\|null` | `lunch` |
| `new_time` | `HH:MM\|null` | `14:00` |
| `busy_start/end` | `HH:MM` | `14:00 / 17:00` |
| `target_day` | `today/tomorrow/day_after_tomorrow\|null` | `tomorrow` |
| `clarifying_question` | `string\|null` | `Bạn ăn trưa lúc mấy giờ?` |

Giới hạn `target_day` chỉ `0..2` (`_DAY_OFFSETS`); `3-4 hôm sau` -> `unclear`.

---

## 4. Planning Agent — 3-phase (pure-rule)

```mermaid
graph LR
    subgraph Phase1 - Snapshot
        Gate[planning_input_gate_node]
        Norm[planning_normalize_node]
        Gate --> Norm
    end
    subgraph Phase2 - Draft
        Gen[planning_generate_candidate_node<br/>expand_schedule pure code]
    end
    subgraph Phase3 - Commit
        Lock[planning_lock_and_revalidate_node<br/>FOR UPDATE]
        Group[planning_apply_grouping_node<br/>pass-through]
        Persist[planning_persist_node]
        Audit[planning_audit_node]
        Lock --> Group --> Persist --> Audit
    end
    Norm --> Gen --> Lock
```

- `expand_schedule()` `src/modules/agents/planner.py:399`: 4 slot `morning->breakfast` ...
- Validators -> Fail => `NEEDS_REVIEW`

---

## 5. Bảng Case

### 5.1 Rescheduling (chat)

| # | Câu | Extract | Kết quả |
|---|-----|---------|---------|
| C1 | `Hôm nay ăn trưa muộn, dời qua 14h` | `lunch 14:00 today` | `rescheduled` |
| C2 | `Tôi ăn muộn` | `unclear lunch` | `needs_clarification` + gợi ý recent_times |
| C3 | `Tối nay 22h-2h bận họp` | `busy_window 22:00-02:00` | `needs_clarification` (gather 2 ngày, window datetime) |
| C4 | `Chiều 14h-17h bận` không có cữ | `busy_window` | `không có cữ` |
| C5 | `Bỏ cữ tối` / `tăng liều` | `out_of_scope` | `refused` |
| C6 | `Lùi thuốc này 9h30` | `out_of_scope` (không anchor) | `refused` — phải nói `ăn sáng/trưa/tối/ngủ` |
| C7 | `Ngày kia ăn sáng 9h30` | `breakfast 09:30 day_after_tomorrow` | `rescheduled` |
| C8 | `3 hôm sau bận` | `unclear` (ngoài 0..2) | `needs_clarification` |
| C9 | LLM timeout | exception | `needs_clarification` |
| C10 | `409 run in progress` | `routine_deviation` hợp lệ | `failed` |

### 5.2 Scope guard (mới)

| Câu | Whitelist | Kết quả |
|-----|-----------|---------|
| `h t mới ăn tối xong` | `an toi xong` thiếu `muon` -> `out_of_scope` LLM | `Mình chỉ hỗ trợ về thuốc...` `src/agents/nodes/scope_guard_node.py:17` |
| `ăn tối muộn 20h30` | `an toi muon` -> `medication` | pass -> rescheduling |

---

## 6. Sequence — C1 thành công

```mermaid
sequenceDiagram
    participant U as User
    participant C as ChatService
    participant G as Chat Graph
    participant R as rescheduling_node
    participant T as Tool
    participant API as POST /routine-overrides
    participant S as SchedulingService
    participant Cel as Celery
    participant P as Planning Graph
    U->>C: "ăn trưa muộn 14h"
    C->>G: agent.ainvoke
    G->>R: report_meal_shift
    R->>T: report_routine_deviation
    T->>API: POST
    API->>S: create AgentRun + upsert
    S->>Cel: send_task
    Cel->>P: execute_run
    P->>P: snapshot->draft->commit
```
