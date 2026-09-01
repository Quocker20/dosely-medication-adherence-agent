"""Grounded formulary answers with stable patient-facing topic layouts."""
from __future__ import annotations

import asyncio
import re
from functools import lru_cache

from langchain_core.messages import AIMessage, HumanMessage

from src.agents.patient_presentation import patient_facing_text
from src.agents.medication_mapping import ingredient_candidates, resolve_catalog_medication
from src.agents.state import AgentState
from src.modules.planning.core.backend_client import BackendAPIError, get
from src.rag_retrieval import SafeDrugRAG
from src.rag_retrieval.input_guardrail import is_contextual_drug_reference
from src.rag_retrieval.service import fold

_CITATION = re.compile(r"\s*\[Nguồn\s+\d+]", re.IGNORECASE)
_EFFECT_QUERY = re.compile(r"\b(?:tác dụng|công dụng|chỉ định|dùng để làm gì|used for|indication)\b", re.IGNORECASE)
_ADVERSE_EFFECT_QUERY = re.compile(r"\b(?:tác dụng phụ|phản ứng bất lợi|side effects?)\b", re.IGNORECASE)
_TOPICS = (
    ("adverse", _ADVERSE_EFFECT_QUERY, "Tác dụng phụ hoặc phản ứng bất lợi"),
    ("interaction", re.compile(r"\b(?:tương tác|interaction)\b", re.IGNORECASE), "Tương tác được ghi nhận"),
    ("contraindication", re.compile(r"\b(?:chống chỉ định|không được dùng|contraindication)\b", re.IGNORECASE), "Trường hợp không được dùng theo Dược Thư"),
    ("missed_dose", re.compile(r"\b(?:quên liều|bỏ lỡ liều|missed dose)\b", re.IGNORECASE), "Thông tin chung khi quên liều"),
    ("storage", re.compile(r"\b(?:bảo quản|cất thuốc|storage)\b", re.IGNORECASE), "Hướng dẫn bảo quản"),
    ("special_population", re.compile(r"\b(?:mang thai|thai kỳ|cho con bú|trẻ em|người cao tuổi|pregnan|breastfeed)\b", re.IGNORECASE), "Thông tin cho nhóm đối tượng được hỏi"),
    ("administration", re.compile(r"\b(?:cách dùng|dùng như thế nào|uống như thế nào|đường dùng|how to take)\b", re.IGNORECASE), "Cách dùng chung trong Dược Thư"),
    ("effect", _EFFECT_QUERY, "Tác dụng hoặc chỉ định chính"),
)
_SCOPES = {
    "effect": "Công dụng chung không đồng nghĩa thuốc phù hợp để điều trị tình trạng cụ thể của bạn.",
    "adverse": "Danh sách này không dự đoán chắc chắn phản ứng nào sẽ xảy ra với riêng bạn.",
    "interaction": "Thông tin chung không xác nhận các thuốc trong đơn của bạn có thể tự phối hợp hoặc tự ngừng.",
    "contraindication": "Không tự kết luận có thể dùng thuốc nếu chưa đối chiếu bệnh nền, dị ứng và các thuốc đang dùng.",
    "administration": "Cách dùng chung không thay thế liều, thời điểm, đường dùng và dặn dò trong đơn đã duyệt.",
    "missed_dose": "Không tự uống bù hoặc gấp đôi liều nếu chỉ dẫn cho thuốc cụ thể chưa được xác minh.",
    "storage": "Ưu tiên điều kiện bảo quản trên nhãn của đúng sản phẩm đang cầm nếu chi tiết hơn.",
    "special_population": "Việc sử dụng cho nhóm đối tượng này cần được bác sĩ/dược sĩ xác nhận cho từng trường hợp.",
}
_UNAVAILABLE_REPLY = (
    "Mình chưa thể tra cứu Dược Thư Quốc gia lúc này. Bạn vui lòng hỏi bác sĩ hoặc dược sĩ "
    "trước khi thay đổi điều trị."
)
_IDENTITY_MISMATCH_REPLY = (
    "Mình chưa tìm thấy đoạn Dược thư khớp đúng với thuốc hoặc hoạt chất đã xác định. "
    "Mình sẽ không dùng thông tin của thuốc khác để trả lời; bạn vui lòng kiểm tra lại tên trên nhãn thuốc."
)


@lru_cache(maxsize=1)
def _get_rag_service() -> SafeDrugRAG:
    return SafeDrugRAG()


def _last_human_text(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def _claims(answer: str) -> list[str]:
    claims = []
    for raw in answer.splitlines():
        cleaned = _CITATION.sub("", raw).strip()
        cleaned = re.sub(r"^[-•*]\s*", "", cleaned).strip()
        if cleaned:
            claims.append(cleaned)
    return claims


def _drug_topic(question: str) -> tuple[str, str] | None:
    for key, pattern, heading in _TOPICS:
        if pattern.search(question):
            return key, heading
    return None


def _format_topic_answer(answer: str, drug_name: str, topic: str, heading: str) -> str:
    claims = _claims(answer)
    if not claims:
        return patient_facing_text(answer)
    lines = [
        "Thuốc được hỏi",
        drug_name or "Tên thuốc đã được xác định trong bước tra cứu",
        "",
        heading,
        *(f"- {claim}" for claim in claims),
        "",
        "Phạm vi của thông tin",
        f"- {_SCOPES.get(topic, 'Đây là thông tin chung từ Dược Thư, không phải chỉ định điều trị cá nhân.')}",
        "- Chỉ dùng theo đúng thuốc, hàm lượng, liều và đường dùng trong đơn đã được bác sĩ duyệt.",
        "",
        "Khi cần xác nhận thêm",
        "- Nếu nhãn thuốc khác dữ liệu App hoặc chưa rõ thông tin này áp dụng thế nào, hãy hỏi bác sĩ/dược sĩ trước khi dùng.",
    ]
    return "\n".join(lines)


def _format_effect_answer(answer: str, drug_name: str) -> str:
    return _format_topic_answer(answer, drug_name, "effect", "Tác dụng hoặc chỉ định chính")


async def _resolve_named_drug(
    rag: SafeDrugRAG, name: str
) -> tuple[list[tuple[str, str]], dict | None]:
    """Resolve a formulary name or an exact catalog brand before retrieval."""
    if not name:
        return [], None
    normalized, display = rag.rag.infer_drug(name)
    if normalized and display:
        return [(normalized, display)], None
    try:
        page = await get("/medications", params={"search": name, "size": 10})
    except BackendAPIError:
        return [], None
    entries = list((page or {}).get("content") or [])
    wanted = fold(name)
    exact = [entry for entry in entries if fold(str(entry.get("name") or "")) == wanted]
    if len(exact) != 1:
        return [], None
    entry = exact[0]
    composition = str(entry.get("composition") or "")
    ingredients = ingredient_candidates(composition)
    identities = resolve_catalog_medication(
        str(entry.get("name") or name), composition, rag.rag
    )
    # A combination product is safe to answer only when every catalogued
    # active ingredient maps to a reviewed formulary heading.
    if not ingredients or len(identities) != len(ingredients):
        return [], entry
    return [
        (identity.normalized_drug_name, identity.formulary_name)
        for identity in identities
    ], entry


async def _query_resolved_drugs(rag: SafeDrugRAG, question: str, drugs: list[tuple[str, str]]):
    if not drugs:
        return await asyncio.to_thread(rag.query, question)
    if len(drugs) == 1:
        return await asyncio.to_thread(rag.query, question, context_drug=drugs[0])
    return await asyncio.to_thread(rag.query, question, context_drugs=drugs)


def _groundable_question(question: str, drug_name: str) -> str:
    """Turn an instruction to repeat an absolute claim into a neutral RAG query."""
    normalized = fold(question)
    absolute_claim = any(marker in normalized for marker in (
        "moi loai", "chua khoi tat ca", "luon luon chua", "chac chan chua",
    ))
    repeat_request = any(marker in normalized for marker in (
        "ghi cau do", "hay xac nhan", "cu khang dinh", "noi rang",
    ))
    if drug_name and absolute_claim and repeat_request:
        return f"{drug_name} có tác dụng và chỉ định gì?"
    return question


async def drug_rag_node(state: AgentState) -> dict:
    question = _last_human_text(state)
    analysis = state.get("intent_analysis") or {}
    rag_question = _groundable_question(question, str(analysis.get("drug_name") or "").strip())
    if analysis.get("needs_clarification"):
        name = str(analysis.get("drug_name") or "thuốc này").strip()
        return {"messages": [AIMessage(content=(
            f"Bạn muốn biết thông tin nào về {name}: công dụng, cách dùng, tác dụng phụ, "
            "chống chỉ định hay tương tác thuốc?"
        ))]}
    try:
        rag = _get_rag_service()
        context_drugs: list[tuple[str, str]] = []
        catalog_entry = None
        memory = state.get("memory_context") or {}
        current = memory.get("current_medication") if isinstance(memory, dict) else None
        if is_contextual_drug_reference(question) and isinstance(current, dict):
            display_name = str(current.get("display_name") or "")
            normalized, canonical = rag.rag.infer_drug(display_name)
            if normalized and canonical:
                context_drugs = [(normalized, canonical)]
        if not context_drugs:
            context_drugs, catalog_entry = await _resolve_named_drug(
                rag, str(analysis.get("drug_name") or "").strip()
            )
        result = await _query_resolved_drugs(rag, rag_question, context_drugs)
        if result.status in {"needs_drug_name", "out_of_scope", "unsupported_language", "no_data"}:
            catalog_name = str(analysis.get("drug_name") or "").strip()
            if catalog_name:
                try:
                    page = await get("/medications", params={"search": catalog_name, "size": 3})
                    entries = list((page or {}).get("content") or [])
                except BackendAPIError:
                    entries = []
                if len(entries) == 1:
                    entry = entries[0]
                    composition = str(entry.get("composition") or "").strip()
                    catalog_identity_verified = False
                    if composition:
                        identities = resolve_catalog_medication(
                            str(entry.get("name") or catalog_name), composition, rag.rag
                        )
                        ingredients = ingredient_candidates(composition)
                        if ingredients and len(identities) == len(ingredients):
                            catalog_identity_verified = True
                            context_drugs = [
                                (identity.normalized_drug_name, identity.formulary_name)
                                for identity in identities
                            ]
                            result = await _query_resolved_drugs(
                                rag, rag_question, context_drugs
                            )
                    if result.status != "answered":
                        # A catalog row proves that the product exists, not its
                        # clinical use. If every ingredient cannot be mapped to
                        # reviewed formulary headings, let the response LLM
                        # explain that evidence gap instead of presenting the
                        # catalog row as a grounded medical answer.
                        if not catalog_identity_verified:
                            reason = (
                                "catalog_missing_verified_uses"
                                if not str(entry.get("uses") or "").strip()
                                else "catalog_drug_not_in_formulary"
                            )
                            return {
                                "messages": [AIMessage(content="Catalog evidence is insufficient for a clinical answer.")],
                                "grounding_valid": False,
                                "grounding_errors": [reason],
                                "rag_sources": [],
                                "refusal_reason": reason,
                                "metadata": {
                                    "catalog_medication": {
                                        "name": str(entry.get("name") or catalog_name),
                                        "composition": composition,
                                        "source_name": str(entry.get("source_name") or ""),
                                    }
                                },
                            }
                        details = [f"Thông tin từ danh mục thuốc\n- Tên: {entry.get('name')}"]
                        if composition:
                            details.append(f"- Hoạt chất/thành phần: {composition}")
                        if entry.get("uses"):
                            details.append(f"- Công dụng: {entry['uses']}")
                        if entry.get("side_effects"):
                            details.append(f"- Tác dụng phụ: {entry['side_effects']}")
                        details.append(f"- Nguồn danh mục: {entry.get('source_name') or 'chưa rõ'}")
                        details.append("Thông tin danh mục không thay thế chỉ dẫn trong đơn đã được bác sĩ duyệt.")
                        return {"messages": [AIMessage(content="\n".join(details))], "grounding_valid": True, "grounding_errors": []}
    except Exception:
        return {
            "messages": [AIMessage(content=_UNAVAILABLE_REPLY)],
            "grounding_valid": False,
            "grounding_errors": ["rag_unavailable"],
        }

    if context_drugs and result.sources:
        expected = {drug[0] for drug in context_drugs}
        mismatched = [
            source.drug_name for source in result.sources
            if fold(str(source.drug_name)).replace(" ", "") not in expected
        ]
        if mismatched:
            return {
                "messages": [AIMessage(content=_IDENTITY_MISMATCH_REPLY)],
                "grounding_valid": False,
                "grounding_errors": ["drug_identity_mismatch"],
                "rag_sources": [],
            }
    answer = patient_facing_text(result.answer)
    if result.status == "needs_drug_name":
        return {
            "messages": [AIMessage(content=answer)],
            "intent": "clarify",
            "grounding_valid": True,
            "grounding_errors": [],
            "rag_sources": [],
        }
    topic = _drug_topic(rag_question)
    if result.status == "answered" and result.grounding_valid and topic:
        names = list(dict.fromkeys(source.drug_name for source in result.sources if source.drug_name))
        answer = _format_topic_answer(result.answer, ", ".join(names), *topic)
    return {
        "messages": [AIMessage(content=answer)],
        "grounding_valid": result.grounding_valid,
        "grounding_errors": result.grounding_errors,
        "rag_sources": [
            {
                "citation": source.citation,
                "drug_name": source.drug_name,
                "section": source.section,
                "excerpt": source.excerpt,
            }
            for source in result.sources
        ],
        # Persist only the verified identity for follow-up context. Schedule
        # questions still re-check live patient data; this is not a schedule cache.
        "metadata": {
            "resolved_medication": {
                "display_name": str(analysis.get("drug_name") or (context_drugs[0][1] if context_drugs else "")),
                "medication_id": str((catalog_entry or {}).get("id") or ""),
                "resolved_from": "drug_name",
                "resolved_ingredients": [display for _normalized, display in context_drugs],
            }
        } if context_drugs else {},
    }
