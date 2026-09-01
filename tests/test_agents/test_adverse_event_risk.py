from src.agents.adverse_event_risk import classify_adverse_event_risk


def test_adverse_event_risk_critical_keywords_override_llm_severity():
    assert (
        classify_adverse_event_risk("Tôi bị khó thở sau khi uống thuốc", [{"name": "mệt", "severity": "MILD"}])
        == "CRITICAL"
    )


def test_adverse_event_risk_uses_structured_severity_for_non_emergency():
    assert classify_adverse_event_risk("Tôi hơi buồn nôn", [{"name": "buồn nôn", "severity": "MODERATE"}]) == "MODERATE"
    assert classify_adverse_event_risk("Tôi hơi ngứa", [{"name": "ngứa", "severity": "MILD"}]) == "LOW"
