from __future__ import annotations

from .database_bm25 import DatabaseBM25Retriever
from .vector import VectorRetriever


class HybridRetriever:
    def __init__(self):
        self.bm25 = DatabaseBM25Retriever()
        self.vector = VectorRetriever()

    def search(self, query: str, top_k: int = 5):
        scores = {}

        for r in self.bm25.search(query, top_k=10):
            scores[r.chunk_id] = {
                "result": r,
                "score": r.score * 0.4,
            }

        for r in self.vector.search(query, top_k=10):
            if r.chunk_id in scores:
                scores[r.chunk_id]["score"] += r.score * 0.6
            else:
                scores[r.chunk_id] = {
                    "result": r,
                    "score": r.score * 0.6,
                }

        merged = []
        for item in scores.values():
            result = item["result"]
            result.score = item["score"]
            merged.append(result)

        return sorted(
            merged,
            key=lambda x: x.score,
            reverse=True,
        )[:top_k]