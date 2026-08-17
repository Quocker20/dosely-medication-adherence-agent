# Prompt chấm RAG Triad

Upload file `rag_triad_bundle_q1_q2.json`, sau đó gửi:

> Đọc toàn bộ file JSON đã tải lên. Thực hiện đúng `grader_instructions` và
> `rubric`. Chỉ dùng `retrieved_contexts` làm nguồn sự thật, không dùng kiến
> thức y dược bên ngoài. Chấm tất cả case và trả về duy nhất một JSON hợp lệ
> theo `grader_output_schema`; không dùng Markdown code fence. Với claim chứa
> liều lượng, số liệu, mã ATC, chống chỉ định hoặc chiều tương tác thuốc,
> groundedness chỉ đạt nếu context hỗ trợ chính xác hoàn toàn.
