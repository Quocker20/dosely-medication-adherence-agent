"""Deterministic post-generation checks for Dược thư RAG answers."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agents.state import AgentState

_CITATION = re.compile(r"\[Nguồn\s+(\d+)]", re.IGNORECASE)
_SOURCE_START = re.compile(r"\[Nguồn\s+(\d+)]", re.IGNORECASE)
_NUMBER = re.compile(r"(?<!\w)\d+(?:[.,]\d+)?(?:\s*(?:mg|g|ml|mcg|µg|%|giờ|lần))?", re.IGNORECASE)
_ATC_CANDIDATE = re.compile(r"\b[A-Z0-9]{7}\b")
_VALID_ATC = re.compile(r"^[A-Z]\d{2}[A-Z]{2}\d{2}$")
_INJECTION_PHRASES = (
    "ignore previous instructions",
    "ignore all instructions",
    "bo qua chi thi truoc",
    "bo qua huong dan truoc",
    "system prompt",
    "api key",
    "execute command",
    "chay lenh",
)
_SAFE_FALLBACK = (
    "Mình chưa thể xác minh câu trả lời này hoàn toàn từ các đoạn Dược thư đã truy xuất. "
    "Bạn vui lòng hỏi bác sĩ hoặc dược sĩ; mình sẽ không suy diễn thêm từ dữ liệu chưa đủ."
)
_STOP_WORDS = {
    "va",
    "la",
    "cua",
    "cho",
    "trong",
    "theo",
    "nay",
    "do",
    "mot",
    "cac",
    "voi",
    "khi",
    "neu",
    "duoc",
    "thuoc",
    "nguon",
    "trang",
    "ve",
    "co",
}

# Generated output is expected to contain normalized Vietnamese. Safety checks
# retain diacritics so distinct words such as "bạn"/"ban" and "dùng"/"dừng"
# cannot collapse into the same token. `_fold` remains appropriate for lexical
# grounding, but not for identifying who is being addressed or advised.
_OUTPUT_PERSONAL = re.compile(
    r"\b(?:tôi|mình|cháu|bạn)\b|(?:^|[,.!?;:]\s*)em\b",
    re.IGNORECASE,
)
_OUTPUT_DECISION = re.compile(
    r"\b(?:được không|có nên|có thể|an toàn không|giúp tôi|cho tôi)\b",
    re.IGNORECASE,
)
_OUTPUT_MEDICATION_ACTION = re.compile(
    r"\b(?:"
    r"tăng liều|giảm liều|đổi liều|gấp đôi liều|bớt liều|thêm liều|"
    r"uống thêm|uống gấp đôi|dừng thuốc|ngừng thuốc|bỏ thuốc|nghỉ thuốc|"
    r"kê thuốc|mua thuốc|dùng thuốc|uống thuốc|"
    r"uống cùng|dùng cùng|phối hợp|uống chung|dùng chung|"
    r"uống|dùng|tiêm|bôi|đặt"
    r")\b",
    re.IGNORECASE,
)


def _fold(value: str) -> str:
    value = unicodedata.normalize("NFD", value.casefold().replace("đ", "d"))
    value = "".join(character for character in value if unicodedata.category(character) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9%]+", " ", value).split())


def _terms(value: str) -> set[str]:
    return {
        token for token in _fold(value).split() if len(token) > 1 and token not in _STOP_WORDS and not token.isdigit()
    }


def _sentences(answer: str) -> list[str]:
    protected = re.sub(r"\bSt\.", "St<dot>", answer, flags=re.IGNORECASE)
    protected = re.sub(r"(?m)^\s*\d+[.)]\s*", "", protected)
    return [
        sentence.strip().replace("<dot>", ".")
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", protected)
        if sentence.strip()
    ]


def _unsafe_personal_decision(sentence: str) -> bool:
    raw = unicodedata.normalize("NFC", sentence.casefold())
    if not _OUTPUT_PERSONAL.search(raw):
        return False
    return bool(
        _OUTPUT_MEDICATION_ACTION.search(raw) and (_OUTPUT_DECISION.search(raw) or _OUTPUT_PERSONAL.search(raw))
    )


def _current_turn(messages: list) -> list:
    start = 0
    for index, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            start = index
    return messages[start:]


def _formulary_sources(messages: list) -> dict[int, str]:
    sources: dict[int, str] = {}
    for message in messages:
        if not isinstance(message, ToolMessage) or message.name != "search_drug_formulary":
            continue
        content = str(message.content)
        matches = list(_SOURCE_START.finditer(content))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
            sources[int(match.group(1))] = content[match.start() : end]
    return sources


@dataclass
class GroundingResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


def validate_grounded_answer(answer: str, sources: dict[int, str]) -> GroundingResult:
    if not sources:
        return GroundingResult(valid=True)
    errors: list[str] = []
    cited = [int(value) for value in _CITATION.findall(answer)]
    if not cited:
        errors.append("missing_citation")
    unknown = sorted(set(cited) - set(sources))
    if unknown:
        errors.append(f"unknown_citation:{','.join(map(str, unknown))}")
    raw_sentences = _sentences(answer)
    if any(_unsafe_personal_decision(sentence) for sentence in raw_sentences):
        errors.append("unsafe_treatment_decision")
    folded_answer = _fold(answer)
    if any(phrase in folded_answer for phrase in _INJECTION_PHRASES):
        errors.append("prompt_injection_content")
    if "�" in answer:
        errors.append("ocr_corruption_in_answer")
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", answer):
        if "atc" not in sentence.casefold():
            continue
        for candidate in _ATC_CANDIDATE.findall(sentence.upper()):
            if not _VALID_ATC.fullmatch(candidate):
                errors.append(f"invalid_atc_code:{candidate}")

    sentences = raw_sentences
    for sentence_index, sentence in enumerate(sentences, start=1):
        sentence_terms = _terms(_CITATION.sub("", sentence))
        numeric_claims = _NUMBER.findall(_CITATION.sub("", sentence))
        sentence_citations = [int(value) for value in _CITATION.findall(sentence)]
        valid_citations = [value for value in sentence_citations if value in sources]
        folded_sentence = _fold(sentence)
        structural_lead = folded_sentence.endswith(("nhu sau", "gom", "bao gom")) or (
            "tuong tac" in folded_sentence and len(sentence_terms) <= 6 and not numeric_claims
        )
        if not valid_citations and not structural_lead and (len(sentence_terms) >= 3 or numeric_claims):
            errors.append(f"sentence_{sentence_index}_missing_citation")
            continue
        if not valid_citations:
            continue
        context = " ".join(sources[value] for value in valid_citations)
        context_terms = _terms(context)
        if len(sentence_terms) >= 3:
            overlap = len(sentence_terms & context_terms) / len(sentence_terms)
            if overlap < 0.35:
                errors.append(f"sentence_{sentence_index}_low_grounding:{overlap:.2f}")
        context_folded = _fold(context)
        for numeric_claim in numeric_claims:
            if _fold(numeric_claim) not in context_folded:
                errors.append(f"sentence_{sentence_index}_unsupported_number:{numeric_claim}")
    return GroundingResult(valid=not errors, errors=errors)


async def grounding_validator_node(state: AgentState) -> dict:
    turn = _current_turn(list(state.get("messages", [])))
    sources = _formulary_sources(turn)
    if not sources:
        return {"grounding_valid": True, "grounding_errors": []}
    answer = next(
        (str(message.content) for message in reversed(turn) if isinstance(message, AIMessage)),
        "",
    )
    result = validate_grounded_answer(answer, sources)
    if result.valid:
        return {"grounding_valid": True, "grounding_errors": []}
    return {
        "messages": [AIMessage(content=_SAFE_FALLBACK)],
        "grounding_valid": False,
        "grounding_errors": result.errors,
    }
