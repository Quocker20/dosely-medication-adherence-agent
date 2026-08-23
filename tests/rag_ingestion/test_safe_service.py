from src.rag_retrieval.safe_service import SafeDrugRAG
from src.rag_retrieval.service import RetrievalHit


class FakeRAG:
    def __init__(self, hits=None, answer=""):
        self.hits = hits or []
        self.answer = answer
        self.answer_calls = 0
        self.retrieve_calls = 0

    def retrieve(self, _question, top_k=5):
        self.retrieve_calls += 1
        return self.hits[:top_k]

    def answer_from_hits(self, _question, _hits, model):
        self.answer_calls += 1
        assert model == "gpt-4o-mini"
        return self.answer


def hit():
    return RetrievalHit(
        "c1", "Acid ascorbic điều trị thiếu vitamin C.",
        {"drug_name": "ACID ASCORBIC", "section": "indications", "section_label": "Chỉ định", "page_start": 1, "page_end": 1},
        0.5,
    )


def test_safe_service_blocks_before_retrieval_generation():
    rag = FakeRAG([hit()], "unused")
    result = SafeDrugRAG(rag=rag).query("Tôi tăng gấp đôi liều được không?")
    assert result.status == "safety_blocked"
    assert not result.sources
    assert rag.answer_calls == 0


def test_safe_service_blocks_personal_paracetamol_after_alcohol_before_retrieval():
    rag = FakeRAG([hit()], "unused")
    result = SafeDrugRAG(rag=rag).query(
        "Tối hôm qua tôi có uống bia thì tôi có uống paracetamol nữa được không?"
    )
    assert result.status == "safety_blocked"
    assert result.safety_reason == "TAKE_MEDICATION_DECISION"
    assert not result.sources
    assert rag.retrieve_calls == 0
    assert rag.answer_calls == 0


def test_safe_service_returns_no_data_without_generation():
    rag = FakeRAG()
    result = SafeDrugRAG(rag=rag).query("Thuốc không tồn tại có chỉ định gì?")
    assert result.status == "no_data"
    assert rag.answer_calls == 0


def test_safe_service_accepts_grounded_generation():
    rag = FakeRAG([hit()], "Acid ascorbic điều trị thiếu vitamin C [Nguồn 1].")
    result = SafeDrugRAG(rag=rag).query("Acid ascorbic có chỉ định gì?")
    assert result.status == "answered"
    assert result.grounding_valid is True
    assert len(result.sources) == 1


def test_safe_service_replaces_ungrounded_generation():
    rag = FakeRAG([hit()], "Thuốc này chữa khỏi mọi bệnh.")
    result = SafeDrugRAG(rag=rag).query("Acid ascorbic có chỉ định gì?")
    assert result.status == "grounding_blocked"
    assert result.grounding_valid is False


def test_safe_service_retries_one_grounding_failure_and_returns_repaired_answer():
    class RepairingRAG(FakeRAG):
        def answer_from_hits(self, _question, _hits, model):
            self.answer_calls += 1
            assert model == "gpt-4o-mini"
            if self.answer_calls == 1:
                return "Bạn có thể dùng thuốc này [Nguồn 1]."
            return "Acid ascorbic điều trị thiếu vitamin C [Nguồn 1]."

    rag = RepairingRAG([hit()])
    result = SafeDrugRAG(rag=rag).query("Acid ascorbic có chỉ định gì?")
    assert result.status == "answered"
    assert result.grounding_valid is True
    assert result.answer == "Acid ascorbic điều trị thiếu vitamin C [Nguồn 1]."
    assert rag.answer_calls == 2


def test_greeting_does_not_retrieve_or_generate():
    rag = FakeRAG([hit()], "unused")
    result = SafeDrugRAG(rag=rag).query("Xin chào")
    assert result.status == "greeting"
    assert "Dược thư Quốc gia" in result.answer
    assert rag.retrieve_calls == 0
    assert rag.answer_calls == 0


def test_capability_question_does_not_retrieve_or_generate():
    rag = FakeRAG([hit()], "unused")
    result = SafeDrugRAG(rag=rag).query("Bạn làm được gì?")
    assert result.status == "capability"
    assert "tra cứu" in result.answer
    assert rag.retrieve_calls == 0
    assert rag.answer_calls == 0


def test_out_of_scope_question_is_blocked_before_retrieval():
    rag = FakeRAG([hit()], "unused")
    result = SafeDrugRAG(rag=rag).query("Hôm nay tôi ăn gì vào buổi tối?")
    assert result.status == "out_of_scope"
    assert rag.retrieve_calls == 0
    assert rag.answer_calls == 0


def test_political_question_is_blocked_before_retrieval():
    rag = FakeRAG([hit()], "unused")
    result = SafeDrugRAG(rag=rag).query("Hoàng Sa Trường Sa là của nước nào?")
    assert result.status == "out_of_scope"
    assert rag.retrieve_calls == 0


def test_ambiguous_drug_reference_requests_name():
    rag = FakeRAG([hit()], "unused")
    result = SafeDrugRAG(rag=rag).query("Thuốc này có tác dụng gì?")
    assert result.status == "needs_drug_name"
    assert rag.retrieve_calls == 0


def test_unknown_drug_name_never_runs_unfiltered_semantic_retrieval():
    class ResolvingRAG(FakeRAG):
        def infer_drug(self, _question):
            return None, None

    rag = ResolvingRAG([hit()], "unused")
    result = SafeDrugRAG(rag=rag).query(
        "natribica dùng như thế nào, có tương kỵ và liều dùng ra sao?"
    )

    assert result.status == "needs_drug_name"
    assert rag.retrieve_calls == 0
    assert rag.answer_calls == 0


def test_explicit_follow_up_uses_drug_from_conversation_context():
    class ContextRAG(FakeRAG):
        def __init__(self):
            super().__init__([hit()], "Acid ascorbic điều trị thiếu vitamin C [Nguồn 1].")
            self.retrieved_drug = None

        def infer_drug(self, _question):
            return None, None

        def retrieve(self, _question, top_k=5, drug=None):
            self.retrieve_calls += 1
            self.retrieved_drug = drug
            return self.hits[:top_k]

    rag = ContextRAG()
    result = SafeDrugRAG(rag=rag).query(
        "Thuốc vừa nãy là thuốc gì?",
        context_drug=("acidascorbic", "ACID ASCORBIC"),
    )

    assert result.status == "answered"
    assert rag.retrieved_drug == "ACID ASCORBIC"
