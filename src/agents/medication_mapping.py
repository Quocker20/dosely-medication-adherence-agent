"""Verified medication catalog -> formulary identity mapping.

Brand names are resolved through the relational catalog's composition. Fuzzy
matching never creates a clinical identity here; it remains a spelling aid in
the formulary resolver after the active ingredient has been established.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.rag_retrieval.service import DrugRAG

_STRENGTH = re.compile(
    r"(?<!\w)\d+(?:[.,]\d+)?\s*(?:mg|mcg|µg|g|ml|iu|ui|%|billion\s+spores?)"
    r"(?:\s*(?:w/w|w/v|v/v|mg/g|mg/ml))?(?=\s|$|[),;+])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FormularyIdentity:
    catalog_name: str
    ingredient: str
    normalized_drug_name: str
    formulary_name: str


def ingredient_candidates(composition: str) -> list[str]:
    """Extract active ingredient names without strengths from catalog text."""
    candidates = []
    for raw in re.split(r"\s*[;+]\s*", composition or ""):
        cleaned = _STRENGTH.sub("", raw)
        cleaned = re.sub(r"[()]", " ", cleaned)
        cleaned = " ".join(cleaned.split()).strip(" -,/")
        if cleaned:
            candidates.append(cleaned)
    return candidates


def resolve_catalog_medication(
    catalog_name: str, composition: str, rag: DrugRAG
) -> list[FormularyIdentity]:
    """Resolve catalog ingredients to reviewed formulary headings."""
    resolved: list[FormularyIdentity] = []
    for ingredient in ingredient_candidates(composition):
        normalized, display = rag.infer_drug(ingredient)
        if normalized and display:
            resolved.append(FormularyIdentity(catalog_name, ingredient, normalized, display))
    return resolved
