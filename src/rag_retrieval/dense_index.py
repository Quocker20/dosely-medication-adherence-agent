from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


class DenseIndex:
    """Small exact-cosine vector store backed by NumPy and JSONL."""

    def __init__(self, directory: Path) -> None:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        self.model = manifest["embedding_model"]
        self.vectors = np.load(directory / "vectors.npy", mmap_mode="r")
        records = [
            json.loads(line)
            for line in (directory / "records.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        if len(records) != self.vectors.shape[0]:
            raise ValueError("Dense index records/vector count mismatch")
        self.ids = [record["id"] for record in records]
        self.documents = [record["document"] for record in records]
        self.metadatas = [record["metadata"] for record in records]

    @staticmethod
    def _matches(metadata: dict[str, Any], where: dict[str, Any] | None) -> bool:
        if not where:
            return True
        conditions = where.get("$and", [where])
        return all(
            all(metadata.get(key) == value for key, value in condition.items())
            for condition in conditions
        )

    def get(self, **_kwargs: Any) -> dict[str, Any]:
        return {"ids": self.ids, "documents": self.documents, "metadatas": self.metadatas}

    def query(
        self,
        *,
        query_embeddings: list[list[float]],
        n_results: int,
        where: dict[str, Any] | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        query = np.asarray(query_embeddings[0], dtype=np.float32)
        query /= max(float(np.linalg.norm(query)), 1e-12)
        candidates = np.asarray(
            [index for index, metadata in enumerate(self.metadatas) if self._matches(metadata, where)],
            dtype=np.int64,
        )
        if not len(candidates):
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        similarities = np.asarray(self.vectors[candidates] @ query)
        order = np.argsort(-similarities)[:n_results]
        selected = candidates[order]
        return {
            "ids": [[self.ids[index] for index in selected]],
            "documents": [[self.documents[index] for index in selected]],
            "metadatas": [[self.metadatas[index] for index in selected]],
            "distances": [[float(1 - similarities[position]) for position in order]],
        }
