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
    """

    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self.documents = [chunk.text.lower().split() for chunk in chunks]

        if self.documents:
            self.avgdl = sum(len(doc) for doc in self.documents) / len(self.documents)
        else:
            self.avgdl = 0.0

    def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        if not self.chunks:
            return []

        query_terms = query.lower().split()
        results: list[RetrievalResult] = []

        total_docs = len(self.documents)
        k1 = 1.5
        b = 0.75

        for chunk, doc in zip(self.chunks, self.documents):
            term_freq = Counter(doc)
            score = 0.0

            for term in query_terms:
                document_frequency = sum(term in d for d in self.documents)

                if document_frequency == 0:
                    continue

                idf = math.log(
                    ((total_docs - document_frequency + 0.5) /
                     (document_frequency + 0.5)) + 1
                )

                frequency = term_freq[term]
                document_length = len(doc)

                denominator = (
                    frequency +
                    k1 * (1 - b + b * document_length / max(self.avgdl, 1))
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