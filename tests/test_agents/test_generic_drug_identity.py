from types import SimpleNamespace
import pytest
from langchain_core.messages import HumanMessage
from src.agents.nodes import drug_rag_node as module


def source(name):
    return SimpleNamespace(drug_name=name, citation="Dược thư", section="indications", excerpt="excerpt")


@pytest.mark.asyncio
async def test_brand_maps_to_ingredient_before_rag(monkeypatch):
    seen = {}

    class IdentityRag:
        def infer_drug(self, value):
            return ("doxycyclin", "DOXYCYCLIN") if "Doxycycline" in value else (None, None)

    class SafeRag:
        rag = IdentityRag()
        def query(self, _question, **kwargs):
            seen["context"] = kwargs.get("context_drug")
            return SimpleNamespace(answer="Doxycyclin là kháng sinh.", status="answered",
                                   grounding_valid=True, grounding_errors=[], sources=[source("DOXYCYCLIN")])

    async def fake_get(*_args, **_kwargs):
        return {"content": [{"name": "A Doxid 100mg Capsule", "composition": "Doxycycline 100mg"}]}

    monkeypatch.setattr(module, "_get_rag_service", lambda: SafeRag())
    monkeypatch.setattr(module, "get", fake_get)
    result = await module.drug_rag_node({
        "messages": [HumanMessage(content="A Doxid 100mg Capsule thường để làm gì?")],
        "intent_analysis": {"drug_name": "A Doxid 100mg Capsule"},
    })
    assert seen["context"] == ("doxycyclin", "DOXYCYCLIN")
    assert result["grounding_valid"] is True


@pytest.mark.asyncio
async def test_source_from_another_drug_is_rejected(monkeypatch):
    class IdentityRag:
        def infer_drug(self, _value):
            return "doxycyclin", "DOXYCYCLIN"

    class SafeRag:
        rag = IdentityRag()
        def query(self, _question, **_kwargs):
            return SimpleNamespace(answer="Sai thuốc.", status="answered", grounding_valid=True,
                                   grounding_errors=[], sources=[source("THAN HOẠT")])

    monkeypatch.setattr(module, "_get_rag_service", lambda: SafeRag())
    result = await module.drug_rag_node({
        "messages": [HumanMessage(content="Doxycycline dùng làm gì?")],
        "intent_analysis": {"drug_name": "Doxycycline"},
    })
    assert result["grounding_valid"] is False
    assert result["grounding_errors"] == ["drug_identity_mismatch"]


@pytest.mark.asyncio
async def test_combination_brand_queries_every_catalogued_ingredient(monkeypatch):
    seen = {}

    class IdentityRag:
        def infer_drug(self, value):
            mapping = {
                "Clindamycin": ("clindamycin", "CLINDAMYCIN"),
                "Nicotinamide": ("nicotinamid", "NICOTINAMID"),
            }
            return mapping.get(value, (None, None))

    class SafeRag:
        rag = IdentityRag()

        def query(self, _question, **kwargs):
            seen["contexts"] = kwargs.get("context_drugs")
            return SimpleNamespace(
                answer="Hai hoạt chất được dùng trong điều trị mụn.",
                status="answered",
                grounding_valid=True,
                grounding_errors=[],
                sources=[source("CLINDAMYCIN"), source("NICOTINAMID")],
            )

    async def fake_get(*_args, **_kwargs):
        return {"content": [{
            "name": "A-CN Gel",
            "composition": "Clindamycin (1% w/w) + Nicotinamide (4% w/w)",
        }]}

    monkeypatch.setattr(module, "_get_rag_service", lambda: SafeRag())
    monkeypatch.setattr(module, "get", fake_get)
    result = await module.drug_rag_node({
        "messages": [HumanMessage(content="A-CN Gel thường để làm gì?")],
        "intent_analysis": {"drug_name": "A-CN Gel"},
    })

    assert seen["contexts"] == [
        ("clindamycin", "CLINDAMYCIN"),
        ("nicotinamid", "NICOTINAMID"),
    ]
    assert result["grounding_valid"] is True
    assert {item["drug_name"] for item in result["rag_sources"]} == {
        "CLINDAMYCIN", "NICOTINAMID",
    }


@pytest.mark.asyncio
async def test_catalog_only_drug_is_not_presented_as_grounded_clinical_answer(monkeypatch):
    class IdentityRag:
        def infer_drug(self, _value):
            return None, None

    class SafeRag:
        rag = IdentityRag()

        def query(self, _question, **_kwargs):
            return SimpleNamespace(
                answer="Ngoài phạm vi.", status="out_of_scope",
                grounding_valid=True, grounding_errors=[], sources=[],
            )

    async def fake_get(*_args, **_kwargs):
        return {"content": [{
            "name": "Beclometasone",
            "composition": "Beclometasone",
            "uses": "",
            "source_name": "WHO_EML_2023_STARTER",
        }]}

    monkeypatch.setattr(module, "_get_rag_service", lambda: SafeRag())
    monkeypatch.setattr(module, "get", fake_get)
    result = await module.drug_rag_node({
        "messages": [HumanMessage(content="Beclometasone có tác dụng gì?")],
        "intent_analysis": {"drug_name": "Beclometasone"},
    })

    assert result["grounding_valid"] is False
    assert result["grounding_errors"] == ["catalog_missing_verified_uses"]
    assert result["refusal_reason"] == "catalog_missing_verified_uses"
    assert result["metadata"]["catalog_medication"]["name"] == "Beclometasone"
