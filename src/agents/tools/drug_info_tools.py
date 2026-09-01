"""READ-ONLY tool — drug info lookup, DB-backed via GET /medications?search=.

See cong_viec.md §2.1, FR-4.1. Chroma/RAG is intentionally out of scope here
(chromadb is installed but has no embedding pipeline or ingestion job — see
prbm.md discussion): this looks up the medications catalog directly, which
already holds real composition/uses/side_effects data. Search is name-only
(Medication.name ILIKE), not full-text over composition/uses — a patient
asking by symptom ("thuốc trị đau đầu") rather than drug name won't match.
"""

from __future__ import annotations

from langchain_core.tools import tool

from src.modules.planning.core.backend_client import BackendAPIError, get

_NO_MATCH_MESSAGE = "Tôi không tìm thấy thông tin đáng tin cậy về thuốc này. Bạn vui lòng hỏi bác sĩ hoặc dược sĩ."
_MAX_RESULTS = 3
_MIN_QUERY_LEN = 2  # mirrors GET /medications?search= min_length=2


def _format_result(med: dict) -> str:
    parts = [f"- {med['name']} (medication_id: {med['id']}, nguồn: {med['source_name']})"]
    if med.get("composition"):
        parts.append(f"  Hoạt chất/thành phần: {med['composition']}")
    if med.get("uses"):
        parts.append(f"  Công dụng: {med['uses']}")
    if med.get("side_effects"):
        parts.append(f"  Tác dụng phụ: {med['side_effects']}")
    return "\n".join(parts)


@tool
async def search_drug_info(query: str) -> str:
    """Tra cứu công dụng/hoạt chất của thuốc qua danh mục thuốc trong hệ
    thống (khớp theo TÊN thuốc, không phải triệu chứng).

    KHÔNG dùng để kết luận về tương tác thuốc (xem cong_viec.md §1.1) —
    câu hỏi tương tác thuốc phải được chặn ở safety_guard_node, không đi
    tới tool này.

    Args:
        query: Tên thuốc cần tra cứu

    Returns:
        Tối đa 3 kết quả khớp tên thuốc kèm nguồn (medication_id,
        source_name), hoặc thông báo không tìm thấy nếu không khớp
    """
    trimmed = query.strip()
    if len(trimmed) < _MIN_QUERY_LEN:
        return _NO_MATCH_MESSAGE

    try:
        # backend_client.get() already unwraps the {success,data,...}
        # envelope, so this is the PageResponse dict directly.
        page = await get("/medications", params={"search": trimmed, "size": _MAX_RESULTS})
    except BackendAPIError:
        return _NO_MATCH_MESSAGE

    content = (page or {}).get("content", [])
    if not content:
        return _NO_MATCH_MESSAGE

    return "\n".join(_format_result(med) for med in content[:_MAX_RESULTS])
