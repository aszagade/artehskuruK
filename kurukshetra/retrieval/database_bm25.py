from __future__ import annotations

from kurukshetra.registry.chunks import ChunkRepository

from .bm25 import BM25Retriever
from .models import RetrievalResult


class DatabaseBM25Retriever:
    """BM25 retriever backed by persisted DuckDB chunks."""

    def __init__(self) -> None:
        self.repository = ChunkRepository()

    def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        chunks = self.repository.load()
        retriever = BM25Retriever(chunks)
        return retriever.search(query, top_k)