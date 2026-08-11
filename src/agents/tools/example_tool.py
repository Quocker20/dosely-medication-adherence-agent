from langchain_core.tools import tool


@tool
def search_knowledge(query: str) -> str:
    """Tìm kiếm thông tin trong knowledge base.

    Args:
        query: Câu hỏi cần tìm kiếm

    Returns:
        Kết quả tìm kiếm
    """
    # TODO: Implement actual search logic (e.g., RAG with vector store)
    return f"Kết quả tìm kiếm cho: {query}"
