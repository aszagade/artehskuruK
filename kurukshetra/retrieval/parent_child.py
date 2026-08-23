"""
Parent-Child Retrieval
======================

Small chunks are precise but lack context.
Parent chunks provide context but are imprecise.

Strategy: retrieve at child level for precision, return parent context for completeness.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from kurukshetra.embeddings import BGEEmbedding
from kurukshetra.registry.chunks import ChunkRepository
from kurukshetra.registry.vectors import VectorRepository

from .models import RetrievalResult


@dataclass(slots=True)
class ParentChildPair:
    """A parent chunk with its child chunks."""
    parent_id: str
    parent_text: str
    parent_document_id: str
    children: list[tuple[str, str]]  # [(child_id, child_text), ...]


class ParentChildRetriever:
    """
    Retrieves using parent-child chunk relationships.

    - Parent = section-level chunk (bigger, more context)
    - Child = sentence-level chunk (smaller, more precise)
    - Retrieves at child level, returns parent for full context
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

    def _build_parent_child_index(
        self, chunks: list
    ) -> dict[str, ParentChildPair]:
        """
        Build parent-child relationships from chunks.

        Heuristic: chunks from the same document with sequential
        chunk indices are grouped into parents every N children.
        """
        # Group chunks by document
        doc_chunks: dict[str, list] = defaultdict(list)
        for chunk in chunks:
            doc_chunks[chunk.document_id].append(chunk)

        # Sort within each document
        for doc_id in doc_chunks:
            doc_chunks[doc_id].sort(key=lambda c: c.sequence)

        parent_index: dict[str, ParentChildPair] = {}
        children_per_parent = 5  # 5 children per parent section

        for doc_id, doc_chunk_list in doc_chunks.items():
            for i in range(0, len(doc_chunk_list), children_per_parent):
                parent_group = doc_chunk_list[i:i + children_per_parent]
                if not parent_group:
                    continue

                # Parent is the combined text of all children in the group
                parent_id = parent_group[0].chunk_id.replace("-SC-", "-PARENT-").replace("-CH-", "-PARENT-")
                parent_text = "\n\n".join(c.text for c in parent_group)
                children = [(c.chunk_id, c.text) for c in parent_group]

                pair = ParentChildPair(
                    parent_id=parent_id,
                    parent_text=parent_text,
                    parent_document_id=doc_id,
                    children=children,
                )

                # Index all children pointing to their parent
                for child_id, _ in children:
                    parent_index[child_id] = pair

                # Also index parent itself
                parent_index[parent_id] = pair

        return parent_index

    def search(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        """
        Search using parent-child retrieval.

        1. Embed query
        2. Find best matching children (precision)
        3. Return parent chunks (context)
        """
        # Load data
        all_chunks = self.chunk_repo.load()
        parent_index = self._build_parent_child_index(all_chunks)

        # Embed query
        query_vec = self.embedder.embed(query)

        # Load vector index
        vectors = self.vector_repo.load()
        chunk_map = {c.chunk_id: c for c in all_chunks}

        # Score all chunks
        scored_children: list[tuple[str, float]] = []

        for chunk_id, vec in vectors:
            score = self._cosine(query_vec, vec)
            scored_children.append((chunk_id, score))

        # Sort by score
        scored_children.sort(key=lambda x: x[1], reverse=True)

        # Collect unique parents from top children
        seen_parents: dict[str, float] = {}  # parent_id -> best child score
        results: list[RetrievalResult] = []

        for chunk_id, child_score in scored_children:
            pair = parent_index.get(chunk_id)
            if pair is None:
                continue

            parent_id = pair.parent_id
            if parent_id not in seen_parents:
                seen_parents[parent_id] = child_score

                # Create result with parent context
                # Boost score slightly for having child-level precision
                results.append(
                    RetrievalResult(
                        chunk_id=parent_id,
                        document_id=pair.parent_document_id,
                        score=child_score * 1.1,  # Small boost for parent context
                        text=pair.parent_text,
                        metadata={
                            "strategy": "parent_child",
                            "child_score": child_score,
                            "num_children": len(pair.children),
                        },
                    )
                )

                if len(results) >= top_k:
                    break

        return results[:top_k]
