"""Deterministic ingestion pipeline for the Vietnamese National Formulary."""

from src.rag_ingestion.pipeline import build_corpus, filter_chunks

__all__ = ["build_corpus", "filter_chunks"]
