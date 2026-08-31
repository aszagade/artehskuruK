"""
Evaluation Signal Tracker
=========================

Tracks query/document quality patterns for measurable SANJAYA learning.

Unlike FeedbackLoop (which stores individual feedback records),
this tracker aggregates patterns that can drive real improvements:

- Which queries are frequently asked (query popularity)
- Which documents are consistently helpful (document usefulness)
- Which retrieval patterns fail (failure taxonomy)
- Which queries get negative feedback (problematic queries)
- Feedback accumulation over time (trend detection)

Safety:
- Never modifies production behavior directly
- Read-only statistics for evaluation and future optimization
- User-scoped: feedback from user A does not affect user B's experience
- All data has full provenance and timestamps
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Optional

from kurukshetra.registry.database import get_connection


@dataclass(slots=True)
class QueryPattern:
    """A pattern of query usage and feedback."""
    query_normalized: str
    ask_count: int
    feedback_count: int
    positive_count: int
    negative_count: int
    avg_confidence: float
    first_seen: str
    last_seen: str


@dataclass(slots=True)
class DocumentUsefulness:
    """Document usefulness signal from accumulated feedback."""
    document_id: str
    total_feedback: int
    positive_count: int
    negative_count: int
    approval_rate: float
    authority_score: float  # from FeedbackLoop.get_document_authority


class EvaluationSignalTracker:
    """
    Tracks evaluation signals for measurable SANJAYA learning.

    Creates a query_signals table that aggregates feedback patterns
    by normalized query, and document_signals table that tracks
    per-document usefulness.
    """

    def __init__(self) -> None:
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Create evaluation signal tables if they don't exist."""
        conn = get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS query_signals (
                query_normalized TEXT PRIMARY KEY,
                query_original TEXT,
                ask_count INTEGER DEFAULT 0,
                feedback_count INTEGER DEFAULT 0,
                positive_count INTEGER DEFAULT 0,
                negative_count INTEGER DEFAULT 0,
                total_confidence DOUBLE DEFAULT 0.0,
                first_seen TIMESTAMP,
                last_seen TIMESTAMP,
                user_ids TEXT DEFAULT '[]'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS document_signals (
                document_id TEXT PRIMARY KEY,
                total_feedback INTEGER DEFAULT 0,
                positive_count INTEGER DEFAULT 0,
                negative_count INTEGER DEFAULT 0,
                last_feedback TIMESTAMP,
                user_ids TEXT DEFAULT '[]'
            )
        """)
        # Try to create; if it already exists, ensure it has the right schema
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS retrieval_failures (
                    query TEXT,
                    failure_type TEXT,
                    failure_detail TEXT,
                    strategy_used TEXT,
                    evidence_count INTEGER,
                    user_id TEXT,
                    timestamp TIMESTAMP
                )
            """)
        except Exception:
            pass  # Table already exists with different schema
        conn.close()

    def _normalize_query(self, query: str) -> str:
        """Normalize a query for pattern matching."""
        import re
        q = query.lower().strip()
        q = re.sub(r'[^\w\s]', '', q)
        q = re.sub(r'\s+', ' ', q)
        return q

    def record_query(
        self,
        query: str,
        confidence: float = 0.0,
        user_id: str = "system",
    ) -> None:
        """Record that a query was asked."""
        normalized = self._normalize_query(query)
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        conn = get_connection()
        try:
            existing = conn.execute(
                "SELECT ask_count, user_ids FROM query_signals WHERE query_normalized = ?",
                (normalized,),
            ).fetchone()

            if existing:
                new_count = existing[0] + 1
                user_ids = json.loads(existing[1] or "[]")
                if user_id not in user_ids:
                    user_ids.append(user_id)
                conn.execute(
                    """UPDATE query_signals
                    SET ask_count = ask_count + 1,
                        total_confidence = total_confidence + ?,
                        last_seen = ?,
                        user_ids = ?
                    WHERE query_normalized = ?""",
                    (confidence, now, json.dumps(user_ids), normalized),
                )
            else:
                conn.execute(
                    """INSERT INTO query_signals
                    (query_normalized, query_original, ask_count,
                     total_confidence, first_seen, last_seen, user_ids)
                    VALUES (?, ?, 1, ?, ?, ?, ?)""",
                    (normalized, query, confidence, now, now, json.dumps([user_id])),
                )
            conn.close()
        except Exception:
            conn.close()

    def record_feedback_signal(
        self,
        query: str,
        document_id: str,
        is_correct: bool,
        confidence: float = 0.0,
        user_id: str = "system",
    ) -> None:
        """Record a feedback signal for evaluation tracking."""
        normalized = self._normalize_query(query)
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        conn = get_connection()
        try:
            # Update query signals
            existing = conn.execute(
                "SELECT feedback_count, positive_count, negative_count, user_ids "
                "FROM query_signals WHERE query_normalized = ?",
                (normalized,),
            ).fetchone()

            if existing:
                user_ids = json.loads(existing[3] or "[]")
                if user_id not in user_ids:
                    user_ids.append(user_id)
                conn.execute(
                    """UPDATE query_signals
                    SET feedback_count = feedback_count + 1,
                        positive_count = positive_count + ?,
                        negative_count = negative_count + ?,
                        last_seen = ?,
                        user_ids = ?
                    WHERE query_normalized = ?""",
                    (
                        1 if is_correct else 0,
                        0 if is_correct else 1,
                        now,
                        json.dumps(user_ids),
                        normalized,
                    ),
                )

            # Update document signals
            doc_existing = conn.execute(
                "SELECT total_feedback, positive_count, negative_count, user_ids "
                "FROM document_signals WHERE document_id = ?",
                (document_id,),
            ).fetchone()

            if doc_existing:
                user_ids = json.loads(doc_existing[3] or "[]")
                if user_id not in user_ids:
                    user_ids.append(user_id)
                conn.execute(
                    """UPDATE document_signals
                    SET total_feedback = total_feedback + 1,
                        positive_count = positive_count + ?,
                        negative_count = negative_count + ?,
                        last_feedback = ?,
                        user_ids = ?
                    WHERE document_id = ?""",
                    (
                        1 if is_correct else 0,
                        0 if is_correct else 1,
                        now,
                        json.dumps(user_ids),
                        document_id,
                    ),
                )
            else:
                conn.execute(
                    """INSERT INTO document_signals
                    (document_id, total_feedback, positive_count, negative_count,
                     last_feedback, user_ids)
                    VALUES (?, 1, ?, ?, ?, ?)""",
                    (
                        document_id,
                        1 if is_correct else 0,
                        0 if is_correct else 1,
                        now,
                        json.dumps([user_id]),
                    ),
                )

            conn.close()
        except Exception:
            conn.close()

    def record_retrieval_failure(
        self,
        query: str,
        failure_type: str,
        failure_detail: str = "",
        strategy_used: str = "",
        evidence_count: int = 0,
        user_id: str = "system",
    ) -> None:
        """Record a retrieval failure for failure pattern analysis."""
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        conn = get_connection()
        try:
            conn.execute(
                """INSERT INTO retrieval_failures
                (query, failure_type, failure_detail, strategy_used,
                 evidence_count, user_id, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (query, failure_type, failure_detail, strategy_used,
                 evidence_count, user_id, now),
            )
            conn.close()
        except Exception:
            conn.close()

    def get_popular_queries(self, limit: int = 20) -> list[QueryPattern]:
        """Get the most frequently asked queries with their feedback patterns."""
        conn = get_connection()
        rows = conn.execute(
            """SELECT query_normalized, query_original, ask_count,
                      feedback_count, positive_count, negative_count,
                      total_confidence, first_seen, last_seen
            FROM query_signals
            ORDER BY ask_count DESC
            LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()

        return [
            QueryPattern(
                query_normalized=r[0],
                ask_count=r[2],
                feedback_count=r[3],
                positive_count=r[4],
                negative_count=r[5],
                avg_confidence=round(r[6] / max(r[2], 1), 3),
                first_seen=r[7] or "",
                last_seen=r[8] or "",
            )
            for r in rows
        ]

    def get_useful_documents(self, limit: int = 20) -> list[DocumentUsefulness]:
        """Get documents ranked by feedback usefulness."""
        from kurukshetra.services.feedback import FeedbackLoop

        conn = get_connection()
        rows = conn.execute(
            """SELECT document_id, total_feedback, positive_count, negative_count
            FROM document_signals
            WHERE total_feedback >= 2
            ORDER BY positive_count DESC
            LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()

        fb = FeedbackLoop()
        results = []
        for r in rows:
            doc_id = r[0]
            total = r[1]
            pos = r[2]
            neg = r[3]
            results.append(DocumentUsefulness(
                document_id=doc_id,
                total_feedback=total,
                positive_count=pos,
                negative_count=neg,
                approval_rate=round(pos / max(total, 1), 3),
                authority_score=fb.get_document_authority(doc_id),
            ))
        return results

    def get_failure_patterns(self, limit: int = 20) -> list[dict]:
        """Get common retrieval failure patterns."""
        conn = get_connection()
        rows = conn.execute(
            """SELECT failure_type, COUNT(*) as cnt, COUNT(DISTINCT query) as unique_queries
            FROM retrieval_failures
            GROUP BY failure_type
            ORDER BY cnt DESC
            LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()
        return [
            {"failure_type": r[0], "count": r[1], "unique_queries": r[2]}
            for r in rows
        ]

    def get_learning_summary(self) -> dict:
        """Get a summary of what SANJAYA has learned from feedback."""
        conn = get_connection()
        try:
            # Total queries with signals
            row = conn.execute("SELECT COUNT(*) FROM query_signals").fetchone()
            total_queries = row[0] if row else 0

            # Queries with positive feedback
            row = conn.execute(
                "SELECT COUNT(*) FROM query_signals WHERE positive_count > 0"
            ).fetchone()
            positive_queries = row[0] if row else 0

            # Queries with negative feedback
            row = conn.execute(
                "SELECT COUNT(*) FROM query_signals WHERE negative_count > 0"
            ).fetchone()
            negative_queries = row[0] if row else 0

            # Documents with positive signal
            row = conn.execute(
                "SELECT COUNT(*) FROM document_signals WHERE positive_count > 0"
            ).fetchone()
            useful_docs = row[0] if row else 0

            # Documents with negative signal
            row = conn.execute(
                "SELECT COUNT(*) FROM document_signals WHERE negative_count > 0"
            ).fetchone()
            problematic_docs = row[0] if row else 0

            # Retrieval failures
            row = conn.execute("SELECT COUNT(*) FROM retrieval_failures").fetchone()
            total_failures = row[0] if row else 0

            return {
                "total_queries_with_signals": total_queries,
                "queries_with_positive_feedback": positive_queries,
                "queries_with_negative_feedback": negative_queries,
                "useful_documents": useful_docs,
                "problematic_documents": problematic_docs,
                "total_retrieval_failures": total_failures,
                "learning_active": True,  # Always active; FeedbackAwareRetriever controls actual adjustment
            }
        finally:
            conn.close()



