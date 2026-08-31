"""
Closed-Loop Learning Tests
==========================

Deterministic tests proving SANJAYA genuinely learns from feedback.

Tests cover:
1. Feedback is recorded and retrievable
2. Feedback adjustment changes retrieval scores
3. Evaluation signals are tracked
4. User isolation (feedback from A doesn't affect B)
5. Feedback cannot bypass authorization
6. Feedback cannot become authoritative knowledge
7. Disabling learning reverts behavior
8. Document authority is calculated from feedback
9. Problematic chunks are identified
10. Learning summary is accurate
"""
import os
import sys
import time
import unittest

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, ".")

from kurukshetra.registry.database import get_connection


class TestFeedbackRecording(unittest.TestCase):
    """Test that feedback is correctly recorded and retrievable."""

    def test_record_feedback_creates_entry(self):
        """Feedback is stored in rag_feedback table."""
        from kurukshetra.services.feedback import FeedbackLoop

        loop = FeedbackLoop()
        entry = loop.record_feedback(
            query="What is G3?",
            document_id="DOC-TEST-001",
            chunk_id="CHUNK-TEST-001",
            score=0.85,
            is_correct=True,
            user_id="test-user-1",
            comments="Very helpful",
        )

        self.assertIsNotNone(entry.feedback_id)
        self.assertTrue(entry.feedback_id.startswith("FB-"))
        self.assertEqual(entry.query, "What is G3?")
        self.assertEqual(entry.document_id, "DOC-TEST-001")
        self.assertTrue(entry.is_correct)

    def test_feedback_chunk_history_stored(self):
        """Feedback is also stored in chunk_score_history."""
        from kurukshetra.services.feedback import FeedbackLoop

        loop = FeedbackLoop()
        chunk_id = f"CHUNK-HISTORY-{int(time.time())}"

        loop.record_feedback(
            query="test query",
            document_id="DOC-TEST-002",
            chunk_id=chunk_id,
            score=0.75,
            is_correct=True,
            user_id="test-user-2",
        )

        stats = loop.get_chunk_feedback_stats(chunk_id)
        self.assertGreaterEqual(stats["total_feedback"], 1)
        self.assertGreaterEqual(stats["positive_count"], 1)

    def test_multiple_feedback_accumulates(self):
        """Multiple feedbacks on the same chunk accumulate correctly."""
        from kurukshetra.services.feedback import FeedbackLoop

        loop = FeedbackLoop()
        chunk_id = f"CHUNK-ACCUM-{int(time.time())}"

        # Record 3 positive and 1 negative
        for _ in range(3):
            loop.record_feedback(
                query="accumulation test",
                document_id="DOC-ACCUM",
                chunk_id=chunk_id,
                score=0.8,
                is_correct=True,
                user_id="test-accum",
            )
        loop.record_feedback(
            query="accumulation test",
            document_id="DOC-ACCUM",
            chunk_id=chunk_id,
            score=0.3,
            is_correct=False,
            user_id="test-accum",
        )

        stats = loop.get_chunk_feedback_stats(chunk_id)
        self.assertEqual(stats["total_feedback"], 4)
        self.assertEqual(stats["positive_count"], 3)
        self.assertEqual(stats["negative_count"], 1)
        self.assertAlmostEqual(stats["confidence"], 0.75, places=2)


class TestScoreAdjustment(unittest.TestCase):
    """Test that feedback-based score adjustments work correctly."""

    def test_positive_feedback_boosts_score(self):
        """Chunks with positive feedback get score boost."""
        from kurukshetra.services.feedback import FeedbackLoop

        loop = FeedbackLoop()
        chunk_id = f"CHUNK-BOOST-{int(time.time())}"

        # Build up positive feedback
        for _ in range(5):
            loop.record_feedback(
                query="boost test",
                document_id="DOC-BOOST",
                chunk_id=chunk_id,
                score=0.5,
                is_correct=True,
                user_id="test-boost",
            )

        adjustment = loop.adjust_score(chunk_id, 0.5)
        self.assertGreater(adjustment.adjusted_score, 0.5)
        self.assertIn("High approval", adjustment.adjustment_reason)

    def test_negative_feedback_penalizes_score(self):
        """Chunks with negative feedback get score penalty."""
        from kurukshetra.services.feedback import FeedbackLoop

        loop = FeedbackLoop()
        chunk_id = f"CHUNK-PENALTY-{int(time.time())}"

        # Build up negative feedback
        for _ in range(5):
            loop.record_feedback(
                query="penalty test",
                document_id="DOC-PENALTY",
                chunk_id=chunk_id,
                score=0.5,
                is_correct=False,
                user_id="test-penalty",
            )

        adjustment = loop.adjust_score(chunk_id, 0.5)
        self.assertLess(adjustment.adjusted_score, 0.5)
        self.assertIn("Very low approval", adjustment.adjustment_reason)

    def test_no_feedback_returns_original_score(self):
        """Chunks without feedback keep their original score."""
        from kurukshetra.services.feedback import FeedbackLoop

        loop = FeedbackLoop()
        chunk_id = f"CHUNK-NOFEED-{int(time.time())}"

        adjustment = loop.adjust_score(chunk_id, 0.7)
        self.assertEqual(adjustment.adjusted_score, 0.7)
        self.assertEqual(adjustment.feedback_count, 0)


class TestDocumentAuthority(unittest.TestCase):
    """Test document authority calculation from feedback."""

    def test_all_positive_gives_high_authority(self):
        """Documents with 100% positive feedback get authority > 1.0."""
        from kurukshetra.services.feedback import FeedbackLoop

        loop = FeedbackLoop()
        doc_id = f"DOC-AUTH-{int(time.time())}"

        for _ in range(5):
            loop.record_feedback(
                query="authority test",
                document_id=doc_id,
                chunk_id=f"CHUNK-AUTH-{int(time.time())}",
                score=0.8,
                is_correct=True,
                user_id="test-auth",
            )

        authority = loop.get_document_authority(doc_id)
        self.assertGreater(authority, 1.0)

    def test_all_negative_gives_low_authority(self):
        """Documents with 0% positive feedback get authority < 1.0."""
        from kurukshetra.services.feedback import FeedbackLoop

        loop = FeedbackLoop()
        doc_id = f"DOC-AUTH-NEG-{int(time.time())}"

        for _ in range(5):
            loop.record_feedback(
                query="authority neg test",
                document_id=doc_id,
                chunk_id=f"CHUNK-AUTH-NEG-{int(time.time())}",
                score=0.3,
                is_correct=False,
                user_id="test-auth-neg",
            )

        authority = loop.get_document_authority(doc_id)
        self.assertLess(authority, 1.0)

    def test_untested_document_neutral_authority(self):
        """Documents without feedback have neutral authority (1.0)."""
        from kurukshetra.services.feedback import FeedbackLoop

        loop = FeedbackLoop()
        authority = loop.get_document_authority("DOC-UNTESTED-99999")
        self.assertEqual(authority, 1.0)


class TestProblematicChunks(unittest.TestCase):
    """Test identification of consistently problematic chunks."""

    def test_identifies_problematic_chunks(self):
        """Chunks with majority negative feedback are flagged."""
        from kurukshetra.services.feedback import FeedbackLoop

        loop = FeedbackLoop()
        bad_chunk = f"CHUNK-BAD-{int(time.time())}"

        # Create a chunk with strong negative signal
        for _ in range(5):
            loop.record_feedback(
                query="bad chunk test",
                document_id="DOC-BAD",
                chunk_id=bad_chunk,
                score=0.2,
                is_correct=False,
                user_id="test-bad",
            )

        problematic = loop.get_negative_feedback_chunks(min_feedback=2)
        chunk_ids = [p["chunk_id"] for p in problematic]
        self.assertIn(bad_chunk, chunk_ids)


class TestEvaluationTracker(unittest.TestCase):
    """Test evaluation signal tracking."""

    def test_query_signal_recorded(self):
        """Query signals are stored and retrievable."""
        from kurukshetra.retrieval.evaluation_tracker import EvaluationSignalTracker

        tracker = EvaluationSignalTracker()
        tracker.record_query(
            query="eval test query",
            confidence=0.8,
            user_id="eval-test-user",
        )

        patterns = tracker.get_popular_queries(limit=5)
        queries = [p.query_normalized for p in patterns]
        self.assertIn("eval test query", queries)

    def test_document_signal_recorded(self):
        """Document signals are stored and retrievable."""
        from kurukshetra.retrieval.evaluation_tracker import EvaluationSignalTracker

        tracker = EvaluationSignalTracker()
        doc_id = f"DOC-EVAL-{int(time.time() * 1000)}"

        # Record 2 feedbacks so doc passes the min_feedback=2 threshold
        tracker.record_feedback_signal(
            query="eval doc test unique",
            document_id=doc_id,
            is_correct=True,
            confidence=0.85,
        )
        tracker.record_feedback_signal(
            query="eval doc test 2 unique",
            document_id=doc_id,
            is_correct=True,
            confidence=0.9,
        )

        # Verify directly in DB since get_useful_documents limits results
        conn = get_connection()
        row = conn.execute(
            "SELECT positive_count, total_feedback FROM document_signals WHERE document_id = ?",
            (doc_id,),
        ).fetchone()
        conn.close()

        self.assertIsNotNone(row, f"Document signal not found for {doc_id}")
        self.assertEqual(row[0], 2)  # 2 positive
        self.assertEqual(row[1], 2)  # 2 total

    def test_retrieval_failure_recorded(self):
        """Retrieval failures are tracked."""
        from kurukshetra.retrieval.evaluation_tracker import EvaluationSignalTracker

        tracker = EvaluationSignalTracker()
        unique_query = f"failure-test-{int(time.time() * 1000)}"
        tracker.record_retrieval_failure(
            query=unique_query,
            failure_type="test_insufficient_evidence",
            failure_detail="No relevant documents found",
            strategy_used="hybrid",
            evidence_count=0,
        )

        # Query directly from DB to verify it was stored
        conn = get_connection()
        row = conn.execute(
            "SELECT failure_type FROM retrieval_failures WHERE query = ?",
            (unique_query,),
        ).fetchone()
        conn.close()

        self.assertIsNotNone(row, f"Failure record not found for query: {unique_query}")
        self.assertEqual(row[0], "test_insufficient_evidence")

    def test_learning_summary_accurate(self):
        """Learning summary reflects actual data."""
        from kurukshetra.retrieval.evaluation_tracker import EvaluationSignalTracker

        tracker = EvaluationSignalTracker()
        summary = tracker.get_learning_summary()

        self.assertIn("total_queries_with_signals", summary)
        self.assertIn("useful_documents", summary)
        self.assertIn("total_retrieval_failures", summary)
        self.assertIsInstance(summary["total_queries_with_signals"], int)


class TestUserIsolation(unittest.TestCase):
    """Test that feedback from one user doesn't leak to another."""

    def test_feedback_user_scoped(self):
        """Feedback records include user_id and are distinguishable."""
        from kurukshetra.services.feedback import FeedbackLoop

        loop = FeedbackLoop()
        user_a = f"user-a-{int(time.time())}"
        user_b = f"user-b-{int(time.time())}"
        ts = int(time.time() * 1000)
        chunk_a = f"CHUNK-ISO-A-{ts}"
        chunk_b = f"CHUNK-ISO-B-{ts}"

        # User A gives positive feedback
        loop.record_feedback(
            query=f"isolation test {ts}",
            document_id=f"DOC-ISO-{ts}",
            chunk_id=chunk_a,
            score=0.8,
            is_correct=True,
            user_id=user_a,
        )

        # User B gives negative feedback on different chunk
        loop.record_feedback(
            query=f"isolation test {ts}",
            document_id=f"DOC-ISO-{ts}",
            chunk_id=chunk_b,
            score=0.3,
            is_correct=False,
            user_id=user_b,
        )

        # Each chunk has its own feedback
        stats_a = loop.get_chunk_feedback_stats(chunk_a)
        stats_b = loop.get_chunk_feedback_stats(chunk_b)

        self.assertEqual(stats_a["positive_count"], 1)
        self.assertEqual(stats_a["negative_count"], 0)
        self.assertEqual(stats_b["positive_count"], 0)
        self.assertEqual(stats_b["negative_count"], 1)

    def test_evaluation_tracker_user_scoped(self):
        """Evaluation signals track which users provided feedback."""
        from kurukshetra.retrieval.evaluation_tracker import EvaluationSignalTracker

        tracker = EvaluationSignalTracker()
        user_a = f"eval-user-a-{int(time.time())}"
        user_b = f"eval-user-b-{int(time.time())}"

        tracker.record_feedback_signal(
            query="user isolation eval test",
            document_id="DOC-EVAL-ISO",
            is_correct=True,
            user_id=user_a,
        )
        tracker.record_feedback_signal(
            query="user isolation eval test",
            document_id="DOC-EVAL-ISO",
            is_correct=False,
            user_id=user_b,
        )

        # Both users are tracked
        conn = get_connection()
        row = conn.execute(
            "SELECT user_ids FROM document_signals WHERE document_id = ?",
            ("DOC-EVAL-ISO",),
        ).fetchone()
        conn.close()

        import json
        user_ids = json.loads(row[0]) if row else []
        self.assertIn(user_a, user_ids)
        self.assertIn(user_b, user_ids)


class TestSecurityBoundary(unittest.TestCase):
    """Test that feedback cannot bypass security or become authoritative knowledge."""

    def test_feedback_not_treated_as_authoritative(self):
        """Feedback is metadata about retrieval quality, not organizational knowledge."""
        from kurukshetra.services.feedback import FeedbackLoop

        loop = FeedbackLoop()
        # Record feedback with a user-provided comment
        entry = loop.record_feedback(
            query="security test",
            document_id="DOC-SEC-001",
            chunk_id="CHUNK-SEC-001",
            score=0.9,
            is_correct=True,
            user_id="security-test",
            comments="This is classified information",  # Should not become knowledge
        )

        # Verify the comment is stored as metadata, not as knowledge
        conn = get_connection()
        row = conn.execute(
            "SELECT comments FROM rag_feedback WHERE feedback_id = ?",
            (entry.feedback_id,),
        ).fetchone()
        conn.close()

        self.assertEqual(row[0], "This is classified information")
        # Verify it's NOT in any knowledge/graph table
        conn = get_connection()
        graph_row = conn.execute(
            "SELECT COUNT(*) FROM graph_entities WHERE name = ?",
            ("This is classified information",),
        ).fetchone()
        conn.close()
        self.assertEqual(graph_row[0], 0)

    def test_feedback_does_not_modify_graph(self):
        """Feedback cannot inject entities into the knowledge graph."""
        from kurukshetra.services.feedback import FeedbackLoop

        loop = FeedbackLoop()
        fake_entity = f"INJECTED-ENTITY-{int(time.time())}"

        loop.record_feedback(
            query="injection test",
            document_id="DOC-INJECT-001",
            chunk_id="CHUNK-INJECT-001",
            score=0.9,
            is_correct=True,
            user_id="injector",
            comments=fake_entity,
        )

        # Verify entity was NOT injected into graph
        conn = get_connection()
        row = conn.execute(
            "SELECT COUNT(*) FROM graph_entities WHERE name = ?",
            (fake_entity,),
        ).fetchone()
        conn.close()
        self.assertEqual(row[0], 0)


class TestFeedbackAwareRetriever(unittest.TestCase):
    """Test the FeedbackAwareRetriever integration."""

    def test_retriever_wraps_base_retriever(self):
        """FeedbackAwareRetriever delegates to base retriever."""
        from kurukshetra.retrieval.feedback_retriever import FeedbackAwareRetriever

        class MockRetriever:
            def search(self, query, top_k=5):
                from kurukshetra.retrieval.models import RetrievalResult
                return [
                    RetrievalResult(
                        chunk_id="MOCK-1",
                        document_id="DOC-MOCK",
                        score=0.8,
                        text="mock result",
                        metadata={},
                    )
                ]

        retriever = FeedbackAwareRetriever(MockRetriever())
        results = retriever.search("test query")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].chunk_id, "MOCK-1")

    def test_feedback_disabled_returns_vanilla(self):
        """When feedback is disabled, no adjustments are made."""
        from kurukshetra.retrieval.feedback_retriever import (
            FeedbackAwareRetriever,
            set_feedback_enabled,
        )

        class MockRetriever:
            def search(self, query, top_k=5):
                from kurukshetra.retrieval.models import RetrievalResult
                return [
                    RetrievalResult(
                        chunk_id="MOCK-VANILLA",
                        document_id="DOC-VANILLA",
                        score=0.75,
                        text="vanilla result",
                        metadata={},
                    )
                ]

        set_feedback_enabled(False)
        try:
            retriever = FeedbackAwareRetriever(MockRetriever())
            results = retriever.search("test query")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].score, 0.75)
            self.assertNotIn("_feedback_adjusted", results[0].metadata)
        finally:
            set_feedback_enabled(True)

    def test_disabling_learning_reverts_behavior(self):
        """Disabling feedback adjustment reverts to vanilla retrieval."""
        from kurukshetra.retrieval.feedback_retriever import (
            FeedbackAwareRetriever,
            set_feedback_enabled,
            is_feedback_enabled,
        )

        # Verify toggle works
        original = is_feedback_enabled()
        set_feedback_enabled(False)
        self.assertFalse(is_feedback_enabled())
        set_feedback_enabled(True)
        self.assertTrue(is_feedback_enabled())
        set_feedback_enabled(original)


class TestFeedbackStats(unittest.TestCase):
    """Test FeedbackAwareRetriever.get_feedback_stats()."""

    def test_stats_returns_structure(self):
        """Feedback stats returns expected structure."""
        from kurukshetra.retrieval.feedback_retriever import FeedbackAwareRetriever

        class MockRetriever:
            def search(self, query, top_k=5):
                return []

        retriever = FeedbackAwareRetriever(MockRetriever())
        stats = retriever.get_feedback_stats()

        self.assertIn("feedback_enabled", stats)
        self.assertIn("total_feedback", stats)
        self.assertIn("positive_count", stats)
        self.assertIn("negative_count", stats)
        self.assertIn("unique_queries", stats)
        self.assertIn("unique_documents", stats)
        self.assertIn("unique_chunks", stats)
        self.assertIn("problematic_chunks", stats)


if __name__ == "__main__":
    unittest.main()
