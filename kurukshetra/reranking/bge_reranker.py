from __future__ import annotations

from sentence_transformers import CrossEncoder


class BGEReranker:
    model_name = "BAAI/bge-reranker-v2-m3"

    def __init__(self):
        self.model = CrossEncoder(self.model_name)

    def rerank(self, query: str, results, top_k: int = 3):
        pairs = [[query, r.text] for r in results]
        scores = self.model.predict(pairs)

        for r, s in zip(results, scores):
            r.score = float(s)

        return sorted(results, key=lambda x: x.score, reverse=True)[:top_k]