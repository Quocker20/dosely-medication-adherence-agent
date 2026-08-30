"""Deterministic risk classification; never diagnoses medication causality."""
from src.rag_retrieval.service import fold

_CRITICAL = ("kho tho", "sung moi", "sung luoi", "bat tinh", "ngat", "dau nguc", "tuc nguc", "co giat")
_HIGH = ("phat ban toan than", "non lien tuc", "choang", "chong mat nang", "tim dap nhanh")


def classify_adverse_event_risk(raw_text: str, symptoms: list[dict]) -> str:
    text = fold(raw_text + " " + " ".join(str(item.get("name", "")) for item in symptoms))
    if any(marker in text for marker in _CRITICAL): return "CRITICAL"
    if any(marker in text for marker in _HIGH): return "HIGH"
    levels = {str(item.get("severity", "MILD")).upper() for item in symptoms}
    if "SEVERE" in levels: return "HIGH"
    if "MODERATE" in levels: return "MODERATE"
    return "LOW"
