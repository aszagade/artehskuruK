"""
Unknown Term Detection & Glossary
==================================

Detects new terms in ingested documents:
- Acronyms and abbreviations
- Product-specific jargon
- Client names and codenames
- Technical terminology

Builds and maintains an organizational glossary over time.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from kurukshetra.registry.database import get_connection


@dataclass(slots=True)
class GlossaryEntry:
    """A glossary term with definition and metadata."""
    term: str
    definition: str
    category: str  # product, system, process, acronym, client, general
    source_document_id: str
    confidence: float
    confirmed: bool  # Human-confirmed
    usage_count: int = 0


@dataclass(slots=True)
class UnknownTerm:
    """A term detected but not yet in the glossary."""
    term: str
    first_seen_doc: str
    first_seen_date: str
    occurrence_count: int
    context_snippet: str  # Where it was found
    suggested_category: str
    status: str = "pending"  # pending, confirmed, rejected


# Known IDeaS terminology to skip during unknown detection
KNOWN_TERMS: set[str] = {
    # Common English
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "her",
    "was", "one", "our", "out", "has", "his", "how", "its", "may", "new",
    "now", "old", "see", "way", "who", "did", "get", "let", "say", "she",
    "too", "use", "this", "that", "with", "from", "have", "been", "will",
    "more", "when", "what", "your", "they", "than", "them", "each", "make",
    "like", "just", "over", "such", "also", "into", "some", "could", "other",
    # IDeaS common
    "G3", "RMS", "IDeaS", "Opera", "PMS", "CRS", "BAR", "SRP", "OXI",
    "NGI", "OHIP", "FOLS", "TARS", "CP", "RSS", "ESA", "CDP", "SFDC",
    "HTNG", "LDB", "LRA", "NCP", "AMS", "BAD", "ROI", "SLA", "SRE",
    "PDF", "CSV", "SQL", "API", "URL", "DNS", "HTTP", "JSON", "XML",
    "SAS", "CRM", "ERP", "SOP", "KPI", "RCA",
    # Common technical
    "server", "database", "table", "query", "job", "step", "process",
    "system", "property", "client", "hotel", "config", "error", "log",
    "file", "data", "code", "test", "user", "role", "team", "group",
}


class GlossaryManager:
    """
    Manages the organizational glossary and detects unknown terms.

    Stores glossary in DuckDB for persistence.
    """

    def __init__(self) -> None:
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Create glossary and unknown terms tables."""
        conn = get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS glossary (
                term TEXT PRIMARY KEY,
                definition TEXT,
                category TEXT,
                source_document_id TEXT,
                confidence DOUBLE,
                confirmed BOOLEAN DEFAULT FALSE,
                usage_count INTEGER DEFAULT 0,
                created_at TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS unknown_terms (
                term TEXT PRIMARY KEY,
                first_seen_doc TEXT,
                first_seen_date TEXT,
                occurrence_count INTEGER DEFAULT 1,
                context_snippet TEXT,
                suggested_category TEXT,
                status TEXT DEFAULT 'pending'
            )
        """)
        conn.close()

    def add_known_term(
        self,
        term: str,
        definition: str,
        category: str = "general",
        source_document_id: str = "",
        confirmed: bool = True,
    ) -> GlossaryEntry:
        """Add a confirmed term to the glossary."""
        conn = get_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO glossary
            (term, definition, category, source_document_id, confidence,
             confirmed, usage_count, created_at)
            VALUES (?, ?, ?, ?, 1.0, ?, 0, CURRENT_TIMESTAMP)
            """,
            (term, definition, category, source_document_id, confirmed),
        )
        conn.close()

        return GlossaryEntry(
            term=term,
            definition=definition,
            category=category,
            source_document_id=source_document_id,
            confidence=1.0,
            confirmed=confirmed,
        )

    def is_known(self, term: str) -> bool:
        """Check if a term is in the glossary."""
        if term.upper() in {t.upper() for t in KNOWN_TERMS}:
            return True

        conn = get_connection()
        row = conn.execute(
            "SELECT term FROM glossary WHERE UPPER(term) = UPPER(?)",
            (term,),
        ).fetchone()
        conn.close()

        return row is not None

    def detect_unknown_terms(
        self,
        text: str,
        document_id: str = "",
    ) -> list[UnknownTerm]:
        """
        Scan text for terms not in the glossary.

        Detects:
        - ALL CAPS sequences (likely acronyms)
        - CamelCase terms
        - Terms with specific patterns (e.g., "Step-Name", "Product_v2")
        """
        unknown = []
        seen = set()

        # Pattern 1: ALL CAPS acronyms (3+ chars)
        for match in re.finditer(r"\b([A-Z][A-Z\-]{2,})\b", text):
            term = match.group(1)
            if term not in seen and not self.is_known(term):
                seen.add(term)
                context = self._extract_context(text, match.start(), match.end())
                unknown.append(UnknownTerm(
                    term=term,
                    first_seen_doc=document_id,
                    first_seen_date="",
                    occurrence_count=text.upper().count(term.upper()),
                    context_snippet=context,
                    suggested_category="acronym",
                ))

        # Pattern 2: Capitalized multi-word terms (potential product/process names)
        for match in re.finditer(
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})\b", text
        ):
            term = match.group(1)
            if (
                term not in seen
                and not self.is_known(term)
                and len(term) > 5
                and term.split()[0] not in {"The", "This", "When", "How",
                                            "What", "Step", "Note", "Table",
                                            "Figure", "Section", "Chapter"}
            ):
                seen.add(term)
                context = self._extract_context(text, match.start(), match.end())
                unknown.append(UnknownTerm(
                    term=term,
                    first_seen_doc=document_id,
                    first_seen_date="",
                    occurrence_count=text.count(term),
                    context_snippet=context,
                    suggested_category="product",
                ))

        # Pattern 3: Terms with underscores or hyphens (technical identifiers)
        for match in re.finditer(r"\b([A-Za-z]+[\-_][A-Za-z0-9]+(?:[\-_][A-Za-z0-9]+)*)\b", text):
            term = match.group(1)
            if (
                term not in seen
                and not self.is_known(term)
                and len(term) > 5
                and not term.startswith("http")
                and not term.endswith(".py")
            ):
                seen.add(term)
                context = self._extract_context(text, match.start(), match.end())
                unknown.append(UnknownTerm(
                    term=term,
                    first_seen_doc=document_id,
                    first_seen_date="",
                    occurrence_count=text.count(term),
                    context_snippet=context,
                    suggested_category="technical",
                ))

        # Store unknown terms in database
        self._store_unknown_terms(unknown)

        return unknown

    def _extract_context(
        self, text: str, start: int, end: int, window: int = 100
    ) -> str:
        """Extract surrounding context for a term."""
        ctx_start = max(0, start - window)
        ctx_end = min(len(text), end + window)
        snippet = text[ctx_start:ctx_end].replace("\n", " ").strip()
        return f"...{snippet}..."

    def _store_unknown_terms(self, terms: list[UnknownTerm]) -> None:
        """Store detected unknown terms in the database."""
        conn = get_connection()
        for term in terms:
            conn.execute(
                """
                INSERT OR IGNORE INTO unknown_terms
                (term, first_seen_doc, first_seen_date, occurrence_count,
                 context_snippet, suggested_category, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    term.term,
                    term.first_seen_doc,
                    term.first_seen_date,
                    term.occurrence_count,
                    term.context_snippet,
                    term.suggested_category,
                ),
            )
            # Update occurrence count if already exists
            conn.execute(
                """
                UPDATE unknown_terms
                SET occurrence_count = occurrence_count + ?
                WHERE term = ? AND status = 'pending'
                """,
                (term.occurrence_count - 1, term.term),
            )
        conn.close()

    def confirm_term(
        self, term: str, definition: str, category: str = "general"
    ) -> GlossaryEntry:
        """Confirm a pending unknown term and add to glossary."""
        # Add to glossary
        entry = self.add_known_term(
            term=term,
            definition=definition,
            category=category,
            confirmed=True,
        )

        # Update status in unknown_terms
        conn = get_connection()
        conn.execute(
            "UPDATE unknown_terms SET status = 'confirmed' WHERE term = ?",
            (term,),
        )
        conn.close()

        return entry

    def reject_term(self, term: str) -> None:
        """Reject a pending unknown term."""
        conn = get_connection()
        conn.execute(
            "UPDATE unknown_terms SET status = 'rejected' WHERE term = ?",
            (term,),
        )
        conn.close()

    def get_pending_terms(self) -> list[UnknownTerm]:
        """Get all pending unknown terms awaiting confirmation."""
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT term, first_seen_doc, first_seen_date, occurrence_count,
                   context_snippet, suggested_category, status
            FROM unknown_terms
            WHERE status = 'pending'
            ORDER BY occurrence_count DESC
            """
        ).fetchall()
        conn.close()

        return [
            UnknownTerm(
                term=r[0],
                first_seen_doc=r[1],
                first_seen_date=r[2],
                occurrence_count=r[3],
                context_snippet=r[4],
                suggested_category=r[5],
                status=r[6],
            )
            for r in rows
        ]

    def get_glossary_stats(self) -> dict:
        """Get glossary statistics."""
        conn = get_connection()
        total = conn.execute("SELECT COUNT(*) FROM glossary").fetchone()[0]
        confirmed = conn.execute(
            "SELECT COUNT(*) FROM glossary WHERE confirmed = TRUE"
        ).fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(*) FROM unknown_terms WHERE status = 'pending'"
        ).fetchone()[0]
        conn.close()

        return {
            "total_terms": total,
            "confirmed_terms": confirmed,
            "pending_unknown": pending,
        }

    def increment_usage(self, term: str) -> None:
        """Increment usage count for a glossary term."""
        conn = get_connection()
        conn.execute(
            "UPDATE glossary SET usage_count = usage_count + 1 WHERE term = ?",
            (term,),
        )
        conn.close()
