# Dosely Chatbot Full Evaluation

- Passed: **106/106**
- Pass rate: **100.00%**
- Skipped: **0**
- Average latency: **146.5 ms**
- P95 latency: **736.61 ms**

## Results by layer

| Layer | Passed | Evaluated | Skipped | Pass rate | P95 latency (ms) |
|---|---:|---:|---:|---:|---:|
| emergency_keyword | 10 | 10 | 0 | 100.00% | 0.02 |
| explain_my_medications | 12 | 12 | 0 | 100.00% | 1.34 |
| intent | 12 | 12 | 0 | 100.00% | 0.3 |
| medication_policy | 27 | 27 | 0 | 100.00% | 0.1 |
| memory_isolation | 2 | 2 | 0 | 100.00% | 0.02 |
| next_dose | 5 | 5 | 0 | 100.00% | 0.39 |
| output_guard | 8 | 8 | 0 | 100.00% | 0.07 |
| personal_medications | 6 | 6 | 0 | 100.00% | 2.26 |
| rag | 6 | 6 | 0 | 100.00% | 7922.72 |
| scope_guard | 8 | 8 | 0 | 100.00% | 1937.61 |
| today_schedule | 4 | 4 | 0 | 100.00% | 11.12 |
| tool_policy | 6 | 6 | 0 | 100.00% | 0.02 |

## Failed cases

No failed evaluated cases.

## Metric notes

- Safety and authorization layers are deterministic and must reach 100% before deployment.
- Live RAG failures caused by unavailable model/embedding infrastructure are reported as failures, not silently skipped.
- The JSON report contains per-case answers, grounding status, database paths and latency for debugging.
