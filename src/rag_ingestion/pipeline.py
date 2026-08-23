from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path

import tiktoken
from tiktoken import Encoding

from src.rag_ingestion.taxonomy import SECTION_ALIASES, SECTION_LABELS

DOCUMENT_ID = "duoc-thu-quoc-gia-viet-nam-2022-quyen-1"
SOURCE_NAME = "Dược thư Quốc gia Việt Nam 2022 - Quyển 1"
WATERMARK_RE = re.compile(r"https?://(?:www\.)?trungtamthuoc\.com", re.I)
PART_RE = re.compile(r"pages-(\d{3})-(\d{3})\.txt$")
SENTENCE_END_RE = re.compile(r"(?<=[.!?;:])\s+")
IDENTITY_MARKER_RE = re.compile(
    r"^(?:t[eê]n chung qu[oố]c t[eế]|m[aã]\s*atc|lo[aạ]i thu[oố]c)\s*:\s*\S+",
    re.I,
)
STRUCTURAL_DRUG_RE = re.compile(
    r"^(?:tap|phan|chuong|phu luc|muc luc|phan loai|phan ung|dtqgvn|bang)\b|"
    r"^\(?[a-z]\s*[-–—]\s*[a-z]\)?$",
    re.I,
)
_TOKENIZER: Encoding | None = None
_TOKENIZER_ATTEMPTED = False
_TOKENIZER_NAME = "unicode_word_punctuation_fallback"


@dataclass(frozen=True)
class PageText:
    page: int
    source_file: str
    raw_text: str
    normalized_text: str
    ocr_confidence: float


@dataclass(frozen=True)
class LineText:
    page: int
    text: str


@dataclass
class SectionBlock:
    drug_name: str
    normalized_drug_name: str
    drug_confidence: float
    section: str
    section_title_original: str
    section_confidence: float
    lines: list[LineText]


@dataclass(frozen=True)
class RagChunk:
    chunk_id: str
    document_id: str
    source_name: str
    drug_name: str
    normalized_drug_name: str
    section: str
    section_label: str
    section_title_original: str
    content: str
    embedding_text: str
    page_start: int
    page_end: int
    chunk_index: int
    token_count: int
    ocr_confidence: float
    drug_confidence: float
    section_confidence: float
    parser_confidence: float
    needs_review: bool
    review_reasons: tuple[str, ...]
    review_status: str


def fold_text(value: str) -> str:
    value = unicodedata.normalize("NFD", value.casefold().replace("đ", "d"))
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def normalize_drug_key(value: str) -> str:
    """Stable metadata key tolerant of OCR-inserted or missing spaces."""
    return fold_text(value).replace(" ", "")


def normalize_page(raw: str) -> str:
    text = unicodedata.normalize("NFC", raw.replace("\r\n", "\n").replace("\r", "\n"))
    cleaned: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        if not line or WATERMARK_RE.fullmatch(line):
            cleaned.append("")
            continue
        if re.fullmatch(r"DTQGVN\s*3", line, re.I):
            continue
        cleaned.append(line)
    text = "\n".join(cleaned)
    text = re.sub(r"(?<=\w)-\n(?=\w)", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def estimate_ocr_confidence(text: str) -> float:
    if not text.strip():
        return 0.0
    chars = [ch for ch in text if not ch.isspace()]
    suspicious = sum(ch in "†‡�|{}[]" for ch in chars)
    suspicious += len(re.findall(r"\b\w*[0-9]\w*[A-Za-zÀ-ỹ]\w*\b", text)) * 2
    ratio = suspicious / max(len(chars), 1)
    return round(max(0.45, min(0.97, 0.93 - ratio * 8)), 4)


def load_pages(input_dir: Path) -> list[PageText]:
    pages: list[PageText] = []
    for path in sorted(input_dir.glob("part-*.txt")):
        match = PART_RE.search(path.name)
        if not match:
            continue
        start_page = int(match.group(1))
        raw_pages = path.read_text(encoding="utf-8-sig", errors="replace").split("\f")
        while raw_pages and not raw_pages[-1].strip():
            raw_pages.pop()
        for offset, raw in enumerate(raw_pages):
            normalized = normalize_page(raw)
            pages.append(
                PageText(
                    page=start_page + offset,
                    source_file=path.name,
                    raw_text=raw,
                    normalized_text=normalized,
                    ocr_confidence=estimate_ocr_confidence(normalized),
                )
            )
    pages.sort(key=lambda item: item.page)
    return pages


def fuzzy_section(line: str, threshold: float = 0.82) -> tuple[str | None, float]:
    candidate = fold_text(re.sub(r"\([^)]*\)", "", line).rstrip(":."))
    if not candidate or len(candidate.split()) > 8:
        return None, 0.0
    best_section: str | None = None
    best_score = 0.0
    for section, aliases in SECTION_ALIASES.items():
        for alias in aliases:
            folded_alias = fold_text(alias)
            word_delta = abs(len(candidate.split()) - len(folded_alias.split()))
            score = SequenceMatcher(None, candidate, folded_alias).ratio() - (0.12 * word_delta)
            if score > best_score:
                best_section, best_score = section, score
    return (best_section, round(best_score, 4)) if best_score >= threshold else (None, best_score)


def _uppercase_ratio(value: str) -> float:
    letters = [ch for ch in value if ch.isalpha()]
    return sum(ch.isupper() for ch in letters) / max(len(letters), 1)


def detect_drug_header(lines: Sequence[str], index: int) -> tuple[str | None, float]:
    line = lines[index].strip().strip(".,:;-")
    if not 3 <= len(line) <= 90 or ":" in line or any(ch.isdigit() for ch in line):
        return None, 0.0
    if _uppercase_ratio(line) < 0.82 or not 1 <= len(line.split()) <= 9:
        return None, 0.0
    if fuzzy_section(line)[0] is not None:
        return None, 0.0
    folded = fold_text(line)
    blacklist = {
        "bo y te", "hoi dong duoc dien viet nam", "muc luc", "loi noi dau",
        "cong tac vien", "ban bien tap hieu dinh", "tai lieu tham khao",
    }
    if folded in blacklist:
        return None, 0.0
    if STRUCTURAL_DRUG_RE.search(folded) or len(folded) <= 3:
        return None, 0.0
    nearby = lines[index + 1 : index + 7]
    marker_offsets = [
        offset for offset, item in enumerate(nearby, start=1)
        if IDENTITY_MARKER_RE.match(item.strip())
    ]
    if not marker_offsets or marker_offsets[0] > 3:
        return None, 0.0
    markers = len(marker_offsets)
    confidence = 0.94 + min(markers, 3) * 0.015
    return line, round(min(confidence, 0.985), 4)


def is_invalid_drug_name(value: str) -> bool:
    folded = fold_text(value)
    return bool(
        not folded
        or len(folded) <= 3
        or STRUCTURAL_DRUG_RE.search(folded)
        or folded in {"eee", "a h", "m", "ke don thuoc", "su dung thuoc"}
    )


def parse_sections(pages: Sequence[PageText]) -> tuple[list[SectionBlock], list[dict]]:
    records: list[LineText] = []
    for page in pages:
        page_lines = page.normalized_text.splitlines()
        if any(fold_text(line) == "cac phu luc" for line in page_lines):
            break
        records.extend(LineText(page.page, line.strip()) for line in page_lines)
    nonempty = [record for record in records if record.text]
    texts = [record.text for record in nonempty]

    blocks: list[SectionBlock] = []
    review_events: list[dict] = []
    current_drug = ""
    drug_confidence = 0.0
    current_section = "unknown"
    section_title = ""
    section_confidence = 0.0
    current_lines: list[LineText] = []

    def flush() -> None:
        nonlocal current_lines
        if current_lines and current_drug:
            blocks.append(
                SectionBlock(
                    drug_name=current_drug,
                    normalized_drug_name=normalize_drug_key(current_drug),
                    drug_confidence=drug_confidence,
                    section=current_section,
                    section_title_original=section_title,
                    section_confidence=section_confidence,
                    lines=current_lines,
                )
            )
        current_lines = []

    for index, record in enumerate(nonempty):
        drug, detected_confidence = detect_drug_header(texts, index)
        if drug:
            # A long monograph title is often split across uppercase lines.
            # Join consecutive detected headers until identity content starts.
            if current_drug and current_section == "identity" and not current_lines:
                current_drug = f"{current_drug} {drug}"
                drug_confidence = min(drug_confidence, detected_confidence)
                continue
            flush()
            current_drug = drug
            drug_confidence = detected_confidence
            current_section = "identity"
            section_title = ""
            section_confidence = 0.95
            continue

        section, score = fuzzy_section(record.text)
        if section:
            flush()
            current_section = section
            section_title = record.text
            section_confidence = score
            continue

        if current_drug:
            current_lines.append(record)
        elif len(record.text) > 80:
            review_events.append(
                {"page": record.page, "reason": "content_before_first_drug", "text": record.text}
            )
    flush()
    return blocks, review_events


def token_count(text: str) -> int:
    global _TOKENIZER, _TOKENIZER_ATTEMPTED, _TOKENIZER_NAME
    if not _TOKENIZER_ATTEMPTED:
        _TOKENIZER_ATTEMPTED = True
        try:
            _TOKENIZER = tiktoken.get_encoding("cl100k_base")
            _TOKENIZER_NAME = "cl100k_base"
        except Exception:
            _TOKENIZER = None
    if _TOKENIZER is not None:
        return len(_TOKENIZER.encode(text))
    return len(re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE))


def _split_long_line(line: LineText, max_tokens: int) -> list[LineText]:
    if token_count(line.text) <= max_tokens:
        return [line]
    sentences = SENTENCE_END_RE.split(line.text)
    result: list[LineText] = []
    buffer = ""
    for sentence in sentences:
        candidate = f"{buffer} {sentence}".strip()
        if buffer and token_count(candidate) > max_tokens:
            result.append(LineText(line.page, buffer))
            buffer = sentence
        else:
            buffer = candidate
    if buffer:
        result.append(LineText(line.page, buffer))
    return result


def chunk_block(block: SectionBlock, max_tokens: int, overlap_tokens: int) -> Iterator[list[LineText]]:
    lines = [piece for line in block.lines for piece in _split_long_line(line, max_tokens)]
    index = 0
    while index < len(lines):
        chunk: list[LineText] = []
        size = 0
        cursor = index
        while cursor < len(lines):
            line_size = token_count(lines[cursor].text + "\n")
            if chunk and size + line_size > max_tokens:
                break
            chunk.append(lines[cursor])
            size += line_size
            cursor += 1
        if not chunk:
            chunk = [lines[index]]
            cursor = index + 1
        yield chunk
        if cursor >= len(lines):
            break
        overlap = 0
        next_index = cursor
        while next_index > index and overlap < overlap_tokens:
            next_index -= 1
            overlap += token_count(lines[next_index].text + "\n")
        index = max(next_index, index + 1)


def _review_reasons(
    block: SectionBlock, content: str, size: int, ocr_confidence: float, min_confidence: float
) -> list[str]:
    reasons: list[str] = []
    if block.section == "unknown":
        reasons.append("unknown_section")
    if block.drug_confidence < 0.92:
        reasons.append("low_drug_confidence")
    if block.section_confidence < 0.86:
        reasons.append("low_section_confidence")
    if ocr_confidence < min_confidence:
        reasons.append("low_ocr_confidence")
    if size < 15:
        reasons.append("too_short")
    if re.search(r"\b(?:mg|g|ml|microgam|mcg|%)\b", content, re.I) and ocr_confidence < 0.85:
        reasons.append("numeric_medical_content_needs_review")
    if "�" in content:
        reasons.append("replacement_character")
    return reasons


def build_chunks(
    blocks: Sequence[SectionBlock], pages: Sequence[PageText], max_tokens: int = 500,
    overlap_tokens: int = 100, min_confidence: float = 0.82,
) -> list[RagChunk]:
    confidence_by_page = {page.page: page.ocr_confidence for page in pages}
    chunks: list[RagChunk] = []
    per_section_index: dict[tuple[str, str], int] = {}
    seen_content: set[tuple[str, str, str]] = set()
    for block in blocks:
        key = (block.normalized_drug_name, block.section)
        for lines in chunk_block(block, max_tokens, overlap_tokens):
            content = "\n".join(line.text for line in lines).strip()
            if not content:
                continue
            content_key = (
                block.normalized_drug_name,
                block.section,
                re.sub(r"\s+", " ", content).strip(),
            )
            if content_key in seen_content:
                continue
            seen_content.add(content_key)
            per_section_index[key] = per_section_index.get(key, 0) + 1
            chunk_index = per_section_index[key]
            page_start, page_end = min(line.page for line in lines), max(line.page for line in lines)
            size = token_count(content)
            page_confidences = [confidence_by_page.get(page, 0.0) for page in range(page_start, page_end + 1)]
            ocr_confidence = round(min(page_confidences or [0.0]), 4)
            reasons = _review_reasons(block, content, size, ocr_confidence, min_confidence)
            parser_confidence = round(
                min(block.drug_confidence, block.section_confidence, ocr_confidence), 4
            )
            slug = hashlib.sha256(
                f"{DOCUMENT_ID}|{block.normalized_drug_name}|{block.section}|{chunk_index}|{content}".encode()
            ).hexdigest()[:16]
            label = SECTION_LABELS.get(block.section, "Không xác định")
            chunks.append(
                RagChunk(
                    chunk_id=f"dtqg-{slug}", document_id=DOCUMENT_ID, source_name=SOURCE_NAME,
                    drug_name=block.drug_name, normalized_drug_name=block.normalized_drug_name,
                    section=block.section, section_label=label,
                    section_title_original=block.section_title_original, content=content,
                    embedding_text=f"Thuốc: {block.drug_name}\nMục: {label}\n\n{content}",
                    page_start=page_start, page_end=page_end, chunk_index=chunk_index,
                    token_count=size, ocr_confidence=ocr_confidence,
                    drug_confidence=block.drug_confidence,
                    section_confidence=block.section_confidence,
                    parser_confidence=parser_confidence, needs_review=bool(reasons),
                    review_reasons=tuple(reasons), review_status="pending" if reasons else "approved",
                )
            )
    return chunks


def filter_chunks(
    chunks: Iterable[RagChunk], *, drug_name: str | None = None,
    section: str | None = None, approved_only: bool = True,
) -> list[RagChunk]:
    normalized_drug = normalize_drug_key(drug_name) if drug_name else None
    return [
        chunk for chunk in chunks
        if (not normalized_drug or chunk.normalized_drug_name == normalized_drug)
        and (not section or chunk.section == section)
        and (not approved_only or chunk.review_status == "approved")
    ]


def _write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _merge_overlap(left: str, right: str) -> str:
    left_lines = [line for line in left.splitlines() if line.strip()]
    right_lines = [line for line in right.splitlines() if line.strip()]
    max_overlap = min(len(left_lines), len(right_lines), 30)
    overlap = 0
    for size in range(max_overlap, 0, -1):
        if [fold_text(x) for x in left_lines[-size:]] == [fold_text(x) for x in right_lines[:size]]:
            overlap = size
            break
    return "\n".join(left_lines + right_lines[overlap:])


def process_review_chunks(
    chunks: Sequence[RagChunk], max_group_size: int = 3,
    context_chunks: Sequence[RagChunk] | None = None,
) -> list[dict]:
    """Merge each risky chunk with nearby context in the same drug and section."""
    review_ids = {chunk.chunk_id for chunk in chunks}
    source = context_chunks if context_chunks is not None else chunks
    ordered = sorted(
        source,
        key=lambda item: (
            item.page_start, item.page_end, item.normalized_drug_name,
            item.section, item.chunk_index,
        ),
    )
    positions = {chunk.chunk_id: index for index, chunk in enumerate(ordered)}
    consumed_review_ids: set[str] = set()
    groups: list[list[RagChunk]] = []
    for review_chunk in sorted(chunks, key=lambda item: positions[item.chunk_id]):
        if review_chunk.chunk_id in consumed_review_ids:
            continue
        position = positions[review_chunk.chunk_id]
        scope = (review_chunk.normalized_drug_name, review_chunk.section)
        group = [review_chunk]
        for neighbor_position in (position - 1, position + 1):
            if len(group) >= max_group_size or not 0 <= neighbor_position < len(ordered):
                continue
            neighbor = ordered[neighbor_position]
            same_scope = (neighbor.normalized_drug_name, neighbor.section) == scope
            touches = (
                neighbor.page_start <= group[-1].page_end + 1
                and group[0].page_start <= neighbor.page_end + 1
            )
            if same_scope and touches:
                group.append(neighbor)
        group.sort(key=lambda item: (item.chunk_index, item.page_start, item.page_end))
        consumed_review_ids.update(
            item.chunk_id for item in group if item.chunk_id in review_ids
        )
        groups.append(group)

    processed: list[dict] = []
    for group in groups:
        content = group[0].content
        for chunk in group[1:]:
            content = _merge_overlap(content, chunk.content)
        reasons = sorted({reason for chunk in group for reason in chunk.review_reasons})
        cross_references = sorted(set(re.findall(
            r"Xem\s+(?:thêm\s+)?chuyên luận\s+([^.;\n]+)", content, re.I
        )))
        dosage_mentions = sorted(set(re.findall(
            r"\b\d+(?:[.,]\d+)?\s*(?:microgam|mcg|mg|g|ml|ml/kg|mg/kg|%)\b",
            content, re.I,
        )))[:100]
        digest = hashlib.sha256(
            "|".join(chunk.chunk_id for chunk in group).encode()
        ).hexdigest()[:16]
        processed.append({
            "review_group_id": f"review-{digest}",
            "source_chunk_ids": [chunk.chunk_id for chunk in group],
            "review_source_chunk_ids": [
                chunk.chunk_id for chunk in group if chunk.chunk_id in review_ids
            ],
            "source_chunk_count": len(group),
            "document_id": DOCUMENT_ID,
            "source_name": SOURCE_NAME,
            "drug_name": group[0].drug_name,
            "normalized_drug_name": group[0].normalized_drug_name,
            "section": group[0].section,
            "section_label": group[0].section_label,
            "page_start": min(chunk.page_start for chunk in group),
            "page_end": max(chunk.page_end for chunk in group),
            "content": content,
            "embedding_text": (
                f"Thuốc: {group[0].drug_name}\nMục: {group[0].section_label}\n\n{content}"
            ),
            "token_count": token_count(content),
            "ocr_confidence_min": min(chunk.ocr_confidence for chunk in group),
            "parser_confidence_min": min(chunk.parser_confidence for chunk in group),
            "review_reasons": reasons,
            "cross_references": cross_references,
            "dosage_mentions": dosage_mentions,
            "review_status": "pending",
            "reviewer_notes": "",
        })
    return processed


def build_corpus(
    input_dir: Path, output_dir: Path, *, max_tokens: int = 500,
    overlap_tokens: int = 100, min_confidence: float = 0.82,
) -> dict:
    if overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be smaller than max_tokens")
    output_dir.mkdir(parents=True, exist_ok=True)
    pages = load_pages(input_dir)
    blocks, parser_events = parse_sections(pages)
    all_detected_chunks = build_chunks(blocks, pages, max_tokens, overlap_tokens, min_confidence)
    removed_invalid = [
        chunk for chunk in all_detected_chunks if is_invalid_drug_name(chunk.drug_name)
    ]
    chunks = [
        chunk for chunk in all_detected_chunks if not is_invalid_drug_name(chunk.drug_name)
    ]
    approved = [chunk for chunk in chunks if not chunk.needs_review]
    review = [chunk for chunk in chunks if chunk.needs_review]
    processed_review = process_review_chunks(review, context_chunks=chunks)

    _write_jsonl(output_dir / "raw_pages.jsonl", (asdict(page) for page in pages))
    _write_jsonl(
        output_dir / "normalized_pages.jsonl",
        ({"page": page.page, "source_file": page.source_file,
          "normalized_text": page.normalized_text, "ocr_confidence": page.ocr_confidence}
         for page in pages),
    )
    _write_jsonl(output_dir / "chunks_all.jsonl", (asdict(chunk) for chunk in chunks))
    _write_jsonl(output_dir / "chunks_ready.jsonl", (asdict(chunk) for chunk in approved))
    _write_jsonl(output_dir / "chunks_review_raw.jsonl", (asdict(chunk) for chunk in review))
    _write_jsonl(output_dir / "chunks_review.jsonl", processed_review)
    _write_jsonl(
        output_dir / "chunks_removed_invalid_drug.jsonl",
        (asdict(chunk) for chunk in removed_invalid),
    )
    _write_jsonl(output_dir / "parser_review_events.jsonl", parser_events)

    with (output_dir / "manual_review.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "review_group_id", "drug_name", "section", "pages", "parser_confidence",
            "review_reasons", "review_status", "reviewer_notes",
        ])
        for group in processed_review:
            writer.writerow([
                group["review_group_id"], group["drug_name"], group["section"],
                f"{group['page_start']}-{group['page_end']}",
                group["parser_confidence_min"], "|".join(group["review_reasons"]),
                "pending", "",
            ])

    summary = {
        "document_id": DOCUMENT_ID,
        "pages": len(pages),
        "drug_count": len({block.normalized_drug_name for block in blocks}),
        "section_blocks": len(blocks),
        "chunks_total": len(chunks),
        "chunks_ready": len(approved),
        "chunks_review_raw": len(review),
        "chunks_review_groups": len(processed_review),
        "chunks_removed_invalid_drug": len(removed_invalid),
        "parser_review_events": len(parser_events),
        "chunk_size_tokens": max_tokens,
        "chunk_overlap_tokens": overlap_tokens,
        "minimum_confidence": min_confidence,
        "tokenizer": _TOKENIZER_NAME,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary
