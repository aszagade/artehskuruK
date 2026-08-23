"""
SEAL Decisions
==============

Stores human-verified answers as organizational decisions.

Design principles:
- Never overwrite original documents
- All learning is human-verified
- Decisions carry provenance (who decided, when, why)
- Decisions can be superseded but never deleted
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Optional

from kurukshetra.registry.database import get_connection


@dataclass
class Decision:
    """A human-verified decision stored by SEAL."""
    decision_id: str
    term: str
    definition: str
    category: str           # glossary, process, correction, clarification
    source_term: str        # the unknown term that triggered this decision
    source_documents: list[str]  # documents referenced
    decided_by: str         # human identifier
    decided_at: str
    confidence: float       # 1.0 for human-verified
    status: str             # active, superseded


class DecisionStore:
    """Persists SEAL decisions in DuckDB."""

    def __init__(self) -> None:
        self._ensure_table()

    def _ensure_table(self) -> None:
        conn = get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS seal_decisions (
                decision_id TEXT PRIMARY KEY,
                term TEXT,
                definition TEXT,
                category TEXT,
                source_term TEXT,
                source_documents TEXT,
                decided_by TEXT,
                decided_at TIMESTAMP,
                confidence DOUBLE,
                status TEXT DEFAULT 'active'
            )
        """)
        conn.close()

    def record(
        self,
        term: str,
        definition: str,
        category: str = "glossary",
        source_term: str = "",
        source_documents: Optional[list[str]] = None,
        decided_by: str = "developer",
    ) -> Decision:
        """Record a human-verified decision."""
        decision_id = f"DEC-{int(time.time() * 1000)}"
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        decision = Decision(
            decision_id=decision_id,
            term=term,
            definition=definition,
            category=category,
            source_term=source_term or term,
            source_documents=source_documents or [],
            decided_by=decided_by,
            decided_at=now,
            confidence=1.0,
            status="active",
        )

        conn = get_connection()
        conn.execute(
            """INSERT INTO seal_decisions
            (decision_id, term, definition, category, source_term,
             source_documents, decided_by, decided_at, confidence, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                decision.decision_id,
                decision.term,
                decision.definition,
                decision.category,
                decision.source_term,
                json.dumps(decision.source_documents),
                decision.decided_by,
                decision.decided_at,
                decision.confidence,
                decision.status,
            ],
        )
        conn.close()
        return decision

    def get_pending(self) -> list[dict]:
        """Get decisions awaiting review (if any review workflow exists)."""
        conn = get_connection()
        rows = conn.execute(
            "SELECT decision_id, term, definition, category, decided_by, decided_at "
            "FROM seal_decisions WHERE status = 'active' ORDER BY decided_at DESC"
        ).fetchall()
        conn.close()
        return [
            {"decision_id": r[0], "term": r[1], "definition": r[2],
             "category": r[3], "decided_by": r[4], "decided_at": r[5]}
            for r in rows
        ]

    def get_by_term(self, term: str) -> Optional[dict]:
        """Get the active decision for a term."""
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM seal_decisions WHERE term = ? AND status = 'active' "
            "ORDER BY decided_at DESC LIMIT 1",
            (term,),
        ).fetchone()
        conn.close()
        if row is None:
            return None
        return {
            "decision_id": row[0], "term": row[1], "definition": row[2],
            "category": row[3], "source_term": row[4],
            "source_documents": json.loads(row[5]) if row[5] else [],
            "decided_by": row[6], "decided_at": row[7],
            "confidence": row[8], "status": row[9],
        }

    def count(self) -> int:
        """Total active decisions."""
        conn = get_connection()
        n = conn.execute(
            "SELECT COUNT(*) FROM seal_decisions WHERE status = 'active'"
        ).fetchone()[0]
        conn.close()
        return n
