"""
Retrieval-Time Access Control
=============================

Filters retrieval results by document visibility level.

Visibility hierarchy (least to most restrictive):
  PUBLIC < INTERNAL < CONFIDENTIAL < RESTRICTED

A user cleared for INTERNAL can see PUBLIC and INTERNAL documents,
but NOT CONFIDENTIAL or RESTRICTED.

Usage:
    from kurukshetra.retrieval.access_control import VisibilityFilter, VisibilityLevel

    # Allow INTERNAL and below
    vf = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)

    # Filter results from any retriever
    filtered = vf.filter(results)

    # Or wrap a retriever
    safe_retriever = vf.wrap(my_retriever)
"""

from __future__ import annotations

from enum import IntEnum
from typing import Protocol

from kurukshetra.registry.database import get_connection

from .models import RetrievalResult


class VisibilityLevel(IntEnum):
    """Document visibility levels, ordered by restrictiveness."""

    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    RESTRICTED = 3

    @classmethod
    def from_string(cls, value: str | None) -> VisibilityLevel:
        """Parse a visibility string, defaulting to INTERNAL."""
        if value is None:
            return cls.INTERNAL
        mapping = {
            "public": cls.PUBLIC,
            "internal": cls.INTERNAL,
            "confidential": cls.CONFIDENTIAL,
            "restricted": cls.RESTRICTED,
        }
        return mapping.get(value.strip().lower(), cls.INTERNAL)


class RetrieverLike(Protocol):
    """Any object with a search(query, top_k) method."""

    def search(self, query: str, top_k: int = 5) -> list[RetrievalResult]: ...


class VisibilityFilter:
    """
    Filters retrieval results by document visibility.

    Maintains a cache of document_id -> VisibilityLevel to avoid
    repeated database lookups.
    """

    def __init__(self, max_level: VisibilityLevel = VisibilityLevel.INTERNAL) -> None:
        self.max_level = max_level
        self._doc_visibility: dict[str, VisibilityLevel] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Load document visibility map from DuckDB."""
        if self._loaded:
            return
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT document_id, visibility FROM documents"
            ).fetchall()
            for doc_id, vis in rows:
                self._doc_visibility[doc_id] = VisibilityLevel.from_string(vis)
        except Exception:
            # If documents table doesn't exist, treat all as INTERNAL
            pass
        finally:
            conn.close()
        self._loaded = True

    def invalidate(self) -> None:
        """Force reload of visibility cache on next filter call."""
        self._loaded = False
        self._doc_visibility.clear()

    def is_allowed(self, document_id: str) -> bool:
        """Check if a document is accessible at the current clearance level."""
        self._ensure_loaded()
        doc_level = self._doc_visibility.get(document_id, VisibilityLevel.INTERNAL)
        return doc_level <= self.max_level

    def filter(self, results: list[RetrievalResult]) -> list[RetrievalResult]:
        """Filter results, keeping only those the caller is authorized to see."""
        self._ensure_loaded()
        filtered = []
        for r in results:
            doc_level = self._doc_visibility.get(
                r.document_id, VisibilityLevel.INTERNAL
            )
            if doc_level <= self.max_level:
                filtered.append(r)
        return filtered

    def wrap(self, retriever: RetrieverLike) -> FilteredRetriever:
        """Wrap a retriever with visibility filtering."""
        return FilteredRetriever(retriever, self)


class FilteredRetriever:
    """Wrapper that applies visibility filtering to any retriever."""

    def __init__(self, retriever: RetrieverLike, vis_filter: VisibilityFilter) -> None:
        self.retriever = retriever
        self.vis_filter = vis_filter

    def search(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        """Search and filter results by visibility."""
        # Over-fetch to compensate for filtered-out results
        raw = self.retriever.search(query, top_k=top_k * 3)
        filtered = self.vis_filter.filter(raw)
        return filtered[:top_k]
