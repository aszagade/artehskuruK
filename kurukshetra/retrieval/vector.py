from __future__ import annotations

import math

from kurukshetra.embeddings import BGEEmbedding
from kurukshetra.registry.chunks import ChunkRepository
from kurukshetra.registry.vectors import VectorRepository
from .models import RetrievalResult


class VectorRetriever:
    def __init__(self):
        self.embedder = BGEEmbedding()
        self.chunk_repo = ChunkRepository()
        self.vector_repo = VectorRepository()

    def _cosine(self, a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb)

    def search(self, query: str, top_k: int = 5):
        q = self.embedder.embed(query)

        chunks = {
            c.chunk_id: c
            for c in self.chunk_repo.load()
        }

        results = []

        for chunk_id, vec in self.vector_repo.load():
            score = self._cosine(q, vec)

            chunk = chunks.get(chunk_id)
            if chunk:
                results.append(
                    RetrievalResult(
                        chunk_id=chunk.chunk_id,
                        document_id=chunk.document_id,
                        score=score,
                        text=chunk.text,
                        metadata={},
                    )
                )

        return sorted(
            results,
            key=lambda x: x.score,
            reverse=True,
        )[:top_k]