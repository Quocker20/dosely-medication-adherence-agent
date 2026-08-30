from __future__ import annotations

from dataclasses import asdict, dataclass

from src.agents.medication_policy import match_medication_decision
from src.agents.nodes.grounding_validator_node import validate_grounded_answer
from src.rag_retrieval.input_guardrail import (
    NEEDS_DRUG_NAME_REPLY,
    is_contextual_drug_reference,
    route_input,
)
from src.rag_retrieval.language_guardrail import detect_supported_language
from src.rag_retrieval.service import DrugRAG, RetrievalHit

_BLOCKED_REPLY = (
    "Mình không thể quyết định thay đổi điều trị, kê thuốc hoặc xác nhận phối hợp thuốc "
    "cho bạn. Hãy giữ nguyên hướng dẫn hiện tại và hỏi bác sĩ/dược sĩ trước khi thay đổi."
)
_NO_DATA_REPLY = (
    "Không tìm thấy thông tin phù hợp trong phần Dược thư Quốc gia đã được phê duyệt. "
    "Mình sẽ không suy diễn; bạn vui lòng hỏi bác sĩ hoặc dược sĩ."
)
_GROUNDING_FALLBACK = (
    "Mình chưa thể xác minh câu trả lời hoàn toàn từ các đoạn Dược thư đã truy xuất. "
    "Bạn vui lòng hỏi bác sĩ hoặc dược sĩ."
)
_UNSUPPORTED_LANGUAGE_REPLY = (
    "Mình chỉ hỗ trợ câu hỏi bằng tiếng Việt hoặc tiếng Anh. "
    "Vui lòng nhập lại câu hỏi bằng một trong hai ngôn ngữ này."
)


@dataclass(frozen=True)
class SourceView:
    number: int
    chunk_id: str
    citation: str
    document_id: str
    source_name: str
    drug_name: str
    section: str
    page_start: int | str
    page_end: int | str
    score: float
    excerpt: str


@dataclass(frozen=True)
class SafeRAGResult:
    answer: str
    status: str
    safety_reason: str | None
    grounding_valid: bool
    grounding_errors: list[str]
    sources: list[SourceView]

    def to_dict(self) -> dict:
        return asdict(self)


def _source_map(hits: list[RetrievalHit]) -> dict[int, str]:
    return {
        index: f"[Nguồn {index}] {hit.citation}\n{hit.document}"
        for index, hit in enumerate(hits, start=1)
    }


def _source_views(hits: list[RetrievalHit]) -> list[SourceView]:
    return [
        SourceView(
            number=index,
            chunk_id=hit.chunk_id,
            citation=hit.citation,
            document_id=str(hit.metadata.get("document_id", "")),
            source_name=str(hit.metadata.get("source_name", "")),
            drug_name=str(hit.metadata.get("drug_name", "")),
            section=str(hit.metadata.get("section", "")),
            page_start=hit.metadata.get("page_start", "?"),
            page_end=hit.metadata.get("page_end", "?"),
            score=hit.score,
            excerpt=hit.document[:900],
        )
        for index, hit in enumerate(hits, start=1)
    ]


class SafeDrugRAG:
    def __init__(self, rag: DrugRAG | None = None, *, answer_model: str = "gpt-4o-mini") -> None:
        self.rag = rag or DrugRAG()
        self.answer_model = answer_model

    def query(
        self,
        question: str,
        *,
        top_k: int = 5,
        context_drug: tuple[str, str] | None = None,
    ) -> SafeRAGResult:
        question = question.strip()
        infer_drug = getattr(self.rag, "infer_drug", None)
        resolved_drug = infer_drug(question) if callable(infer_drug) else (None, None)
        language = detect_supported_language(question, recognized_drug=bool(resolved_drug[0]))
        if language is None:
            return SafeRAGResult(
                answer=_UNSUPPORTED_LANGUAGE_REPLY,
                status="unsupported_language",
                safety_reason=None,
                grounding_valid=True,
                grounding_errors=[],
                sources=[],
            )
        policy = match_medication_decision(question)
        if policy:
            return SafeRAGResult(
                answer=_BLOCKED_REPLY,
                status="safety_blocked",
                safety_reason=policy,
                grounding_valid=True,
                grounding_errors=[],
                sources=[],
            )
        # An upstream catalog->ingredient resolution is authoritative even
        # when the question contains an explicit brand name. Brand names do
        # not necessarily exist as formulary headings.
        using_context = bool(context_drug)
        if using_context:
            resolved_drug = context_drug
        recognized_drug = bool(resolved_drug[0])
        route = route_input(question, recognized_drug=recognized_drug)
        if route.intent != "drug_query":
            return SafeRAGResult(
                answer=route.reply or "",
                status=route.intent,
                safety_reason=None,
                grounding_valid=True,
                grounding_errors=[],
                sources=[],
            )
        # A drug-looking query with no resolvable name must never fall through
        # to an unfiltered semantic search across the whole formulary. That can
        # confidently return an unrelated medicine for a misspelling.
        if callable(infer_drug) and not recognized_drug:
            return SafeRAGResult(
                answer=NEEDS_DRUG_NAME_REPLY,
                status="needs_drug_name",
                safety_reason=None,
                grounding_valid=True,
                grounding_errors=[],
                sources=[],
            )
        if using_context:
            normalized, display = resolved_drug
            retrieval_question = f"{display}: {question}"
            hits = self.rag.retrieve(retrieval_question, top_k=top_k, drug=display)
        else:
            hits = self.rag.retrieve(question, top_k=top_k)
        if not hits:
            return SafeRAGResult(
                answer=_NO_DATA_REPLY,
                status="no_data",
                safety_reason=None,
                grounding_valid=True,
                grounding_errors=[],
                sources=[],
            )
        answer = self.rag.answer_from_hits(question, hits, model=self.answer_model)
        grounding = validate_grounded_answer(answer, _source_map(hits))
        # Generation is non-deterministic. Retry once when formatting or wording
        # violates grounding; never relax the validator or return the failed text.
        if not grounding.valid:
            repaired_answer = self.rag.answer_from_hits(question, hits, model=self.answer_model)
            repaired_grounding = validate_grounded_answer(repaired_answer, _source_map(hits))
            if repaired_grounding.valid:
                answer = repaired_answer
                grounding = repaired_grounding
        return SafeRAGResult(
            answer=answer if grounding.valid else _GROUNDING_FALLBACK,
            status="answered" if grounding.valid else "grounding_blocked",
            safety_reason=None,
            grounding_valid=grounding.valid,
            grounding_errors=grounding.errors,
            sources=_source_views(hits),
        )
