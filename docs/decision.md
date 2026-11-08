# Chatbot hardening: decisions

Scope: chat-only features, tool calling and safety guardrails in `src/chatbot/`. RAG content and knowledge sync are out of scope (RAG code stays untouched unless a non-RAG fix requires it).
Branch: `claude/chatbot-hardening` (from `main` 377bb44).
Rule: change user-visible behavior only when needed for correctness or safety. Every decision taken during the work is logged here, one line each.

## Roadmap

| Phase | Work | Mode |
|---|---|---|
| 0 | Baseline: 16 chatbot tests fail (graph 9, medication_mapping 3, safety_guard 2, scheduled_drug_info 1, scope_guard 1); 242 pass | Orchestrator |
| 1 | Fix the 12 non-RAG failures (graph, safety_guard, scope_guard). RAG-related failures (medication_mapping, scheduled_drug_info) only if the cause is not knowledge data | 1 agent |
| 2a | Safety lane: Red Alert from chat with anti-spam, keyword matching on folded text with negation and severity tiers, recent-turn context for the LLM layer, scope and safety LLM in parallel | test-writer agent, then impl agent |
| 2b | Chat and tool lane: `agent_node` prompt matches no-tool reality, remove error-text leaks, remove dead `classify_intent` node from graph, read-only adherence stats intent, output_guard and abuse-list boundary fixes | test-writer agent, then impl agent |
| 3 | Merge lanes, full test run (chatbot + backend) | Orchestrator |
| 4 | Verify agent: conflicts between lanes and with backend (SOS service SEC-09, alert service, idempotency, tool_authorization, chat_service) | 1 agent |
| 5 | Fix findings, push branch | agent + orchestrator |

## Decisions

- D01: Work on branch `claude/chatbot-hardening`; push the branch, do not merge into `main` (chatbot belongs to a teammate; the merge needs a human look).
- D02: `record_dose_action` via chat is NOT added. Dose marking already exists in the app UI; a chat write path adds an injection surface and changes how users act. Keep the `fabricated_medication_status` block.
- D03: Bulk consolidation of fixed reply strings into one module is skipped: touches every node, high merge-conflict risk, no behavior gain.
- D04: Live LLM eval scripts in `eval/` are not run (cost, needs a real API key). Verification is by unit tests with mocked LLM.
- D05: Executing agents use Sonnet 5.5 at medium effort or lower.
- D06: Phase 2 order: one test agent writes failing tests for both lanes first (TDD), then two impl agents run in parallel in isolated worktrees, merged by the orchestrator.
- D07 (Red Alert anti-spam): backend already dedupes by Idempotency-Key and SEC-09 soft limit (5 per minute returns the existing alert). That is not enough for chat: today's key includes the matched keyword, so rewording inside 5 minutes makes a new alert, and a 30-minute conversation about chest pain would page every 5 minutes. Chat adds a per-patient Redis gate `SET NX EX 1800` (one agent-raised SEVERE_SYMPTOM alert per patient per 30 minutes); the idempotency key uses the category `SEVERE_SYMPTOM`, not the keyword. Redis down: fail-open (send; backend dedupe still applies). Send failure never blocks the reply.
- D08: Alert severity: life-threatening keyword tier CRITICAL; other keywords and LLM-only detection HIGH. Message carries the patient's own words (backend truncates at 500 chars), metadata `source=agent_auto_detect`, `conversation_id`, `detector` (keyword or llm).
- D09: All current emergency keywords still escalate the reply (no keyword removed). Matching improves: negation right before the keyword ("không", "chưa", "hết", "không còn") cancels that match; unaccented input matches multi-syllable keywords only (single-syllable ones like "ngất", "xỉu" stay accent-exact because "xiu"/"ngat" collide with common words).
- D10: Reply after escalation: keep the existing fixed safe reply; append one sentence that the doctor has been notified only when the alert call succeeded (or an alert already exists in the 30-minute window).
- D11: The emergency LLM layer sees the last 3 patient messages for context; the keyword layer still judges only the current message (avoids re-escalating every later turn).
- D12: `trigger_red_alert` must pass `authorize_patient_write(..., intent="emergency")` like other write tools.
- D13: `semantic_output_reviewer` skips the LLM review for deterministic-data answers (schedule, next dose, current medications, recent adverse event, clarification, fixed refusals); LLM review stays for free-text LLM answers. Saves one LLM call and avoids false rejection of correct backend data.
- D14: Read-only adherence stats intent added (questions like "tuần này tôi uống đủ thuốc chưa"), using the existing `GET /patients/{id}/adherence` endpoint. No write path.
- D15: Rescheduling writes keep no extra confirmation step (the patient states the time directly; adding a prompt changes UX).
- D16: Escalation replies are rewritten by the refusal LLM in output_guard, so the "doctor notified" sentence (D10) is appended deterministically after that rewrite, driven by a state flag set in safety_guard; the LLM is never told an alert was sent.
- D17: `output_guard_node.py` is shared by both lanes (S: alert-notice append, C: directive regex). Orchestrator resolves the merge.
- P1-01: test_graph.py was stale, not the code: classify_intent is no longer on the main path (semantic_planner -> plan_guard); tests now mock semantic_planner and route-test `plan_guard`. Planner/plan failure routes to `clarification` by design, so the legacy-classifier route test now asserts that.
- P1-02: Refusal/escalation replies are now generated by `refusal_response.get_llm` (fixed texts are only the fail-safe). Graph tests mock that LLM and assert `escalated`/`safety_blocked`/`scope_blocked`/`refusal_reason` plus "planner and chat LLM not called" (safety intent kept); no reply text changed.
- P1-03: safety_guard layer 2 now uses structured output plus a verification pass, and policy reasons are plain codes (`DOSE_CHANGE`); tests updated to match. Chatbot Red Alert is still not wired (nothing calls `trigger_red_alert`); no alert assertion existed in these tests.
- P1-04: scope_guard test moved to a non-keyword message for the LLM path (World Cup is now a deterministic block with `refusal_reason=outside_dosely_scope`, covered by a new test). Left failing, need the formulary index (chromadb collection missing): test_medication_mapping (3), test_scheduled_drug_info_node (1). Note: `classify_intent` node is orphaned in graph.py (no inbound edge); removal is planned in phase 2b.
- C-D01: Removed orphaned classify_intent node/edges from graph.py; kept _route_after_classify_intent (used by plan_guard routing and tests) and classify_intent_node.py (imported by tests).
- C-D02: Chat prompt no longer names uncallable tools; tells model it has no verified drug data. Updated test_graph.py addressing assertion (it required the removed "không cần gọi tool hồ sơ" phrase, contradicting C-01) and test_graph_routing_map.py (added adherence_stats).
- C-D03: Rescheduling failure messages (exception and backend-rejection detail) no longer include raw text; class name only is logged.
- C-D04: Reviewer skips LLM for deterministic intents incl. new ask_adherence_stats; medical grounding fallback runs first and is unchanged.
- C-D05: get_adherence_stats reads GET /patients/{id}/adherence with from/to = 7 days ending at client_date (inclusive); percent computed as round(taken/total*100) from counts (backend adherence_rate is 0-100; ignored); errors give a generic Vietnamese line.
- C-D06: Dangerous directive is a subject+modal+action regex plus a negation lookbehind ("không/đừng/chớ" within 16 chars); "bác sĩ" is excluded as a subject.

- S-D01: Red Alert send path is `dispatch_red_alert` in safety_tools (authorize -> optional Redis gate -> post); `trigger_red_alert` tool and the chat node share it. Gate is released if the send fails so the next turn can retry.
- S-D02: Authorization failure is logged at CRITICAL (not warning) with patient_id and exception class only; an existing test captures at CRITICAL and an unsent emergency alert warrants it. Tool text keeps "[LỖI NGHIÊM TRỌNG]" but no raw exception.
- S-D03: Keyword tiers: CRITICAL = breathing (except khò khè), chest, stroke, consciousness, bleeding, lip/tongue/throat swelling, self-harm, overdose; HIGH = thở khò khè, heart palpitations, rash/hives, sưng mặt, severe abdominal/head pain, sốt cao. Needs clinician review.
- S-D04: Negation = không/chưa/hết/chẳng/chả directly before the keyword, optionally with one filler (còn, bị, hề, có, thấy, phải). Folded matching skips single-syllable keywords and also "tự tử" (unaccented "tu tu" = "từ từ").
- S-D05: safety_guard runs the emergency LLM and the scope LLM via asyncio.gather only after deterministic checks found nothing, and only when scope_guard would not short-circuit (`needs_scope_llm`). Result goes in state `scope_prefetch` (rewritten every turn, None on escalation); scope_guard reuses it. Graph topology unchanged.
- S-D06: Abusive markers are matched on token boundaries against folded text (dropped accented duplicates, they never matched folded text anyway).
- S-D07: Test fix: `test_safety_and_scope_llms_run_concurrently` also patches the output reviewer's `get_llm`; unpatched, the reviewer made a real OpenAI call (~1.3s with the test key) that drowned the 0.5s timing assertion.
- F-D01: Negation never crosses clause punctuation: `_tokens` emits a break token for . , ; : ! ? newline; the 2-token negation window stops at it ("Không. Đau ngực quá" escalates).
- F-D02: `dispatch_red_alert` releases the gate on BaseException too (release capped at 1s, errors swallowed) and re-raises CancelledError; no stale gate after a cancelled send.
- F-D03: On escalated turns output_guard falls back to the fixed emergency reply (not `_SAFE_FALLBACK`) when the refusal LLM fails, and appends the fixed 115 sentence (`CALL_115_SENTENCE`, shared with safety_guard) if the LLM text lacks "115"; the doctor-notified notice is appended after.
- F-D04: Adherence percent = round(taken/total*100) from counts; `adherence_rate` is ignored (backend scale is 0-100). Replaces the C-D05 wording.
- F-D05: Anti-spam gate is per (patient, severity): CRITICAL is blocked only by a CRITICAL gate, HIGH by a HIGH or CRITICAL gate, so HIGH then CRITICAL within 30 min sends both. Idempotency category is `SEVERE_SYMPTOM:<SEVERITY>` (key differs by severity, so the backend does not replay the HIGH alert). Same-severity rewording still collapses. Supersedes the single gate in D07/S-D01.
- F-D06: Added CRITICAL keywords: không thở được, không thể thở, thở không nổi, ngưng thở, bất tỉnh, đột quỵ. Keywords that contain "không" still match (negation only looks before the keyword's first token). No bare "quá liều" keyword (questions like "uống vậy có quá liều không" would false-alarm); left to the LLM layer.
- F-D07: Chatbot tests cannot reach the network: `tests/test_chatbot/conftest.py` autouse fixture blocks non-loopback socket connects (guarded by test_network_guard.py). LLM-dependent tests patch their LLMs explicitly (scope LLM in safety specs, reviewer in graph tests); concurrency test asserts start/end event overlap, not wall-clock.
- F-D08: Alert notice says "bác sĩ của bạn" although alerts go to the shared doctor dashboard (SEC-01, intentional); accurate enough, no change.
