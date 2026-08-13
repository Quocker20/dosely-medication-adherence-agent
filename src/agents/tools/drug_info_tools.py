"""READ-ONLY tool — drug info lookup via RAG. See cong_viec.md §2.1, FR-4.1.

STUB. This needs a real RAG pipeline (Chroma collection populated with drug
info, `text-embedding-3-small` embeddings, similarity-threshold grounding
per cong_viec.md §4.3) — none of that exists in this repo yet, only the
`chroma_persist_dir` config value. Building the ingestion pipeline is a
separate, larger piece of work (cong_viec.md §5 P1 item 10: "Grounding
threshold + citation check"), not something to fake inside a single tool
function. Wire this up once the Chroma collection exists.
"""
from __future__ import annotations

from langchain_core.tools import tool


@tool
async def search_drug_info(query: str) -> str:
    """Tra cứu công dụng/hoạt chất của thuốc (RAG, bám sát nguồn).

    KHÔNG dùng để kết luận về tương tác thuốc (xem cong_viec.md §1.1) —
    câu hỏi tương tác thuốc phải được chặn ở safety_guard_node, không đi
    tới tool này.

    Args:
        query: Tên thuốc hoặc câu hỏi cần tra cứu

    Returns:
        Đoạn trích thông tin thuốc kèm nguồn, hoặc thông báo chưa sẵn sàng
    """
    # TODO: Chroma retriever chưa tồn tại — xem module docstring.
    return (
        "Tôi không tìm thấy thông tin đáng tin cậy về thuốc này. "
        "Bạn vui lòng hỏi bác sĩ hoặc dược sĩ."
    )
