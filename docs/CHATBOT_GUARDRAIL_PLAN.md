# Kế hoạch xây dựng Guardrail cho chatbot RemindRx

## 1. Mục tiêu

Xây dựng một lớp kiểm soát an toàn chạy trước mọi chức năng của chatbot nhằm:

- Phát hiện triệu chứng có dấu hiệu khẩn cấp và kích hoạt cảnh báo.
- Chặn yêu cầu để chatbot tự kê thuốc, chọn thuốc, tăng/giảm liều, ngừng thuốc hoặc xác nhận phối hợp thuốc.
- Chỉ cho phép RAG tra cứu khi xác định được chính xác tên thuốc hoặc hoạt chất.
- Không trả lời thông tin y khoa nếu nội dung sinh ra không được dữ liệu Dược thư hỗ trợ.
- Luôn trả về câu trả lời an toàn, ổn định khi LLM, RAG hoặc backend gặp lỗi.

Guardrail chỉ hỗ trợ sàng lọc và giảm rủi ro; không thay thế bác sĩ, dược sĩ hoặc hệ thống cấp cứu.

## 2. Phạm vi

### Trong phạm vi

- Tin nhắn văn bản và nội dung đã chuyển từ giọng nói thành văn bản.
- Câu hỏi về thuốc, lịch uống thuốc và thông tin điều trị của người dùng.
- Kiểm tra đầu vào trước khi phân loại intent.
- Kiểm tra truy vấn trước khi gọi RAG.
- Kiểm tra câu trả lời sau khi LLM sinh nội dung.
- Tạo Red Alert khi phát hiện tình huống nghiêm trọng.

### Ngoài phạm vi

- Chẩn đoán bệnh.
- Tự động kê đơn hoặc thay đổi đơn thuốc.
- Thay thế cuộc gọi cấp cứu.
- Đánh giá tương tác thuốc theo dữ liệu không có trong Dược thư.

## 3. Kiến trúc đề xuất

```text
Tin nhắn người dùng
        |
        v
Safety Guard
  |-- Có triệu chứng khẩn cấp --> Red Alert + câu trả lời cố định --> END
  |-- Yêu cầu quyết định dùng thuốc --> Chặn + hướng dẫn hỏi chuyên gia --> END
  `-- An toàn
        |
        v
Phân loại intent
  |-- Dữ liệu cá nhân --> API lấy dữ liệu theo patient_id trong JWT
  `-- Thông tin thuốc --> RAG Input Guard
                              |-- Không rõ tên thuốc --> yêu cầu cung cấp tên --> END
                              |-- Ngoài phạm vi/ngôn ngữ --> từ chối phù hợp --> END
                              `-- Hợp lệ --> Retrieval + LLM
                                                |
                                                v
                                       Grounding Validator
                                         |-- Hợp lệ --> ẩn citation --> trả lời
                                         `-- Không hợp lệ --> thử lại 1 lần hoặc fallback
```

## 4. Các lớp kiểm soát

### Lớp 1 — Rule-based emergency detection

Kiểm tra danh sách từ khóa và mẫu câu biểu thị triệu chứng nghiêm trọng, ví dụ khó thở, đau ngực dữ dội, mất ý thức hoặc co giật.

- Chạy bằng code, không phụ thuộc LLM.
- Nếu khớp, lập tức tạo Red Alert mức `HIGH`.
- Trả câu cố định khuyến nghị gọi 115 trong tình huống khẩn cấp.
- Dừng graph, không gọi intent classifier, RAG hay chatbot thông thường.

### Lớp 2 — Medication decision policy

Phát hiện yêu cầu buộc chatbot đưa ra quyết định điều trị, gồm:

- Chọn hoặc kê thuốc để điều trị.
- Tăng, giảm hoặc dùng gấp đôi liều.
- Ngừng hoặc thay thuốc.
- Xác nhận người dùng có thể tự phối hợp nhiều thuốc.

Khi phát hiện, hệ thống trả câu từ chối cố định và yêu cầu người dùng trao đổi với bác sĩ/dược sĩ. Truy vấn không được chuyển sang RAG để tránh việc mô hình biến thông tin tham khảo thành chỉ định cá nhân.

### Lớp 3 — LLM emergency classifier

Chỉ chạy khi rule-based detection không phát hiện nguy hiểm. LLM được yêu cầu trả duy nhất `CO` hoặc `KHONG` để nhận diện cách diễn đạt dân dã hoặc trường hợp chưa có trong danh sách từ khóa.

- `temperature = 0`.
- Timeout tối đa 3 giây.
- LLM không được phép đảo ngược kết luận nguy hiểm của lớp rule-based.
- Khi LLM lỗi hoặc timeout, ghi log để theo dõi và tiếp tục theo chính sách fail-safe đã thống nhất.

### Lớp 4 — RAG input guard

Trước retrieval, hệ thống kiểm tra:

- Ngôn ngữ có được hỗ trợ hay không.
- Câu hỏi có thuộc phạm vi thuốc/Dược thư hay không.
- Có nhận diện được tên thuốc hoặc hoạt chất không.
- Cụm từ như “thuốc này” có tham chiếu hợp lệ đến thuốc đã được xác định trong hội thoại không.

Nếu chưa xác định được tên thuốc, hệ thống phải yêu cầu người dùng cung cấp tên; tuyệt đối không tìm kiếm semantic trên toàn bộ Dược thư vì có thể trả về thuốc gần nghĩa nhưng sai đối tượng.

### Lớp 5 — Output grounding guard

Sau khi RAG sinh câu trả lời:

- Mỗi thông tin y khoa phải được đối chiếu với chunk đã truy xuất.
- Citation nội bộ phải trỏ đến nguồn tồn tại.
- Chặn câu chứa quyết định điều trị cá nhân hoặc dấu hiệu prompt injection.
- Chặn nội dung lỗi OCR hoặc claim không đủ bằng chứng.
- Nếu không hợp lệ, sinh lại tối đa một lần.
- Nếu vẫn không hợp lệ, trả fallback an toàn thay vì trả nội dung chưa xác minh.
- Citation được giữ để kiểm tra nội bộ nhưng được xóa khỏi câu trả lời hiển thị cho bệnh nhân.

## 5. Kế hoạch triển khai

### Bước 1 — Chuẩn hóa policy

- Liệt kê rõ các nhóm triệu chứng cần cảnh báo.
- Liệt kê các hành động dùng thuốc chatbot không được quyết định.
- Định nghĩa `SafetyVerdict`: `escalated`, `blocked`, `reason`, `fixed_reply`.
- Chuẩn hóa mã lý do để phục vụ log và kiểm thử.

### Bước 2 — Xây dựng Safety Guard node

- Tạo hàm đánh giá độc lập với LangGraph để dễ unit test.
- Chạy rule khẩn cấp trước, medication policy sau, LLM classifier cuối cùng.
- Chỉ dùng câu trả lời cố định cho nhánh bị chặn hoặc cảnh báo.
- Không đưa nội dung nguy hiểm trở lại general LLM để viết lại.

### Bước 3 — Gắn guardrail vào graph

- Đặt `safety_guard` làm entry point.
- Nếu `escalated=true` hoặc `safety_blocked=true`, chuyển thẳng tới `END`.
- Chỉ phân loại intent khi guardrail trả trạng thái an toàn.

### Bước 4 — Bảo vệ luồng RAG

- Kiểm tra ngôn ngữ và phạm vi câu hỏi.
- Resolve tên thuốc trước retrieval.
- Chỉ truyền `context_drug` khi lịch sử hội thoại xác định rõ thuốc được tham chiếu.
- Trả trạng thái riêng: `needs_drug_name`, `no_data`, `safety_blocked`, `grounding_blocked` và `unsupported_language`.

### Bước 5 — Kiểm tra đầu ra

- Xác minh citation và claim dựa trên các chunk được lấy trong đúng lượt hỏi.
- Retry một lần khi lỗi định dạng hoặc grounding.
- Dùng fallback cố định nếu lần retry vẫn thất bại.
- Xóa `[Nguồn N]` ở lớp presentation sau khi validation thành công.

### Bước 6 — Logging và giám sát

Ghi lại các trường không chứa dữ liệu nhạy cảm dư thừa:

- `request_id`, `patient_id` đã định danh hoặc băm.
- Guardrail layer đã kích hoạt.
- `reason`, `status`, thời gian xử lý và trạng thái tạo alert.
- Lỗi timeout, backend unavailable, RAG unavailable hoặc grounding failure.

Không ghi access token, mật khẩu, toàn bộ hồ sơ bệnh án hoặc dữ liệu không cần thiết vào log.

## 6. Kế hoạch kiểm thử

### Unit test

- Từ khóa khẩn cấp tạo Red Alert và dừng graph.
- Cách diễn đạt nguy hiểm không có trong rule được LLM phát hiện.
- Yêu cầu tăng liều, ngừng thuốc hoặc kê thuốc bị chặn.
- Câu hỏi thông thường đi qua guardrail.
- Timeout và lỗi LLM không làm endpoint bị crash.
- Truy vấn mơ hồ không được gọi retrieval.
- Claim thiếu citation hoặc sai nguồn bị grounding validator chặn.

### Integration test

- Guardrail luôn chạy trước intent classifier.
- Khi cảnh báo, `trigger_red_alert` chỉ được gọi một lần.
- RAG chỉ chạy sau khi safety check thành công.
- Chatbot không truy cập thuốc của bệnh nhân khác; dữ liệu cá nhân luôn lấy theo JWT.
- Citation nội bộ vẫn được dùng để validate nhưng không xuất hiện trên UI.

### Golden set

Golden set cần có tối thiểu các nhóm:

1. Triệu chứng khẩn cấp rõ ràng.
2. Triệu chứng khẩn cấp diễn đạt gián tiếp.
3. Yêu cầu tự thay đổi điều trị.
4. Câu hỏi thuốc hợp lệ.
5. Câu hỏi không có tên thuốc.
6. Câu hỏi ngoài phạm vi.
7. Không tìm thấy dữ liệu Dược thư.
8. Backend hoặc RAG không khả dụng.
9. Prompt injection và nội dung cố làm sai lệch nguồn.
10. Câu hỏi về thuốc của người dùng cần kết hợp PostgreSQL và RAG.

## 7. Tiêu chí nghiệm thu

- 100% lượt chat đi qua `safety_guard` trước các node khác.
- Truy vấn bị chặn không gọi general LLM hoặc RAG.
- Truy vấn chưa xác định tên thuốc không thực hiện tìm kiếm rộng.
- Red Alert lưu đúng `patient_id` lấy từ phiên xác thực.
- Chatbot không trả nội dung RAG khi grounding không hợp lệ.
- Không hiển thị `[Nguồn N]` trong câu trả lời cho người dùng.
- Các trạng thái lỗi có thông báo riêng, không bị mô tả nhầm thành “không có lịch” hoặc “không có thuốc”.
- Toàn bộ unit test, integration test và golden set bắt buộc pass trước khi deploy.

## 8. Vị trí code hiện tại

- Safety guard chính: `src/agents/nodes/safety_guard_node.py`
- Medication policy: `src/agents/medication_policy.py`
- Điều phối graph: `src/agents/graph.py`
- Red Alert và rule triệu chứng: `src/agents/tools/safety_tools.py`
- RAG input guard: `src/rag_retrieval/input_guardrail.py`
- Language guard: `src/rag_retrieval/language_guardrail.py`
- Điều phối Safe RAG: `src/rag_retrieval/safe_service.py`
- Grounding validator: `src/agents/nodes/grounding_validator_node.py`
- Test safety guard: `tests/test_agents/test_safety_guard_node.py`
- Test Safe RAG: `tests/rag_ingestion/test_safe_service.py`
- Test grounding: `tests/test_agents/test_grounding_validator_node.py`

## 9. Rủi ro và hướng cải tiến

- Rule từ khóa có thể false positive hoặc bỏ sót cách diễn đạt mới; cần cập nhật từ dữ liệu đã ẩn danh và được review.
- Cơ chế LLM timeout hiện có thể cho phép luồng tiếp tục khi classifier lỗi; cần đánh giá lại fail-open và fail-closed theo mức độ rủi ro của từng intent.
- Citation bị ẩn trên UI làm giao diện gọn hơn nhưng giảm khả năng kiểm chứng; nên giữ metadata nguồn trong log hoặc màn hình dành cho chuyên gia.
- Guardrail không được chỉ dựa vào prompt. Các quyết định quan trọng phải được cưỡng chế bằng code, graph routing, quyền truy cập backend và test tự động.
