# Kế hoạch build tầng 2 — Agent layer

> Tiền đề: tầng 1 (constraint solver) đã xong và pass `test_scheduler.py`.
> Tầng 2 KHÔNG tính giờ. Mọi phép tính lịch đều gọi lại solver của tầng 1.

---

## Nguyên tắc xuyên suốt

**Agent là lớp dịch, không phải lớp quyết định.** Nhiệm vụ của nó: chuyển ngôn ngữ
tự nhiên thành tham số có cấu trúc, gọi tool, rồi chuyển kết quả ngược lại thành
câu chữ. Mọi quyết định có hệ quả y tế đều nằm ở code hoặc ở con người.

Kiểm tra nhanh khi phân vân: *nếu LLM trả lời sai ở bước này, hậu quả là gì?*
Hậu quả là câu chữ hơi lệch → để LLM làm. Hậu quả là sai giờ, sai liều, hoặc bỏ
sót cảnh báo → phải là code.

---

## Thứ tự build

Sắp theo rủi ro giảm dần, không theo độ dễ. Làm phần an toàn trước để nếu hết
thời gian thì thứ bị cắt là phần ít quan trọng nhất.

### Sprint 1 — Đường an toàn (2-3 ngày)

Không có phần này thì sản phẩm không có giá trị an toàn nào.

#### 1.1. `trigger_red_alert` — tool

```
Input:  patient_id, reason, severity, evidence
Output: {alert_id, channels_notified, timestamp}
```

Định nghĩa xong:
- [ ] Gọi được endpoint `POST /alerts` của backend
- [ ] Retry 3 lần nếu lỗi mạng, sau đó ghi vào dead-letter queue
- [ ] Không phụ thuộc LLM ở bất kỳ điểm nào trên đường đi
- [ ] Test: mock backend trả 500 → alert vẫn được ghi lại để gửi sau

#### 1.2. Rule-based detector — thuần code

```python
# src/safety/crisis_detector.py
CRITICAL_KEYWORDS = [...]   # ngôn ngữ dân dã, không phải thuật ngữ y khoa
MISSED_DOSE_THRESHOLD = 3

def detect(text: str | None, adherence: dict) -> Alert | None
```

Định nghĩa xong:
- [ ] Danh sách keyword ≥ 40 mục, viết theo cách bệnh nhân thật sự nói
- [ ] Đếm chuỗi bỏ liều liên tiếp từ `adherence_logs`
- [ ] Test: 30 câu triệu chứng nặng → bắt được 100%
- [ ] Test: 20 câu lành tính → false positive < 20%

#### 1.3. `safety_guard_node` — kết hợp 2 lớp

```
text vào
  → Lớp 1: rule detect     → khớp thì alert NGAY, dừng
  → Lớp 2: LLM phân loại   → chỉ chạy khi lớp 1 không khớp
  → LLM nói "nặng"          → cũng alert
  → LLM nói "không"         → KHÔNG hủy được kết luận lớp 1
```

Định nghĩa xong:
- [ ] LLM có timeout 3 giây, quá thì bỏ qua lớp 2 (không chặn luồng)
- [ ] Test: mock LLM trả về "không nghiêm trọng" cho câu có keyword
      → vẫn phải alert

---

### Sprint 2 — Tool đọc/ghi (2 ngày)

#### 2.1. Tools read-only

| Tool | Endpoint | Test |
|---|---|---|
| `get_prescriptions` | `GET /patients/{id}/prescriptions` | Trả đúng schema, xử lý 404 |
| `get_patient_profile` | `GET /patients/{id}/routine` | Thiếu field → raise rõ ràng |
| `get_scheduled_doses` | `GET /patients/{id}/scheduled-doses` | Lọc đúng theo ngày |
| `get_adherence_stats` | `GET /patients/{id}/adherence` | Tính đúng chuỗi bỏ liều |

#### 2.2. Tools write

| Tool | Ràng buộc phải test |
|---|---|
| `reschedule_remaining_doses` | Payload chứa thay đổi liều → backend reject |
| `record_health_survey` | Free-text lưu riêng, không đưa vào prompt |

Định nghĩa xong cho cả nhóm:
- [ ] Mọi tool có type hint và docstring rõ (LLM đọc docstring để quyết định gọi)
- [ ] Mọi tool xử lý được lỗi mạng, không để exception thoát lên graph
- [ ] DB credential đã cấu hình read-only trên `prescriptions`

---

### Sprint 3 — Rescheduling agent (2 ngày)

Đây là chỗ agent thật sự có giá trị: hiểu câu nói tự do của bệnh nhân.

```
"hôm nay tôi ăn trưa muộn, tầm 2 giờ chiều"
        ↓ LLM extract (structured output)
{"event": "meal_shift", "meal": "lunch", "new_time": "14:00"}
        ↓ code
solver.recompute(routine_override=..., from_time=now)
        ↓ code
lịch mới cho các cữ còn lại
        ↓ LLM
"Cữ Metformin trưa dời sang 13:30, cữ tối giữ nguyên 17:30 ạ."
```

Định nghĩa xong:
- [ ] Extract dùng structured output với schema cứng, không parse text tự do
- [ ] Sau khi extract, gọi solver — agent tuyệt đối không tự tính giờ
- [ ] Test: 20 câu diễn đạt khác nhau cùng ý → extract ra cùng tham số
- [ ] Test: câu mơ hồ ("ăn muộn") → hỏi lại, không đoán giờ cụ thể
- [ ] Test: câu vượt thẩm quyền ("bỏ cữ tối luôn") → từ chối, hướng bác sĩ

---

### Sprint 4 — Message generation (1 ngày)

```python
TEMPLATE = "Đến giờ uống {drug_name} {dosage}, {meal_relation}."
# LLM chỉ sinh câu động viên phía sau, < 20 từ
# Post-check: nếu chứa số hoặc tên thuốc → bỏ, dùng câu mặc định
```

Định nghĩa xong:
- [ ] Slot dữ liệu y tế do code điền 100%
- [ ] Post-check regex chặn số và tên thuốc trong phần LLM sinh
- [ ] Test: chạy 100 lần, không lần nào phần LLM chứa liều lượng
- [ ] Có bộ câu mặc định để fallback khi LLM lỗi

---

### Sprint 5 — Drug info RAG (2 ngày)

Phụ thuộc: Chroma đã ingest xong Dược thư.

```
query → retriever (k=3)
      → nếu score < threshold → TỪ CHỐI, không gọi LLM
      → structured output bắt buộc có citation
      → post-check: tên hoạt chất trong output phải có trong chunks
```

Định nghĩa xong:
- [ ] Ngưỡng similarity đã hiệu chỉnh trên tập câu hỏi thật
- [ ] Test: hỏi thuốc không có trong Chroma → từ chối, không bịa
- [ ] Test: hỏi về tương tác thuốc → từ chối (ngoài scope MVP)
- [ ] Mọi câu trả lời hiển thị nguồn "Dược thư Quốc gia VN, tr.XXX"

---

### Sprint 6 — Nối graph (1 ngày)

```
classify_intent
    ├─ ask_schedule      → get_scheduled_doses → format
    ├─ report_meal_shift → rescheduling_agent
    ├─ ask_drug_info     → drug_info_node
    ├─ report_symptom    → safety_guard_node
    └─ out_of_scope      → từ chối lịch sự
```

Định nghĩa xong:
- [ ] `safety_guard_node` chạy trên MỌI input, không chỉ nhánh `report_symptom`
- [ ] Có `agent_runs` log đầy đủ: input, tool calls, output, timestamp
- [ ] Test end-to-end: 10 kịch bản hội thoại thật

---

## Bộ eval cuối cùng

Phải chạy được trước demo. Đây là căn cứ trả lời ban giám khảo.

| Nhóm | Số case | Ngưỡng đạt |
|---|---|---|
| Escalation recall | 30-50 | ~100% |
| False positive | 20 | < 20% |
| Grounding (từ chối khi không có nguồn) | 15 | 100% |
| HITL boundary (từ chối đổi liều) | 15 | 100% |
| Prompt injection | 10 | 100% không thực thi |
| Rescheduling extract | 20 | > 85% đúng tham số |
| Message không chứa liều sai | 100 | 100% |

---

## Rủi ro và cách xử lý

| Rủi ro | Dấu hiệu | Xử lý |
|---|---|---|
| Hết thời gian | Sprint 5 chưa xong trước deadline | Cắt RAG, demo với FAQ tĩnh. Đừng cắt Sprint 1 |
| LLM extract kém | Test sprint 3 dưới 70% | Thu hẹp về vài mẫu câu cố định + nút bấm |
| Chroma chưa sẵn sàng | Ingest Dược thư còn lỗi | Sprint 5 dùng 20 thuốc hardcode làm demo |
| Backend chưa có endpoint | Tool gọi 404 | Mock bằng JSON local, đánh dấu rõ trong demo |

---

## Ước tính tổng

10-11 ngày công cho 1 người, hoặc 5-6 ngày nếu 2 người chia Sprint 1-2 và 3-4.

Sprint 1 là phần duy nhất không được cắt trong mọi tình huống.