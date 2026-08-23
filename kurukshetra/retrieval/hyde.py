"""
HyDE Retrieval (Hypothetical Document Embeddings)
==================================================

Generates a hypothetical answer to the query, then uses that
hypothetical document's embedding to find real similar chunks.

This bridges the gap between short queries and long documents,
dramatically improving recall for complex questions.
"""

from __future__ import annotations

import math
from typing import Optional

from kurukshetra.embeddings import BGEEmbedding
from kurukshetra.registry.chunks import ChunkRepository
from kurukshetra.registry.vectors import VectorRepository

from .models import RetrievalResult


# ---------------------------------------------------------------------------
# Hypothetical answer templates for different query types
# ---------------------------------------------------------------------------

PROCEDURE_TEMPLATE = (
    "The process for {query} involves several steps. "
    "First, you need to check the system configuration and verify the property settings. "
    "Then, follow the standard procedure which includes checking the job status, "
    "verifying the data flow, and confirming the output. "
    "If there are any failures, check the error logs and follow the troubleshooting guide. "
    "The key steps are: verify configuration, check job status, review logs, and apply resolution."
)

TROUBLESHOOTING_TEMPLATE = (
    "To troubleshoot {query}, first identify the error message and failure stage. "
    "Check the relevant logs in the monitoring system. "
    "Verify the configuration parameters and data inputs. "
    "Common resolutions include checking property configuration, "
    "verifying data integrity, and ensuring proper system connectivity. "
    "If the issue persists, escalate to the appropriate team with the correlation ID."
)

GENERAL_TEMPLATE = (
    "Regarding {query}: this is a documented process in the IDeaS G3 RMS system. "
    "The relevant information covers the configuration, setup, and operational procedures. "
    "Key aspects include property management, data flow verification, and monitoring. "
    "For detailed steps, refer to the process documentation and troubleshooting guides."
)


class HyDERetriever:
    """
    Hypothetical Document Embeddings retriever.

    Instead of searching with the raw query, generates a hypothetical
    answer document, embeds it, and finds real chunks most similar
    to that hypothetical answer.
    """

    def __init__(self) -> None:
        self.embedder = BGEEmbedding()
        self.chunk_repo = ChunkRepository()
        self.vector_repo = VectorRepository()

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def _generate_hypothetical(self, query: str) -> str:
        """
        Generate a hypothetical answer document.

        In production this would use an LLM. Here we use template-based
        generation for zero-latency, no-API-cost operation.
        """
        q = query.lower()

        if any(kw in q for kw in ["how to", "process", "steps", "procedure"]):
            return PROCEDURE_TEMPLATE.format(query=query)
        elif any(kw in q for kw in ["error", "failure", "troubleshoot", "issue", "fix"]):
            return TROUBLESHOOTING_TEMPLATE.format(query=query)
        else:
            return GENERAL_TEMPLATE.format(query=query)

    def search(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        """
        Search using HyDE: generate hypothetical answer, then find
        real chunks similar to it.
        """
        # Generate hypothetical answer
        hypothetical = self._generate_hypothetical(query)

        # Embed the hypothetical answer
        hypo_vector = self.embedder.embed(hypothetical)

        # Also embed the original query for hybrid scoring
        query_vector = self.embedder.embed(query)

        # Load all chunks and vectors
        chunks = {c.chunk_id: c for c in self.chunk_repo.load()}
        vectors = self.vector_repo.load()

        results: list[RetrievalResult] = []

        for chunk_id, vec in vectors:
            # Score: 60% similarity to hypothetical, 40% to original query
            hypo_sim = self._cosine(hypo_vector, vec)
            query_sim = self._cosine(query_vector, vec)
            score = hypo_sim * 0.6 + query_sim * 0.4

            chunk = chunks.get(chunk_id)
            if chunk:
                results.append(
                    RetrievalResult(
                        chunk_id=chunk.chunk_id,
                        document_id=chunk.document_id,
                        score=score,
                        text=chunk.text,
                        metadata={
                            "strategy": "hyde",
                            "hypo_score": hypo_sim,
                            "query_score": query_sim,
                        },
                    )
                )

        return sorted(results, key=lambda x: x.score, reverse=True)[:top_k]
