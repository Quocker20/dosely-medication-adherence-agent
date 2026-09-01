from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from openai import OpenAI

from src.core.config import get_settings

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data" / "chroma_q1_q2"
DEFAULT_DENSE_INDEX = ROOT / "data" / "rag_dense_index_q1_q2"
LEGACY_DENSE_INDEX = ROOT / "data" / "rag_dense_index"
DEFAULT_COLLECTION = "duoc_thu_2022_q1_q2_te3large_v1"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"

SECTION_HINTS = {
    "interactions": ("tuong tac", "uong cung", "phoi hop"),
    "contraindications": ("chong chi dinh", "khong duoc dung"),
    "dosage_administration": (
        "lieu", "cach dung", "su dung", "dung nhu the nao", "uong nhu the nao", "bao nhieu"
    ),
    "adverse_effects": ("tac dung khong mong muon", "tac dung phu", "adr"),
    "indications": ("chi dinh", "dieu tri", "cong dung", "dung de lam gi"),
    "warnings": ("than trong", "canh bao"),
    "pharmacokinetics": ("duoc dong hoc", "hap thu", "phan bo", "thai tru"),
    "pharmacodynamics": ("duoc ly", "duoc luc hoc", "co che", "tac dung gi"),
    "forms_strengths": ("dang thuoc", "ham luong", "bao che"),
    "identity": ("ten chung", "ma atc", "phan loai", "loai thuoc"),
    "pregnancy": ("mang thai", "thai ky"),
    "lactation": ("cho con bu", "nuoi con bang sua me"),
    "overdose": ("qua lieu", "xu tri qua lieu"),
}

# Common formulary abbreviations that do not resemble the canonical heading.
DRUG_ALIASES = {
    "pas": "acidaminosalicylic",
    # International spelling; the Vietnamese formulary heading uses one "l".
    "amoxicillin": "amoxicilin",
    "doxycycline": "doxycyclin",
    "nicotinamide": "nicotinamid",
    "niacinamide": "nicotinamid",
    # OCR in the source heading produced WAREARIN NATRI.
    "warfarin": "warearinnatri",
    # English catalog names -> Vietnamese formulary headings.
    "calcium gluconate": "calcigluconat",
    "cetirizine": "cetirizinhydroclorid",
    "isosorbide dinitrate": "isosorbiddinitrat",
}

# Tokens that occur in many canonical headings and are unsafe as abbreviated
# names by themselves. A remaining token is accepted only when it uniquely
# identifies one formulary heading in the loaded corpus.
_NON_DISTINCTIVE_DRUG_TOKENS = {
    "thuoc", "acid", "natri", "kali", "calci", "hydroclorid", "hydrat",
    "dung", "uong", "tiem", "va", "voi", "chua", "phoi", "hop",
    # Common query words must not identify a medicine merely because they are
    # unique in one compound heading (for example "liên" -> estrogen liên hợp).
    "lien", "quan", "luu", "truong", "trong", "ngoai", "theo",
    "thuc", "bua", "lam", "nao", "nhung", "nhieu",
}


def fold(value: str) -> str:
    value = unicodedata.normalize("NFD", value.casefold().replace("đ", "d"))
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def tokenize(value: str) -> list[str]:
    return [token for token in fold(value).split() if len(token) > 1]


@dataclass(frozen=True)
class RetrievalHit:
    chunk_id: str
    document: str
    metadata: dict[str, Any]
    score: float
    vector_rank: int | None = None
    lexical_rank: int | None = None

    @property
    def citation(self) -> str:
        drug = self.metadata.get("drug_name", "Không rõ thuốc")
        source = self.metadata.get("source_name", "Dược thư Quốc gia Việt Nam 2022")
        section = self.metadata.get("section_label") or self.metadata.get("section", "")
        start = self.metadata.get("page_start", "?")
        end = self.metadata.get("page_end", start)
        pages = str(start) if start == end else f"{start}–{end}"
        return f"{source} — {drug} — {section}, trang {pages}"


class DrugRAG:
    def __init__(
        self,
        *,
        persist_dir: Path = DEFAULT_DB,
        collection_name: str = DEFAULT_COLLECTION,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        client: OpenAI | None = None,
        collection: Any | None = None,
    ) -> None:
        if collection is None:
            if (DEFAULT_DENSE_INDEX / "manifest.json").exists():
                from src.rag_retrieval.dense_index import DenseIndex

                collection = DenseIndex(DEFAULT_DENSE_INDEX)
            elif (persist_dir / "chroma.sqlite3").exists():
                import chromadb

                chroma = chromadb.PersistentClient(path=str(persist_dir))
                collection = chroma.get_collection(collection_name)
            elif (LEGACY_DENSE_INDEX / "manifest.json").exists():
                from src.rag_retrieval.dense_index import DenseIndex

                collection = DenseIndex(LEGACY_DENSE_INDEX)
            else:
                import chromadb

                chroma = chromadb.PersistentClient(path=str(persist_dir))
                collection = chroma.get_collection(collection_name)
        self.collection = collection
        self.embedding_model = embedding_model
        if client is None:
            settings = get_settings()
            client_kwargs: dict[str, Any] = {
                "api_key": settings.openai_api_key or None,
                "timeout": 45.0,
                "max_retries": 2,
            }
            if settings.openai_base_url:
                client_kwargs["base_url"] = settings.openai_base_url
            client = OpenAI(**client_kwargs)
        self.client = client
        self._documents: dict[str, str] | None = None
        self._metadatas: dict[str, dict[str, Any]] | None = None
        self._drug_names: dict[str, str] | None = None
        self._unique_drug_tokens: dict[str, tuple[str, str]] | None = None

    def _load_lexical_index(self) -> None:
        if self._documents is not None:
            return
        result = self.collection.get(include=["documents", "metadatas"])
        ids = result.get("ids", [])
        documents = result.get("documents", [])
        metadatas = result.get("metadatas", [])
        self._documents = dict(zip(ids, documents, strict=True))
        self._metadatas = dict(zip(ids, metadatas, strict=True))
        self._drug_names = {}
        for metadata in metadatas:
            normalized = str(metadata.get("normalized_drug_name", ""))
            display = str(metadata.get("drug_name", ""))
            if normalized and display:
                self._drug_names[normalized] = display
        token_owners: dict[str, set[str]] = {}
        for normalized, display in self._drug_names.items():
            for token in set(fold(display).split()):
                if len(token) >= 4 and token not in _NON_DISTINCTIVE_DRUG_TOKENS:
                    token_owners.setdefault(token, set()).add(normalized)
        self._unique_drug_tokens = {
            token: (normalized, self._drug_names[normalized])
            for token, owners in token_owners.items()
            if len(owners) == 1
            for normalized in owners
        }

    def infer_drug(self, query: str) -> tuple[str | None, str | None]:
        self._load_lexical_index()
        assert self._drug_names is not None
        folded_query = f" {fold(query)} "
        compact_query = fold(query).replace(" ", "")
        matches = []
        for normalized, display in self._drug_names.items():
            spaced = fold(display)
            position = folded_query.find(f" {spaced} ")
            if position >= 0:
                matches.append((position, -len(spaced), normalized, display))
            # A normalized heading embedded inside a longer token is not an
            # identity match (e.g. DESONID occurs inside BUDESONIDE). Only a
            # bare fully-concatenated heading may use this compact form.
            elif normalized == compact_query:
                matches.append((0, -len(normalized), normalized, display))
        for alias, normalized in DRUG_ALIASES.items():
            position = folded_query.find(f" {alias} ")
            if position >= 0 and normalized in self._drug_names:
                matches.append((position, -len(alias), normalized, self._drug_names[normalized]))
        # Accept an incomplete canonical heading only when the supplied token
        # uniquely maps to one drug in the corpus. This resolves e.g. "opiat"
        # to "THUỐC PHIỆN - OPIAT - OPIOID", while ambiguous fragments such as
        # "acid" or "natri" remain unresolved instead of guessing.
        if not matches:
            assert self._unique_drug_tokens is not None
            for position, token in enumerate(fold(query).split()):
                resolved = self._unique_drug_tokens.get(token)
                if resolved:
                    normalized, display = resolved
                    matches.append((position, -len(token), normalized, display))
        # Also accept a sufficiently long, unique prefix of a canonical name.
        # Users commonly type concatenated names and stop early, e.g.
        # "natribica" for "NATRI BICARBONAT". Never resolve a prefix shared by
        # multiple headings, since near-identical drug names are safety-critical.
        if not matches:
            for position, token in enumerate(fold(query).split()):
                if len(token) < 7:
                    continue
                prefix_matches = [
                    (normalized, display)
                    for normalized, display in self._drug_names.items()
                    if normalized.startswith(token)
                ]
                if len(prefix_matches) == 1:
                    normalized, display = prefix_matches[0]
                    matches.append((position, -len(token), normalized, display))
        # Tolerate a small typo in a sufficiently long drug name.  Only accept
        # a unique, clearly better candidate: in a clinical setting an
        # ambiguous fuzzy match is worse than asking the user to clarify.
        if not matches:
            for position, token in enumerate(fold(query).split()):
                if len(token) < 7 or token in _NON_DISTINCTIVE_DRUG_TOKENS:
                    continue
                ranked = sorted(
                    (
                        SequenceMatcher(None, token, normalized).ratio(),
                        normalized,
                        display,
                    )
                    for normalized, display in self._drug_names.items()
                    if abs(len(normalized) - len(token)) <= 2
                )
                if not ranked:
                    continue
                best_score, normalized, display = ranked[-1]
                second_score = ranked[-2][0] if len(ranked) > 1 else 0.0
                # Preserve both boundaries. This keeps minor internal typos
                # (paracatamil -> paracetamol) but prevents clinically unsafe
                # look-alike matches such as budesonide -> desonid.
                same_boundaries = token[0] == normalized[0] and token[-1] == normalized[-1]
                if same_boundaries and best_score >= 0.80 and best_score - second_score >= 0.08:
                    matches.append((position, -len(token), normalized, display))
        if not matches:
            return None, None
        _, _, normalized, display = min(matches)
        return normalized, display

    @staticmethod
    def infer_section(query: str) -> str | None:
        folded_query = fold(query)
        matches = [
            (len(hint), section)
            for section, hints in SECTION_HINTS.items()
            for hint in hints
            if hint in folded_query
        ]
        return max(matches)[1] if matches else None

    @staticmethod
    def _where(drug: str | None, section: str | None) -> dict[str, Any] | None:
        conditions = []
        if drug:
            conditions.append({"normalized_drug_name": drug})
        if section:
            conditions.append({"section": section})
        conditions.append({"review_status": "approved"})
        return conditions[0] if len(conditions) == 1 else {"$and": conditions}

    def _bm25(self, query: str, candidate_ids: list[str], limit: int) -> list[str]:
        assert self._documents is not None
        query_terms = tokenize(query)
        if not query_terms or not candidate_ids:
            return []
        tokenized = {chunk_id: tokenize(self._documents[chunk_id]) for chunk_id in candidate_ids}
        average_length = sum(map(len, tokenized.values())) / max(len(tokenized), 1)
        document_frequency = Counter()
        for tokens in tokenized.values():
            document_frequency.update(set(tokens))
        scores: dict[str, float] = {}
        for chunk_id, tokens in tokenized.items():
            frequencies = Counter(tokens)
            score = 0.0
            for term in query_terms:
                frequency = frequencies[term]
                if not frequency:
                    continue
                count = document_frequency[term]
                inverse_frequency = math.log(1 + (len(tokenized) - count + 0.5) / (count + 0.5))
                denominator = frequency + 1.5 * (1 - 0.75 + 0.75 * len(tokens) / average_length)
                score += inverse_frequency * frequency * 2.5 / denominator
            scores[chunk_id] = score
        return [
            chunk_id
            for chunk_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]
            if score > 0
        ]

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        drug: str | None = None,
        section: str | None = None,
    ) -> list[RetrievalHit]:
        if not query.strip():
            return []
        self._load_lexical_index()
        assert self._documents is not None and self._metadatas is not None
        inferred_drug, _ = self.infer_drug(query)
        drug_filter = fold(drug).replace(" ", "") if drug else inferred_drug
        if not drug_filter:
            explicit = re.search(r"\bthuoc\s+([a-z0-9-]{3,})", fold(query))
            if explicit and explicit.group(1) not in {"nay", "nao", "khong", "dang"}:
                return []
        section_filter = section or self.infer_section(query)
        where = self._where(drug_filter, section_filter)

        query_embedding = self.client.embeddings.create(
            model=self.embedding_model, input=query
        ).data[0].embedding
        vector_result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=max(top_k * 4, 20),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        vector_ids = (vector_result.get("ids") or [[]])[0]

        candidate_ids = [
            chunk_id
            for chunk_id, metadata in self._metadatas.items()
            if metadata.get("review_status") == "approved"
            and (not drug_filter or metadata.get("normalized_drug_name") == drug_filter)
            and (not section_filter or metadata.get("section") == section_filter)
        ]
        lexical_ids = self._bm25(query, candidate_ids, max(top_k * 4, 20))

        # Reciprocal-rank fusion. Semantic retrieval is weighted slightly higher.
        scores: dict[str, float] = Counter()
        for rank, chunk_id in enumerate(vector_ids, start=1):
            scores[chunk_id] += 1.2 / (60 + rank)
        for rank, chunk_id in enumerate(lexical_ids, start=1):
            scores[chunk_id] += 1.0 / (60 + rank)
        ranked_ids = sorted(scores, key=scores.get, reverse=True)[:top_k]
        vector_ranks = {chunk_id: rank for rank, chunk_id in enumerate(vector_ids, 1)}
        lexical_ranks = {chunk_id: rank for rank, chunk_id in enumerate(lexical_ids, 1)}
        return [
            RetrievalHit(
                chunk_id=chunk_id,
                document=self._documents[chunk_id],
                metadata=self._metadatas[chunk_id],
                score=scores[chunk_id],
                vector_rank=vector_ranks.get(chunk_id),
                lexical_rank=lexical_ranks.get(chunk_id),
            )
            for chunk_id in ranked_ids
        ]

    def answer(self, query: str, *, top_k: int = 5, model: str = "gpt-4o-mini") -> tuple[str, list[RetrievalHit]]:
        hits = self.retrieve(query, top_k=top_k)
        if not hits:
            return "Không tìm thấy thông tin phù hợp trong Dược thư Quốc gia.", []
        return self.answer_from_hits(query, hits, model=model), hits

    def answer_from_hits(
        self, query: str, hits: list[RetrievalHit], *, model: str = "gpt-4o-mini"
    ) -> str:
        context = "\n\n".join(
            f"[Nguồn {index}] {hit.citation}\n{hit.document}"
            for index, hit in enumerate(hits, start=1)
        )
        response = self.client.responses.create(
            model=model,
            store=False,
            instructions=(
                "Bạn là trợ lý tra cứu Dược thư Quốc gia. Chỉ dùng nội dung nguồn được cung cấp; "
                "Toàn bộ câu trả lời phải bằng tiếng Việt. Chỉ giữ nguyên tên thương mại của thuốc, "
                "tên hoạt chất, tên tổ chức/nguồn và ký hiệu hoặc đơn vị chuyên môn khi chúng là tên riêng; "
                "mọi tiêu đề, trạng thái, hướng dẫn và phần giải thích khác phải viết bằng tiếng Việt. "
                "Không dùng các nhãn tiếng Anh như Drug, Schedule, Status, Taken, Pending, Missed, Next dose hay Source. "
                "không tự suy diễn, không kê đơn hay thay đổi liều. Mọi khẳng định y khoa phải gắn "
                "[Nguồn N]. MỖI câu chứa thông tin y khoa phải tự kết thúc bằng đúng citation dạng "
                "[Nguồn 1]., kể cả các câu liên tiếp trong cùng đoạn; không để citation chung ở cuối đoạn. "
                "Giữ nguyên chủ thể, đối tượng, chiều tương tác và số liệu như nguồn, tuyệt đối không đảo "
                "quan hệ. Ví dụ hợp lệ: 'Diphenhydramin làm giảm hấp thu PAS [Nguồn 1].' "
                "Nếu nguồn không đủ, nói rõ không đủ thông tin và khuyên hỏi bác sĩ/dược sĩ. "
                "Chỉ trả lời đúng đề mục người dùng hỏi; bỏ thông tin ở đề mục lân cận. "
                "Chọn số claim tối thiểu nhưng đủ trả lời và diễn đạt sát câu chữ của nguồn. "
                "Không thêm câu khái quát, nhóm hóa, suy rộng hoặc cụm mơ hồ như 'và nhiều loại khác' "
                "nếu nguồn không nói nguyên văn điều đó. Mỗi câu phải tự chứa claim đầy đủ và citation; "
                "không tách claim và citation thành hai câu. Trả lời bằng danh sách gạch đầu dòng; mỗi "
                "gạch đầu dòng chỉ có đúng một câu và câu đó phải kết thúc bằng [Nguồn N]. Không viết "
                "câu mở đầu hoặc câu kết luận y khoa không có citation. Ưu tiên ít câu ngắn, trực tiếp "
                "được nguồn hỗ trợ thay vì cố liệt kê mọi liều cho mọi nhóm người bệnh. Không dùng "
                "đại từ ngôi thứ nhất hoặc thứ hai như 'tôi', 'bạn', 'em'; chỉ diễn đạt thông tin tra "
                "cứu trung tính bằng tên thuốc hoặc nhóm đối tượng ghi trong nguồn."
            ),
            input=f"Câu hỏi: {query}\n\nNguồn tra cứu:\n{context}",
        )
        return response.output_text
