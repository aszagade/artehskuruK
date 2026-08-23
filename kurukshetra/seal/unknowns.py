"""
SEAL Unknowns
=============

Loads pending unknown terms and enriches them with evidence:
- Document references where the term appears
- Graph entity relationships
- Occurrence counts and context snippets
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from kurukshetra.registry.database import get_connection


@dataclass
class UnknownTermWithEvidence:
    """An unknown term enriched with evidence for the interview."""
    term: str
    status: str
    occurrence_count: int
    context_snippet: str
    suggested_category: str
    first_seen_doc: str
    # Evidence
    documents: list[dict] = field(default_factory=list)  # [{id, title, path}]
    graph_entities: list[dict] = field(default_factory=list)  # [{id, name, type}]
    glossary_similar: list[dict] = field(default_factory=list)  # [{term, definition}]


class UnknownLoader:
    """Loads and enriches unknown terms for the SEAL interview."""

    def __init__(self) -> None:
        pass

    def load_pending(self) -> list[UnknownTermWithEvidence]:
        """Load all pending unknown terms with evidence."""
        conn = get_connection()
        rows = conn.execute(
            "SELECT term, status, occurrence_count, context_snippet, "
            "suggested_category, first_seen_doc "
            "FROM unknown_terms WHERE status = 'pending' "
            "ORDER BY occurrence_count DESC"
        ).fetchall()
        conn.close()

        terms = []
        for row in rows:
            term = UnknownTermWithEvidence(
                term=row[0],
                status=row[1],
                occurrence_count=row[2],
                context_snippet=row[3],
                suggested_category=row[4],
                first_seen_doc=row[5],
            )
            # Enrich with evidence
            term.documents = self._find_documents(term.term)
            term.graph_entities = self._find_graph_entities(term.term)
            term.glossary_similar = self._find_similar_glossary(term.term)
            terms.append(term)

        return terms

    def load_one(self, term: str) -> Optional[UnknownTermWithEvidence]:
        """Load a specific unknown term with evidence."""
        conn = get_connection()
        row = conn.execute(
            "SELECT term, status, occurrence_count, context_snippet, "
            "suggested_category, first_seen_doc "
            "FROM unknown_terms WHERE term = ?",
            (term,),
        ).fetchone()
        conn.close()

        if row is None:
            return None

        result = UnknownTermWithEvidence(
            term=row[0],
            status=row[1],
            occurrence_count=row[2],
            context_snippet=row[3],
            suggested_category=row[4],
            first_seen_doc=row[5],
        )
        result.documents = self._find_documents(result.term)
        result.graph_entities = self._find_graph_entities(result.term)
        result.glossary_similar = self._find_similar_glossary(result.term)
        return result

    def count_pending(self) -> int:
        """Count pending unknown terms."""
        conn = get_connection()
        n = conn.execute(
            "SELECT COUNT(*) FROM unknown_terms WHERE status = 'pending'"
        ).fetchone()[0]
        conn.close()
        return n

    def _find_documents(self, term: str) -> list[dict]:
        """Find documents containing this term."""
        conn = get_connection()
        # Search chunks for the term
        rows = conn.execute(
            "SELECT DISTINCT c.document_id, d.title "
            "FROM chunks c JOIN documents d ON c.document_id = d.document_id "
            "WHERE c.text LIKE ? LIMIT 5",
            (f"%{term}%",),
        ).fetchall()
        conn.close()
        return [{"id": r[0], "title": r[1]} for r in rows]

    def _find_graph_entities(self, term: str) -> list[dict]:
        """Find graph entities matching this term."""
        try:
            conn = get_connection()
            rows = conn.execute(
                "SELECT id, name, entity_type FROM graph_entities "
                "WHERE name LIKE ? OR id LIKE ? LIMIT 5",
                (f"%{term}%", f"%{term.upper().replace(' ', '-')}%"),
            ).fetchall()
            conn.close()
            return [{"id": r[0], "name": r[1], "type": r[2]} for r in rows]
        except Exception:
            return []

    def _find_similar_glossary(self, term: str) -> list[dict]:
        """Find similar terms already in the glossary."""
        conn = get_connection()
        rows = conn.execute(
            "SELECT term, definition, category FROM glossary "
            "WHERE term LIKE ? OR ? LIKE '%' || term || '%' LIMIT 3",
            (f"%{term[:len(term)//2]}%", term),
        ).fetchall()
        conn.close()
        return [{"term": r[0], "definition": r[1], "category": r[2]} for r in rows]
