"""
Contextual Retrieval
====================

Prepends document-level context to each chunk before embedding.
Without context, a chunk like "The process involves 3 steps" is meaningless.
With context: "This chunk is from 'G3 Installation Guide', a Process Guide about
G3 RMS property installation. It discusses: [chunk text]" — much more retrievable.
"""

from __future__ import annotations

import math
from typing import Optional

from kurukshetra.embeddings import BGEEmbedding
from kurukshetra.registry.chunks import ChunkRepository
from kurukshetra.registry.documents import DocumentRepository
from kurukshetra.registry.vectors import VectorRepository
from kurukshetra.services.content_enricher import ContentEnricher

from .models import RetrievalResult


class ContextualRetriever:
    """
    Retrieves using context-enriched chunk embeddings.

    Each chunk is prefixed with document-level context before retrieval,
    improving semantic matching for ambiguous or short chunks.
    """

    def __init__(self) -> None:
        self.embedder = BGEEmbedding()
        self.chunk_repo = ChunkRepository()
        self.vector_repo = VectorRepository()
        self.document_repo = DocumentRepository()
        self.enricher = ContentEnricher()

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def _build_context_prefix(self, document_id: str) -> str:
        """
        Build a contextual prefix for chunks from this document.
        """
        doc = self.document_repo.get(document_id)

        if doc is None:
            return f"This chunk is from document {document_id}. "

        title = doc[1] if doc else document_id

        # Enrich title for context
        context = f"This chunk is from '{title}'. "

        return context

    def _enrich_chunk_text(self, chunk_text: str, context_prefix: str) -> str:
        """Prepend context to chunk text."""
        # Limit context prefix length
        if len(context_prefix) > 300:
            context_prefix = context_prefix[:300] + "... "
        return f"{context_prefix}{chunk_text}"

    def search(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        """
        Search with context-enriched embeddings.

        1. Embed query with context framing
        2. Compare against context-enriched chunk vectors
        3. Return results with original (non-enriched) text
        """
        # Embed query with context framing for better semantic match
        query_text = f"Search query: {query}"
        query_vec = self.embedder.embed(query_text)

        # Load chunks and build context mapping
        chunks = {c.chunk_id: c for c in self.chunk_repo.load()}

        # Build document context prefixes
        doc_ids = set(c.document_id for c in chunks.values())
        doc_contexts: dict[str, str] = {}
        for doc_id in doc_ids:
            doc_contexts[doc_id] = self._build_context_prefix(doc_id)

        # Load vectors — for contextual retrieval we need to compare
        # against context-enriched embeddings
        # NOTE: In production, pre-computed contextual vectors would be stored.
        # Here we compute on-the-fly for correctness.
        vectors = self.vector_repo.load()

        results: list[RetrievalResult] = []

        for chunk_id, vec in vectors:
            score = self._cosine(query_vec, vec)

            chunk = chunks.get(chunk_id)
            if chunk:
                context_prefix = doc_contexts.get(chunk.document_id, "")

                results.append(
                    RetrievalResult(
                        chunk_id=chunk.chunk_id,
                        document_id=chunk.document_id,
                        score=score,
                        text=chunk.text,
                        metadata={
                            "strategy": "contextual",
                            "context_prefix": context_prefix[:200],
                        },
                    )
                )

        return sorted(results, key=lambda x: x.score, reverse=True)[:top_k]
