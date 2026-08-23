"""
Multi-Query Retrieval
=====================

Generates multiple query variations from different perspectives:
- Procedural ("How to...")
- Troubleshooting ("What causes... to fail")
- Conceptual ("What is...")
- Comparative ("What's the difference between...")

Retrieves for each variation, merges, and deduplicates.
Catches knowledge that a single query formulation would miss.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict

from kurukshetra.embeddings import BGEEmbedding
from kurukshetra.registry.chunks import ChunkRepository
from kurukshetra.registry.vectors import VectorRepository

from .models import RetrievalResult


# ---------------------------------------------------------------------------
# Query expansion patterns
# ---------------------------------------------------------------------------

EXPANSION_TEMPLATES = [
    # Procedural perspective
    ("how to {core}", "procedure", 0.25),
    ("steps for {core}", "procedure", 0.20),
    ("process to {core}", "procedure", 0.20),

    # Troubleshooting perspective
    ("troubleshooting {core}", "troubleshooting", 0.20),
    ("resolving issues with {core}", "troubleshooting", 0.15),
    ("common errors in {core}", "troubleshooting", 0.15),

    # Configuration perspective
    ("configuration for {core}", "configuration", 0.15),
    ("setup {core}", "configuration", 0.15),
    ("settings for {core}", "configuration", 0.10),

    # Documentation perspective
    ("documentation about {core}", "reference", 0.10),
    ("guide for {core}", "reference", 0.10),
]


def _extract_core_query(query: str) -> str:
    """Extract the core topic from a query by removing common prefixes."""
    prefixes = [
        r"^how\s+(?:do\s+I\s+|to\s+)?",
        r"^what\s+(?:is|are|does)\s+(?:the\s+)?",
        r"^can\s+(?:you\s+)?",
        r"^please\s+",
        r"^help\s+me\s+",
        r"^I\s+need\s+(?:to\s+)?",
        r"^tell\s+me\s+(?:about\s+)?",
    ]

    core = query
    for prefix in prefixes:
        core = re.sub(prefix, "", core, flags=re.IGNORECASE).strip()

    # Remove trailing question marks
    core = core.rstrip("?").strip()

    return core if core else query


class MultiQueryRetriever:
    """
    Retrieves using multiple query formulations, then merges results.
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

    def _generate_variations(self, query: str) -> list[tuple[str, str, float]]:
        """
        Generate query variations with their perspective type and weight.
        """
        core = _extract_core_query(query)
        variations = [(query, "original", 1.0)]

        for template, perspective, weight in EXPANSION_TEMPLATES:
            variation = template.format(core=core)
            variations.append((variation, perspective, weight))

        return variations

    def search(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        """
        Search using multiple query variations and merge results.
        """
        # Generate variations
        variations = self._generate_variations(query)

        # Embed all variations
        query_vectors = []
        for var_text, perspective, weight in variations:
            vec = self.embedder.embed(var_text)
            query_vectors.append((var_text, perspective, weight, vec))

        # Load chunks and vectors
        chunks = {c.chunk_id: c for c in self.chunk_repo.load()}
        vectors = self.vector_repo.load()

        # Score each chunk against all query variations
        chunk_scores: dict[str, dict] = defaultdict(lambda: {
            "total_score": 0.0,
            "hit_count": 0,
            "best_variant": "",
            "best_score": 0.0,
        })

        for chunk_id, vec in vectors:
            for var_text, perspective, weight, qvec in query_vectors:
                sim = self._cosine(qvec, vec)
                weighted = sim * weight

                if weighted > chunk_scores[chunk_id]["best_score"]:
                    chunk_scores[chunk_id]["best_score"] = weighted
                    chunk_scores[chunk_id]["best_variant"] = perspective

                chunk_scores[chunk_id]["total_score"] += weighted
                chunk_scores[chunk_id]["hit_count"] += 1

        # Build results
        results: list[RetrievalResult] = []

        for chunk_id, data in chunk_scores.items():
            chunk = chunks.get(chunk_id)
            if chunk:
                # Normalize: total_score / number of variations, boosted by hit count
                hit_boost = min(data["hit_count"] / len(variations), 1.0)
                final_score = data["total_score"] / len(variations) * (0.7 + 0.3 * hit_boost)

                results.append(
                    RetrievalResult(
                        chunk_id=chunk.chunk_id,
                        document_id=chunk.document_id,
                        score=final_score,
                        text=chunk.text,
                        metadata={
                            "strategy": "multi_query",
                            "hit_count": data["hit_count"],
                            "total_variations": len(variations),
                            "best_variant": data["best_variant"],
                        },
                    )
                )

        return sorted(results, key=lambda x: x.score, reverse=True)[:top_k]
