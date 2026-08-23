"""
Graph-Augmented Retrieval
=========================

Combines vector similarity search with knowledge graph traversal.

Vector search finds semantically similar text.
Graph traversal finds structurally related concepts.

Together they provide richer, more connected results.
"""

from __future__ import annotations

import math
from typing import Optional

from kurukshetra.embeddings import BGEEmbedding
from kurukshetra.graph.builder import GraphBuilder
from kurukshetra.graph.repository import GraphRepository
from kurukshetra.registry.chunks import ChunkRepository
from kurukshetra.registry.vectors import VectorRepository

from .models import RetrievalResult


class GraphAugmentedRetriever:
    """
    Retrieval that combines vector search with graph traversal.

    1. Vector search finds relevant chunks
    2. Graph traversal finds related entities/concepts
    3. Graph context enriches vector results
    """

    def __init__(self) -> None:
        self.embedder = BGEEmbedding()
        self.chunk_repo = ChunkRepository()
        self.vector_repo = VectorRepository()
        self.graph_repo = GraphRepository()
        self.graph_builder = GraphBuilder(self.graph_repo)

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def _search_graph(self, query: str) -> list[dict]:
        """
        Search the knowledge graph for relevant entities.
        Uses query keywords to find matching entities.
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())

        # Search all entities
        entities = self.graph_repo.search_entities()

        relevant = []
        for entity in entities:
            # Score entity relevance to query
            name_lower = entity.name.lower()
            desc_lower = (entity.description or "").lower()

            # Simple word overlap scoring
            name_words = set(name_lower.split())
            desc_words = set(desc_lower.split())

            name_overlap = len(query_words & name_words) / max(len(query_words), 1)
            desc_overlap = len(query_words & desc_words) / max(len(query_words), 1)

            score = name_overlap * 0.7 + desc_overlap * 0.3

            if score > 0.1:
                relevant.append({
                    "entity": entity,
                    "score": score,
                })

        return sorted(relevant, key=lambda x: x["score"], reverse=True)[:10]

    def _expand_with_graph_context(
        self, results: list[RetrievalResult]
    ) -> list[RetrievalResult]:
        """
        Enrich vector results with graph context.

        For each result's document, find related entities in the graph
        and add their information as metadata.
        """
        for result in results:
            # Find entities related to this document
            neighbors = self.graph_repo.get_neighbors(result.document_id)

            if neighbors:
                related_names = []
                for rel in neighbors[:5]:
                    other_id = (
                        rel.target_id
                        if rel.source_id == result.document_id
                        else rel.source_id
                    )
                    entity = self.graph_repo.get_entity(other_id)
                    if entity:
                        related_names.append(entity.name)

                result.metadata["graph_context"] = {
                    "related_entities": related_names,
                    "relationship_count": len(neighbors),
                }

                # Boost score based on graph connectivity
                graph_boost = min(len(neighbors) * 0.02, 0.15)
                result.score *= (1.0 + graph_boost)

        return results

    def search(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        """
        Search using graph-augmented retrieval.

        1. Vector search for semantic similarity
        2. Graph search for entity matching
        3. Merge and enrich results
        """
        # Vector search
        query_vec = self.embedder.embed(query)
        chunks = {c.chunk_id: c for c in self.chunk_repo.load()}
        vectors = self.vector_repo.load()

        vector_results: list[RetrievalResult] = []
        for chunk_id, vec in vectors:
            score = self._cosine(query_vec, vec)
            chunk = chunks.get(chunk_id)
            if chunk:
                vector_results.append(
                    RetrievalResult(
                        chunk_id=chunk.chunk_id,
                        document_id=chunk.document_id,
                        score=score,
                        text=chunk.text,
                        metadata={"strategy": "vector"},
                    )
                )

        vector_results.sort(key=lambda x: x.score, reverse=True)
        vector_results = vector_results[:top_k * 2]  # Get more for merging

        # Graph search
        graph_results = self._search_graph(query)

        # Enrich vector results with graph context
        enriched = self._expand_with_graph_context(vector_results)

        # Add graph-specific results as supplementary
        for gr in graph_results[:3]:
            entity = gr["entity"]
            # Find chunks that mention this entity
            for result in enriched:
                if entity.name.lower() in result.text.lower():
                    result.score *= 1.1  # Boost for graph entity match
                    result.metadata["graph_entity_match"] = entity.name

        return sorted(enriched, key=lambda x: x.score, reverse=True)[:top_k]
