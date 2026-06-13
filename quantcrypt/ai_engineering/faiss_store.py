from __future__ import annotations

from pathlib import Path

import faiss
import numpy

from .embeddings import EmbeddingModel, HashEmbeddingModel
from .reports import MemoryDocument


class FaissVectorStore:
    def __init__(
        self,
        *,
        index_path: str | Path,
        embedding_model: EmbeddingModel | None = None,
    ) -> None:
        self.index_path = Path(index_path)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.embedding_model = embedding_model or HashEmbeddingModel()
        self.index = self._load_or_create_index()

    def _load_or_create_index(self):
        if self.index_path.exists():
            return faiss.read_index(str(self.index_path))
        return faiss.IndexIDMap2(faiss.IndexFlatIP(self.embedding_model.dimension))

    def _persist(self) -> None:
        faiss.write_index(self.index, str(self.index_path))

    def add_memory_documents(self, documents: list[MemoryDocument]) -> int:
        if not documents:
            return 0
        ids = [document.memory_id for document in documents]
        if any(memory_id is None for memory_id in ids):
            raise ValueError("All memory documents must have ids before indexing")
        vectors = self.embedding_model.embed_texts([document.content for document in documents]).astype("float32")
        faiss.normalize_L2(vectors)
        self.index.add_with_ids(vectors, numpy.array(ids, dtype="int64"))
        self._persist()
        return len(documents)

    def search(self, query_text: str, *, top_k: int = 5) -> list[tuple[int, float]]:
        if self.index.ntotal == 0:
            return []
        query_vector = self.embedding_model.embed_texts([query_text]).astype("float32")
        faiss.normalize_L2(query_vector)
        scores, ids = self.index.search(query_vector, top_k)
        results: list[tuple[int, float]] = []
        for memory_id, score in zip(ids[0], scores[0], strict=False):
            if int(memory_id) == -1:
                continue
            results.append((int(memory_id), float(score)))
        return results

