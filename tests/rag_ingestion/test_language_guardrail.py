import pytest

from src.rag_retrieval.language_guardrail import detect_supported_language


@pytest.mark.parametrize(
    ("question", "recognized_drug", "expected"),
    [
        ("Paracetamol có tác dụng gì?", True, "vi"),
        ("Paracetamol co tac dung gi?", True, "vi"),
        ("What is paracetamol used for?", True, "en"),
        ("Paracetamol?", True, "en"),
        ("À quoi sert le paracétamol ?", True, None),
        ("Wofür wird Paracetamol verwendet?", True, None),
        ("¿Para qué se utiliza el paracetamol?", True, None),
        ("对乙酰氨基酚有什么作用？", False, None),
        ("パラセタモールの作用は何ですか？", False, None),
    ],
)
def test_language_allow_list(question: str, recognized_drug: bool, expected: str | None):
    assert detect_supported_language(question, recognized_drug=recognized_drug) == expected
