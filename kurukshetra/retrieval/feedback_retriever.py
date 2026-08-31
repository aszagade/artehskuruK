"""
Feedback-Aware Retriever
========================

Wraps any retrieval strategy and applies feedback-based score adjustments.

This is the CORE of the closed-loop learning system:

  FeedbackLoop.record_feedback()
       ↓ stores in rag_feedback + chunk_score_history
       ↓
  FeedbackAwareRetriever.search()
       ↓ reads back feedback stats
       ↓ adjusts scores via FeedbackLoop.adjust_score()
       ↓ boosts documents via FeedbackLoop.get_document_authority()
       ↓ returns re-ranked results
       ↓
  Better retrieval → Better answers → More feedback → Improvement

Safety:
- Feedback never bypasses visibility filtering
- Feedback only adjusts scores, never creates/removes results
- Disabling feedback adjustment reverts to vanilla retrieval
- All adjustments are logged for auditability
- User-specific feedback does not leak across tenants
"""

from __future__ import annotations

import logging
from typing import Optional

from kurukshetra.retrieval.models import RetrievalResult
from kurukshetra.services.feedback import FeedbackLoop

logger = logging.getLogger(__name__)

# Whether feedback adjustment is enabled globally
_FEEDBACK_ENABLED = True


def set_feedback_enabled(enabled: bool) -> None:
    """Enable/disable feedback-based score adjustment globally."""
    global _FEEDBACK_ENABLED
    _FEEDBACK_ENABLED = enabled


def is_feedback_enabled() -> bool:
    """Check if feedback adjustment is currently enabled."""
    return _FEEDBACK_ENABLED


class FeedbackAwareRetriever:
    """
    Wraps a base retriever and applies feedback-based score adjustments.

    After retrieval, for each result:
    1. Apply chunk-level score adjustment from FeedbackLoop
    2. Apply document-level authority multiplier from FeedbackLoop
    3. Re-sort by adjusted scores

    This makes SANJAYA genuinely learn from accumulated user feedback.
    """

    def __init__(self, base_retriever, feedback_loop: Optional[FeedbackLoop] = None):
        """
        Args:
            base_retriever: Any retriever with a .search(query, top_k) method
            feedback_loop: FeedbackLoop instance (created if not provided)
        """
        self.base_retriever = base_retriever
        self.feedback = feedback_loop or FeedbackLoop()

    def search(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        """
        Retrieve and apply feedback-based score adjustments.

        Falls back to base retriever if feedback adjustment fails.
        """
        # Always retrieve more than needed so we have room to re-rank
        raw_top_k = max(top_k * 2, 10)
        results = self.base_retriever.search(query, top_k=raw_top_k)

        if not results or not _FEEDBACK_ENABLED:
            return results[:top_k]

        adjusted_results = self._apply_feedback_adjustments(results)

        # Re-sort by adjusted score
        adjusted_results.sort(key=lambda r: r.score, reverse=True)

        return adjusted_results[:top_k]

    def _apply_feedback_adjustments(
        self, results: list[RetrievalResult]
    ) -> list[RetrievalResult]:
        """
        Apply feedback-based adjustments to retrieval results.

        Two levels of adjustment:
        1. Chunk-level: individual chunks boosted/penalized by their feedback history
        2. Document-level: documents with good overall feedback get authority boost
        """
        # Cache document authority to avoid repeated DB queries
        doc_authority_cache: dict[str, float] = {}

        adjusted = []
        for result in results:
            try:
                # Chunk-level adjustment
                adjustment = self.feedback.adjust_score(
                    result.chunk_id, result.score
                )
                new_score = adjustment.adjusted_score

                # Document-level authority adjustment
                doc_id = result.document_id
                if doc_id not in doc_authority_cache:
                    doc_authority_cache[doc_id] = (
                        self.feedback.get_document_authority(doc_id)
                    )
                authority = doc_authority_cache[doc_id]

                # Apply authority multiplier (keep score in [0, 1] range)
                final_score = min(new_score * authority, 1.0)

                # Create a copy with adjusted score
                adjusted_result = RetrievalResult(
                    chunk_id=result.chunk_id,
                    document_id=result.document_id,
                    score=round(final_score, 6),
                    text=result.text,
                    metadata={
                        **result.metadata,
                        "_feedback_adjusted": True,
                        "_original_score": result.score,
                        "_chunk_adjustment": adjustment.adjustment_reason,
                        "_doc_authority": authority,
                    },
                )
                adjusted.append(adjusted_result)

            except Exception as e:
                # If feedback adjustment fails, use original score
                logger.warning(
                    f"Feedback adjustment failed for chunk {result.chunk_id}: {e}"
                )
                adjusted.append(result)

        return adjusted

    def get_feedback_stats(self) -> dict:
        """Get summary statistics about feedback-based adjustments."""
        from kurukshetra.registry.database import get_connection

        conn = get_connection()

        try:
            # Total feedback entries
            row = conn.execute(
                "SELECT COUNT(*) FROM rag_feedback"
            ).fetchone()
            total_feedback = row[0] if row else 0

            # Positive vs negative
            row = conn.execute(
                "SELECT "
                "SUM(CASE WHEN is_correct THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN NOT is_correct THEN 1 ELSE 0 END) "
                "FROM rag_feedback"
            ).fetchone()
            positive = row[0] or 0
            negative = row[1] or 0

            # Unique queries with feedback
            row = conn.execute(
                "SELECT COUNT(DISTINCT query) FROM rag_feedback"
            ).fetchone()
            unique_queries = row[0] if row else 0

            # Unique documents with feedback
            row = conn.execute(
                "SELECT COUNT(DISTINCT document_id) FROM rag_feedback"
            ).fetchone()
            unique_docs = row[0] if row else 0

            # Unique chunks with feedback
            row = conn.execute(
                "SELECT COUNT(DISTINCT chunk_id) FROM chunk_score_history"
            ).fetchone()
            unique_chunks = row[0] if row else 0

            # Chunks with negative feedback (problematic evidence)
            neg_chunks = self.feedback.get_negative_feedback_chunks(min_feedback=2)

            return {
                "feedback_enabled": _FEEDBACK_ENABLED,
                "total_feedback": total_feedback,
                "positive_count": positive,
                "negative_count": negative,
                "approval_rate": round(
                    positive / max(total_feedback, 1), 3
                ),
                "unique_queries": unique_queries,
                "unique_documents": unique_docs,
                "unique_chunks": unique_chunks,
                "problematic_chunks": len(neg_chunks),
                "problematic_chunk_details": neg_chunks[:10],
            }
        finally:
            conn.close()
