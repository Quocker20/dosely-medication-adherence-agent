from types import SimpleNamespace

from src.rag_retrieval.input_guardrail import contextual_drug_offset
from src.rag_retrieval.service import DrugRAG, fold


class FakeCollection:
    def __init__(self):
        self.ids = ["a", "b", "c"]
        self.documents = [
            "Thuốc: ACID ASCORBIC\nMục: Tương tác thuốc\nDiphenhydramin làm giảm hấp thu.",
            "Thuốc: ACID ASCORBIC\nMục: Chỉ định\nĐiều trị thiếu vitamin C.",
            "Thuốc: ACICLOVIR\nMục: Tương tác thuốc\nNội dung khác.",
        ]
        self.metadatas = [
            {"drug_name": "ACID ASCORBIC", "normalized_drug_name": "acidascorbic", "section": "interactions", "section_label": "Tương tác thuốc", "page_start": 10, "page_end": 10, "review_status": "approved"},
            {"drug_name": "ACID ASCORBIC", "normalized_drug_name": "acidascorbic", "section": "indications", "section_label": "Chỉ định", "page_start": 11, "page_end": 11, "review_status": "approved"},
            {"drug_name": "ACICLOVIR", "normalized_drug_name": "aciclovir", "section": "interactions", "section_label": "Tương tác thuốc", "page_start": 12, "page_end": 12, "review_status": "approved"},
        ]

    def get(self, **_kwargs):
        return {"ids": self.ids, "documents": self.documents, "metadatas": self.metadatas}

    def query(self, **kwargs):
        where = kwargs["where"]
        conditions = where.get("$and", [where])
        selected = []
        for index, metadata in enumerate(self.metadatas):
            if all(all(metadata.get(key) == value for key, value in condition.items()) for condition in conditions):
                selected.append(index)
        return {"ids": [[self.ids[i] for i in selected]], "documents": [[self.documents[i] for i in selected]], "metadatas": [[self.metadatas[i] for i in selected]], "distances": [[0.1] * len(selected)]}


class FakeEmbeddings:
    def create(self, **_kwargs):
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2])])


def test_fold_vietnamese_text():
    assert fold("Tương tác THUỐC") == "tuong tac thuoc"


def test_hybrid_retrieval_applies_drug_and_section_filters():
    client = SimpleNamespace(embeddings=FakeEmbeddings())
    rag = DrugRAG(collection=FakeCollection(), client=client)
    hits = rag.retrieve("Acid ascorbic tương tác với diphenhydramin thế nào?")
    assert [hit.chunk_id for hit in hits] == ["a"]
    assert hits[0].metadata["drug_name"] == "ACID ASCORBIC"
    assert "trang 10" in hits[0].citation


def test_alias_is_preferred_over_interacting_drug_mentioned_later():
    collection = FakeCollection()
    collection.ids.append("pas")
    collection.documents.append("Thuốc: ACID AMINOSALICYLIC\nDiphenhydramin làm giảm hấp thu PAS.")
    collection.metadatas.append(
        {"drug_name": "ACID AMINOSALICYLIC", "normalized_drug_name": "acidaminosalicylic", "section": "interactions", "section_label": "Tương tác thuốc", "page_start": 20, "page_end": 20, "review_status": "approved"}
    )
    rag = DrugRAG(collection=collection, client=SimpleNamespace(embeddings=FakeEmbeddings()))
    hits = rag.retrieve("PAS tương tác với diphenhydramin như thế nào?")
    assert [hit.chunk_id for hit in hits] == ["pas"]


def test_unique_partial_heading_resolves_to_drug() -> None:
    collection = FakeCollection()
    collection.ids.append("opiat")
    collection.documents.append(
        "Thuốc: THUỐC PHIỆN - OPIAT - OPIOID\nMục: Dược lực học\nOpiat là alcaloid tự nhiên."
    )
    collection.metadatas.append(
        {
            "drug_name": "THUỐC PHIỆN - OPIAT - OPIOID",
            "normalized_drug_name": "thuocphienopiatopioid",
            "section": "pharmacodynamics",
            "section_label": "Dược lực học",
            "page_start": 696,
            "page_end": 696,
            "review_status": "approved",
        }
    )
    rag = DrugRAG(collection=collection, client=SimpleNamespace(embeddings=FakeEmbeddings()))

    assert rag.infer_drug("opiat là gì?") == (
        "thuocphienopiatopioid",
        "THUỐC PHIỆN - OPIAT - OPIOID",
    )


def test_ambiguous_or_generic_partial_heading_is_not_guessed() -> None:
    rag = DrugRAG(
        collection=FakeCollection(), client=SimpleNamespace(embeddings=FakeEmbeddings())
    )

    assert rag.infer_drug("acid là gì?") == (None, None)


def test_unique_concatenated_prefix_resolves_incomplete_drug_name() -> None:
    collection = FakeCollection()
    collection.ids.append("natri-bicarbonat")
    collection.documents.append("Thuốc: NATRI BICARBONAT\nMục: Thông tin định danh")
    collection.metadatas.append(
        {
            "drug_name": "NATRI BICARBONAT",
            "normalized_drug_name": "natribicarbonat",
            "section": "identity",
            "section_label": "Thông tin định danh",
            "page_start": 293,
            "page_end": 293,
            "review_status": "approved",
        }
    )
    rag = DrugRAG(collection=collection, client=SimpleNamespace(embeddings=FakeEmbeddings()))

    assert rag.infer_drug("natribica dùng như thế nào?") == (
        "natribicarbonat",
        "NATRI BICARBONAT",
    )


def test_conversation_reference_selects_current_or_previous_drug_topic() -> None:
    assert contextual_drug_offset("Thuốc vừa nãy là thuốc gì?") == -1
    assert contextual_drug_offset("Thuốc trước thuốc vừa nãy hỏi là gì?") == -2
    assert contextual_drug_offset("Loại thuốc trước đó có tác dụng gì?") == -2
