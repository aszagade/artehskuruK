from __future__ import annotations

from kurukshetra.registry.chunks import ChunkRepository

from .bm25 import BM25Retriever
from .models import RetrievalResult


class DatabaseBM25Retriever:
    """BM25 retriever backed by persisted DuckDB chunks.

    Caches the BM25 index after first search. Refreshes automatically
    when new documents are ingested (detected by chunk count change).
    """

    def __init__(self) -> None:
        self.repository = ChunkRepository()
        self._retriever: BM25Retriever | None = None
        self._chunk_count: int = 0

    def _ensure_index(self) -> BM25Retriever:
        """Build or refresh the BM25 index if chunks changed."""
        current_count = self._current_chunk_count()
        if self._retriever is None or current_count != self._chunk_count:
            chunks = self.repository.load()
            self._retriever = BM25Retriever(chunks)
            self._chunk_count = current_count
        return self._retriever

    def _current_chunk_count(self) -> int:
        """Fast count of chunks without loading all data."""
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        conn.close()
        return count

    def invalidate(self) -> None:
        """Force rebuild of the index on next query."""
        self._retriever = None
        self._chunk_count = 0

    def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        retriever = self._ensure_index()
        return retriever.search(query, top_k)