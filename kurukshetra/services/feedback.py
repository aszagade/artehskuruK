"""
SEAL Feedback Loop
==================

Tracks every query → retrieval → answer → user feedback cycle.
Adjusts chunk relevance scores based on accumulated feedback.
Boosts/reduces document authority based on feedback patterns.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from kurukshetra.registry.database import get_connection


@dataclass(slots=True)
class FeedbackEntry:
    """A single feedback record."""
    feedback_id: str
    query: str
    document_id: str
    chunk_id: str
    score: float
    is_correct: bool
    user_id: str
    suggested_tags: list[str]
    comments: str
    created_at: str


@dataclass(slots=True)
class ChunkScoreAdjustment:
    """Score adjustment for a chunk based on feedback history."""
    chunk_id: str
    original_score: float
    adjusted_score: float
    feedback_count: int
    positive_count: int
    negative_count: int
    adjustment_reason: str


class FeedbackLoop:
    """
    SEAL Feedback Loop implementation.

    Stores feedback in DuckDB and computes score adjustments
    based on accumulated user feedback.
    """

    def __init__(self) -> None:
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create feedback tables if they don't exist."""
        conn = get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rag_feedback (
                feedback_id TEXT PRIMARY KEY,
                query TEXT,
                document_id TEXT,
                chunk_id TEXT,
                score DOUBLE,
                is_correct BOOLEAN,
                user_id TEXT,
                suggested_tags TEXT,
                comments TEXT,
                created_at TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chunk_score_history (
                chunk_id TEXT,
                query TEXT,
                score DOUBLE,
                is_correct BOOLEAN,
                created_at TIMESTAMP
            )
        """)
        conn.close()

    def record_feedback(
        self,
        query: str,
        document_id: str,
        chunk_id: str,
        score: float,
        is_correct: bool,
        user_id: str = "system",
        suggested_tags: Optional[list[str]] = None,
        comments: str = "",
    ) -> FeedbackEntry:
        """
        Record user feedback for a retrieval result.

        Args:
            query: The original query
            document_id: Document that was returned
            chunk_id: Specific chunk that was returned
            score: Original retrieval score
            is_correct: Whether the result was correct/helpful
            user_id: Who provided feedback
            suggested_tags: Tags suggested by the user
            comments: Additional comments

        Returns:
            FeedbackEntry with the recorded feedback
        """
        feedback_id = f"FB-{int(time.time() * 1000)}"
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        entry = FeedbackEntry(
            feedback_id=feedback_id,
            query=query,
            document_id=document_id,
            chunk_id=chunk_id,
            score=score,
            is_correct=is_correct,
            user_id=user_id,
            suggested_tags=suggested_tags or [],
            comments=comments,
            created_at=timestamp,
        )

        conn = get_connection()
        conn.execute(
            """
            INSERT INTO rag_feedback
            (feedback_id, query, document_id, chunk_id, score, is_correct,
             user_id, suggested_tags, comments, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feedback_id,
                query,
                document_id,
                chunk_id,
                score,
                is_correct,
                user_id,
                json.dumps(suggested_tags or []),
                comments,
                timestamp,
            ),
        )
        conn.execute(
            """
            INSERT INTO chunk_score_history
            (chunk_id, query, score, is_correct, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (chunk_id, query, score, is_correct, timestamp),
        )
        conn.close()

        return entry

    def get_chunk_feedback_stats(self, chunk_id: str) -> dict:
        """
        Get accumulated feedback statistics for a chunk.

        Returns dict with:
            - total_feedback: total feedback count
            - positive_count: correct/helpful feedback count
            - negative_count: incorrect/unhelpful feedback count
            - avg_score: average retrieval score
            - confidence: feedback-based confidence (0-1)
        """
        conn = get_connection()
        row = conn.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) as positive,
                SUM(CASE WHEN NOT is_correct THEN 1 ELSE 0 END) as negative,
                AVG(score) as avg_score
            FROM chunk_score_history
            WHERE chunk_id = ?
            """,
            (chunk_id,),
        ).fetchone()
        conn.close()

        if row is None or row[0] == 0:
            return {
                "total_feedback": 0,
                "positive_count": 0,
                "negative_count": 0,
                "avg_score": 0.0,
                "confidence": 0.5,
            }

        total, positive, negative, avg_score = row
        positive = positive or 0
        negative = negative or 0

        # Confidence based on feedback consistency
        if total > 0:
            confidence = positive / total
        else:
            confidence = 0.5

        return {
            "total_feedback": total,
            "positive_count": positive,
            "negative_count": negative,
            "avg_score": avg_score or 0.0,
            "confidence": round(confidence, 3),
        }

    def adjust_score(
        self, chunk_id: str, original_score: float
    ) -> ChunkScoreAdjustment:
        """
        Adjust a chunk's retrieval score based on accumulated feedback.

        Chunks with many positive feedbacks get boosted.
        Chunks with many negative feedbacks get penalized.
        """
        stats = self.get_chunk_feedback_stats(chunk_id)

        if stats["total_feedback"] == 0:
            return ChunkScoreAdjustment(
                chunk_id=chunk_id,
                original_score=original_score,
                adjusted_score=original_score,
                feedback_count=0,
                positive_count=0,
                negative_count=0,
                adjustment_reason="No feedback history",
            )

        # Calculate adjustment multiplier
        # Positive ratio: 0.0 to 1.0
        positive_ratio = stats["confidence"]

        # Feedback volume bonus: more feedback = more reliable signal
        volume_factor = min(stats["total_feedback"] / 10.0, 1.0)

        # Adjustment: 0.7 (all negative) to 1.3 (all positive)
        if positive_ratio >= 0.8:
            multiplier = 1.0 + 0.3 * volume_factor
            reason = f"High approval ({stats['positive_count']}/{stats['total_feedback']})"
        elif positive_ratio >= 0.5:
            multiplier = 1.0
            reason = f"Moderate approval ({stats['positive_count']}/{stats['total_feedback']})"
        elif positive_ratio >= 0.3:
            multiplier = 1.0 - 0.2 * volume_factor
            reason = f"Low approval ({stats['positive_count']}/{stats['total_feedback']})"
        else:
            multiplier = 1.0 - 0.3 * volume_factor
            reason = f"Very low approval ({stats['positive_count']}/{stats['total_feedback']})"

        adjusted = original_score * multiplier

        return ChunkScoreAdjustment(
            chunk_id=chunk_id,
            original_score=original_score,
            adjusted_score=round(adjusted, 4),
            feedback_count=stats["total_feedback"],
            positive_count=stats["positive_count"],
            negative_count=stats["negative_count"],
            adjustment_reason=reason,
        )

    def get_document_authority(self, document_id: str) -> float:
        """
        Calculate document authority based on feedback history.

        Returns a multiplier (0.5 to 1.5) for the document's scores.
        """
        conn = get_connection()
        row = conn.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) as positive
            FROM rag_feedback
            WHERE document_id = ?
            """,
            (document_id,),
        ).fetchone()
        conn.close()

        if row is None or row[0] == 0:
            return 1.0  # Neutral for untested documents

        total, positive = row
        positive = positive or 0
        ratio = positive / total

        # Map ratio to authority multiplier
        # 100% correct → 1.5x, 50% → 1.0x, 0% → 0.5x
        return round(0.5 + ratio, 2)

    def get_negative_feedback_chunks(self, min_feedback: int = 3) -> list[dict]:
        """
        Get chunks that consistently receive negative feedback.

        These are candidates for:
        - Re-chunking
        - Content review
        - Deprioritization
        """
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT
                chunk_id,
                COUNT(*) as total,
                SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) as positive
            FROM chunk_score_history
            GROUP BY chunk_id
            HAVING COUNT(*) >= ? AND SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) * 1.0 / COUNT(*) < 0.3
            ORDER BY COUNT(*) DESC
            """,
            (min_feedback,),
        ).fetchall()
        conn.close()

        return [
            {
                "chunk_id": r[0],
                "total_feedback": r[1],
                "positive_count": r[2] or 0,
                "approval_rate": round((r[2] or 0) / r[1], 3) if r[1] > 0 else 0,
            }
            for r in rows
        ]
