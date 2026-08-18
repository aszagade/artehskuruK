from __future__ import annotations
import math
from collections import Counter

from kurukshetra.chunking.models import Chunk
from .base import BaseRetriever
from .models import RetrievalResult


class BM25Retriever(BaseRetriever):
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.docs = [c.text.lower().split() for c in chunks]
        self.avgdl = sum(len(d) for d in self.docs) / max(len(self.docs), 1)

    def search(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        q = query.lower().split()
        results = []

        for chunk, doc in zip(self.chunks, self.docs):
            tf = Counter(doc)
            score = 0.0

            for term in q:
                df = sum(term in d for d in self.docs)
                if df == 0:
                    continue
                idf = math.log((len(self.docs)-df+0.5)/(df+0.5)+1)
                freq = tf[term]
                dl = len(doc)
                score += idf * (freq*2.5)/(freq+1.5*(1-0.75+0.75*dl/self.avgdl))

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

        return sorted(results, key=lambda x: x.score, reverse=True)[:top_k]