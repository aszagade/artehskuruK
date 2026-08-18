from __future__ import annotations

from kurukshetra.chunking.models import Chunk
from kurukshetra.retrieval import BM25Retriever


class KnowledgeIndexer:
    """Indexes chunks for lexical retrieval."""

    def __init__(self) -> None:
        self.chunks: list[Chunk] = []

    def add(self, chunks: list[Chunk]) -> None:
        self.chunks.extend(chunks)

    def build(self) -> BM25Retriever:
        return BM25Retriever(self.chunks)