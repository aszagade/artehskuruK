from __future__ import annotations

from typing import TYPE_CHECKING

from .database_bm25 import DatabaseBM25Retriever
from .vector import VectorRetriever

if TYPE_CHECKING:
    from .access_control import VisibilityFilter


def _min_max_normalize(scores: list[float]) -> list[float]:
    """Min-max normalize a list of scores to [0, 1].

    Safe for empty lists, single elements, and equal scores.
    """
    if not scores:
        return []
    if len(scores) == 1:
        return [1.0]
    mn = min(scores)
    mx = max(scores)
    if mx == mn:
        return [1.0] * len(scores)
    rng = mx - mn
    return [(s - mn) / rng for s in scores]


class HybridRetriever:
    def __init__(
        self,
        vis_filter: VisibilityFilter | None = None,
        bm25_weight: float = 0.5,
        vector_weight: float = 0.5,
    ):
        self.bm25 = DatabaseBM25Retriever(vis_filter=vis_filter)
        self.vector = VectorRetriever(vis_filter=vis_filter)
        self.vis_filter = vis_filter
        self.bm25_weight = bm25_weight
        self.vector_weight = vector_weight

    def search(self, query: str, top_k: int = 5):
        bm25_results = self.bm25.search(query, top_k=10)
        vector_results = self.vector.search(query, top_k=10)

        # Collect raw scores for normalization
        bm25_raw = {r.chunk_id: r.score for r in bm25_results}
        vector_raw = {r.chunk_id: r.score for r in vector_results}

        bm25_ids = list(bm25_raw.keys())
        vector_ids = list(vector_raw.keys())

        # Normalize each strategy independently to [0, 1]
        bm25_norm = {
            cid: s
            for cid, s in zip(bm25_ids, _min_max_normalize([bm25_raw[cid] for cid in bm25_ids]))
        }
        vector_norm = {
            cid: s
            for cid, s in zip(vector_ids, _min_max_normalize([vector_raw[cid] for cid in vector_ids]))
        }

        # Build result lookup from the richer source (vector has text, bm25 has text)
        result_lookup: dict[str, object] = {}
        for r in bm25_results:
            result_lookup[r.chunk_id] = r
        for r in vector_results:
            if r.chunk_id not in result_lookup:
                result_lookup[r.chunk_id] = r

        # Fuse normalized scores
        all_ids = set(bm25_ids) | set(vector_ids)
        fused: list[tuple[str, float]] = []
        for cid in all_ids:
            b = bm25_norm.get(cid, 0.0)
            v = vector_norm.get(cid, 0.0)
            fused.append((cid, b * self.bm25_weight + v * self.vector_weight))

        # Sort by fused score descending
        fused.sort(key=lambda x: x[1], reverse=True)

        merged = []
        for cid, score in fused:
            result = result_lookup[cid]
            result.score = score
            merged.append(result)

        if self.vis_filter is not None:
            merged = self.vis_filter.filter(merged)

        return merged[:top_k]