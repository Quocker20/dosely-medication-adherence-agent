from __future__ import annotations
from langchain_core.messages import AIMessage
from src.agents.state import AgentState
from src.agents.tools.drug_info_tools import search_drug_info

async def medication_catalog_node(state: AgentState) -> dict:
    analysis = state.get("intent_analysis") or {}
    query = str(analysis.get("drug_name") or "").strip()
    if not query:
        return {"messages": [AIMessage(content="Bạn cho mình biết tên thuốc cần tra cứu nhé.")]}
    result = await search_drug_info.ainvoke({"query": query})
    return {"messages": [AIMessage(content=str(result))], "grounding_valid": True}
