# Pipeline ingest Dược thư cho RAG

## Luồng dữ liệu

```text
OCR sidecar theo trang
  -> raw_pages.jsonl (bất biến)
  -> normalized_pages.jsonl
  -> state parser (drug + section taxonomy)
  -> chunks_all.jsonl (500 token, overlap 100 trong cùng section)
  -> chunks_ready.jsonl | chunks_review_raw.jsonl
  -> chunks_review.jsonl (nhóm review tối đa 3 chunk cùng thuốc/section)
  -> manual_review.csv
  -> embedding/index chỉ từ chunks_ready.jsonl
```

Chạy pipeline:

```powershell
.\.venv\Scripts\python.exe scripts\build_drug_rag_corpus.py
```

Đầu ra mặc định nằm tại `data/rag_corpus`. Không sửa `raw_pages.jsonl`; mọi
quyết định parser phải có thể truy ngược về `page_start/page_end` và PDF gốc.

## Nguyên tắc an toàn

- Parser giữ state `current_drug` và `current_section` xuyên trang.
- Drug header chỉ được tự nhận khi tên viết hoa đi kèm marker định danh gần đó
  (`Tên chung quốc tế`, `Mã ATC`, hoặc `Loại thuốc`).
- Fuzzy matching chỉ áp dụng cho tiêu đề section; không dùng để sửa liều hoặc
  tên hoạt chất.
- Overlap không bao giờ vượt ranh giới thuốc hoặc section.
- Chunk có confidence thấp, section không rõ hoặc nội dung số y tế đáng ngờ đi
  vào `chunks_review.jsonl`, không đi vào `chunks_ready.jsonl`.
- Header cấu trúc (`TẬP`, `PHẦN`, `DTQGVN`, mục lục...) không được phép trở
  thành `drug_name`. Candidate phải có marker định danh có giá trị ngay sau nó.
- Review chunk chỉ được gộp với context liền kề nếu cùng `drug_name + section`;
  không gộp cưỡng ép qua section. Nội dung overlap được loại theo dòng, không
  dùng LLM tóm tắt hay viết lại số liệu y tế.
- `chunks_review_raw.jsonl` giữ record gốc; `chunks_review.jsonl` chứa nhóm đã
  xử lý; `chunks_removed_invalid_drug.jsonl` là audit cho record bị loại ở lớp
  validator cuối.
- Reviewer cập nhật `manual_review.csv`; chỉ record `approved` mới được index.

## Metadata filter

Trước vector search, chuẩn hóa tên thuốc và lọc theo:

```json
{
  "normalized_drug_name": "aciclovir",
  "section": "interactions",
  "review_status": "approved"
}
```

Sau khi có vector index, chạy bộ eval và bổ sung câu hỏi ground-truth đã được
đối chiếu PDF:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_rag_corpus.py
```
## Retrieval and grounded answers

The approved corpus is embedded with `text-embedding-3-large` into
`data/rag_dense_index_q1_q2/` (the default in code — `DEFAULT_DENSE_INDEX` in
`src/rag_retrieval/service.py`; the plain `rag_dense_index` name only survives as
`LEGACY_DENSE_INDEX`, a fallback). The index stores normalized float32 vectors in
`vectors.npy`, aligned metadata/documents in `records.jsonl`, plus a manifest
and resumable state file. Review groups are never included automatically.

Build or resume the dense index:

```powershell
.\.venv\Scripts\python.exe .\scripts\build_dense_index.py --batch-size 64
```

Retrieve only:

```powershell
.\.venv\Scripts\python.exe .\scripts\query_drug_rag.py `
  "PAS tương tác với diphenhydramin như thế nào?" --retrieve-only
```

Generate a grounded answer with numbered sources:

```powershell
.\.venv\Scripts\python.exe .\scripts\query_drug_rag.py `
  "PAS tương tác với diphenhydramin như thế nào?"
```

The retriever combines exact-cosine semantic search and BM25 with
reciprocal-rank fusion. Drug and taxonomy-section metadata filters run before
ranking. Run the real-index evaluation with:

```powershell
.\.venv\Scripts\python.exe .\scripts\evaluate_rag_retrieval.py
```

**Status: wired into the live chatbot, not just an offline eval artifact.** The
`search_drug_formulary` tool (`src/agents/tools/drug_rag_tools.py`) and
`src/agents/nodes/drug_rag_node.py` load this same index at runtime via
`src/rag_retrieval/service.py`/`safe_service.py` to answer real patient chat questions —
see `docs/api-contract.md` (Slice 6) for how the
guardrail/grounding layers wrap this retrieval before it reaches the patient.
