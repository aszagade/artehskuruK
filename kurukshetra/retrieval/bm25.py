from __future__ import annotations

import math
from collections import Counter

from kurukshetra.chunking.models import Chunk

from .base import BaseRetriever
from .models import RetrievalResult


class BM25Retriever(BaseRetriever):
    """
    Deterministic BM25 lexical retriever.

    Operates on persisted Chunk objects and returns RetrievalResult.
    Precomputes document frequency and token frequencies on init
    so that search() is O(k * n) instead of O(k * n^2).
    """

    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self.documents = [chunk.text.lower().split() for chunk in chunks]

        if self.documents:
            self.avgdl = sum(len(doc) for doc in self.documents) / len(self.documents)
        else:
            self.avgdl = 0.0

        # Precompute document frequency for all terms (O(n * avg_len))
        self.total_docs = len(self.documents)
        self._df: dict[str, int] = {}
        for doc in self.documents:
            seen = set(doc)
            for term in seen:
                self._df[term] = self._df.get(term, 0) + 1

        # Precompute term frequency per document
        self._tf: list[Counter] = [Counter(doc) for doc in self.documents]

    def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        if not self.chunks:
            return []

        query_terms = query.lower().split()
        results: list[RetrievalResult] = []

        k1 = 1.5
        b = 0.75

        for i, chunk in enumerate(self.chunks):
            doc = self.documents[i]
            doc_len = len(doc)
            score = 0.0

            for term in query_terms:
                document_frequency = self._df.get(term, 0)

                if document_frequency == 0:
                    continue

                idf = math.log(
                    ((self.total_docs - document_frequency + 0.5) /
                     (document_frequency + 0.5)) + 1
                )

                frequency = self._tf[i][term]

                denominator = (
                    frequency +
                    k1 * (1 - b + b * doc_len / max(self.avgdl, 1))
                )

                score += idf * ((frequency * (k1 + 1)) / denominator)

            if score > 0:
                results.append(
                    RetrievalResult(
                        chunk_id=chunk.chunk_id,
                        document_id=chunk.document_id,
                        score=score,
                        text=chunk.text,
                        metadata={},
                    )
                )

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:top_k]